import asyncio
import io
import json
import logging
import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional, cast

from httpx import HTTPStatusError
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import JSONRPCResponse, ListToolsResult
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pysignalr.client import SignalRClient
from pysignalr.messages import CompletionMessage
from uipath import UiPath
from uipath._cli._runtime._contracts import (
    UiPathBaseRuntime,
    UiPathErrorCategory,
    UiPathRuntimeResult,
)
from uipath.tracing import LlmOpsHttpExporter

from .._utils._config import McpServer
from ._context import UiPathMcpRuntimeContext, UiPathServerType
from ._exception import UiPathMcpRuntimeError
from ._session import SessionServer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class UiPathMcpRuntime(UiPathBaseRuntime):
    """
    A runtime class for hosting UiPath MCP servers.
    """

    def __init__(self, context: UiPathMcpRuntimeContext):
        super().__init__(context)
        self.context: UiPathMcpRuntimeContext = context
        self._server: Optional[McpServer] = None
        self._runtime_id = (
            self.context.job_id if self.context.job_id else str(uuid.uuid4())
        )
        self._signalr_client: Optional[SignalRClient] = None
        self._session_servers: Dict[str, SessionServer] = {}
        self._session_output: Optional[str] = None
        self._cancel_event = asyncio.Event()
        self._keep_alive_task: Optional[asyncio.Task[None]] = None
        self._uipath = UiPath()

    async def validate(self) -> None:
        """Validate runtime inputs and load MCP server configuration."""
        if self.context.config is None:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing configuration",
                "Configuration is required.",
                UiPathErrorCategory.SYSTEM,
            )

        if self.context.entrypoint is None:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing entrypoint",
                "Entrypoint is required.",
                UiPathErrorCategory.SYSTEM,
            )

        self._server = self.context.config.get_server(self.context.entrypoint)
        if not self._server:
            raise UiPathMcpRuntimeError(
                "SERVER_NOT_FOUND",
                "MCP server not found",
                f"Server '{self.context.entrypoint}' not found in configuration",
                UiPathErrorCategory.DEPLOYMENT,
            )

    def _validate_auth(self) -> None:
        """Validate authentication-related configuration.

        Raises:
            UiPathMcpRuntimeError: If any required authentication values are missing.
        """
        uipath_url = os.environ.get("UIPATH_URL")
        if not uipath_url:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing UIPATH_URL environment variable",
                "Please run 'uipath auth'.",
                UiPathErrorCategory.USER,
            )

        if not self.context.trace_context:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing trace context",
                "Trace context is required for SignalR connection.",
                UiPathErrorCategory.SYSTEM,
            )

        if not self.context.trace_context.tenant_id:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing tenant ID",
                "Please run 'uipath auth'.",
                UiPathErrorCategory.SYSTEM,
            )

        if not self.context.trace_context.org_id:
            raise UiPathMcpRuntimeError(
                "CONFIGURATION_ERROR",
                "Missing organization ID",
                "Please run 'uipath auth'.",
                UiPathErrorCategory.SYSTEM,
            )

    async def execute(self) -> Optional[UiPathRuntimeResult]:
        """
        Start the MCP Server runtime.

        Returns:
            Dictionary with execution results

        Raises:
            UiPathMcpRuntimeError: If execution fails
        """
        await self.validate()

        try:
            if self._server is None:
                return None

            if self.context.job_id:
                self.trace_provider = TracerProvider()
                trace.set_tracer_provider(self.trace_provider)
                self.trace_provider.add_span_processor(
                    BatchSpanProcessor(LlmOpsHttpExporter())
                )

            # Validate authentication configuration
            self._validate_auth()

            # Set up SignalR client
            uipath_url = os.environ.get("UIPATH_URL")
            signalr_url = f"{uipath_url}/agenthub_/wsstunnel?slug={self.slug}&runtimeId={self._runtime_id}"

            if not self.context.folder_key:
                folder_path = os.environ.get("UIPATH_FOLDER_PATH")
                if not folder_path:
                    raise UiPathMcpRuntimeError(
                        "REGISTRATION_ERROR",
                        "No UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable set.",
                        "Please set the UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable.",
                        UiPathErrorCategory.USER,
                    )
                self.context.folder_key = self._uipath.folders.retrieve_key(
                    folder_path=folder_path
                )
                if not self.context.folder_key:
                    raise UiPathMcpRuntimeError(
                        "REGISTRATION_ERROR",
                        "Folder NOT FOUND. Invalid UIPATH_FOLDER_PATH environment variable.",
                        "Please set the UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable.",
                        UiPathErrorCategory.USER,
                    )

            logger.info(f"Folder key: {self.context.folder_key}")

            with tracer.start_as_current_span(self.slug) as root_span:
                root_span.set_attribute("runtime_id", self._runtime_id)
                root_span.set_attribute("command", str(self._server.command))
                root_span.set_attribute("args", json.dumps(self._server.args))
                root_span.set_attribute("span_type", "MCP Server")
                bearer_token = os.environ.get("UIPATH_ACCESS_TOKEN")
                self._signalr_client = SignalRClient(
                    signalr_url,
                    headers={
                        "X-UiPath-Internal-TenantId": self.context.trace_context.tenant_id,  # type: ignore
                        "X-UiPath-Internal-AccountId": self.context.trace_context.org_id,  # type: ignore
                        "X-UIPATH-FolderKey": self.context.folder_key,
                        "Authorization": f"Bearer {bearer_token}",
                    },
                )
                self._signalr_client.on("MessageReceived", self._handle_signalr_message)
                self._signalr_client.on(
                    "SessionClosed", self._handle_signalr_session_closed
                )
                self._signalr_client.on_error(self._handle_signalr_error)
                self._signalr_client.on_open(self._handle_signalr_open)
                self._signalr_client.on_close(self._handle_signalr_close)

                # Register the local server with UiPath MCP Server
                await self._register()

                run_task = asyncio.create_task(self._signalr_client.run())
                cancel_task = asyncio.create_task(self._cancel_event.wait())
                self._keep_alive_task = asyncio.create_task(self._keep_alive())

                try:
                    # Wait for either the run to complete or cancellation
                    done, pending = await asyncio.wait(
                        [run_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                    )
                except KeyboardInterrupt:
                    logger.info(
                        "Received keyboard interrupt, shutting down gracefully..."
                    )
                    self._cancel_event.set()
                finally:
                    # Cancel any pending tasks gracefully
                    for task in [run_task, cancel_task, self._keep_alive_task]:
                        if task and not task.done():
                            task.cancel()
                            try:
                                await asyncio.wait_for(task, timeout=2.0)
                            except (asyncio.CancelledError, asyncio.TimeoutError):
                                pass

                output_result = {}
                if self._session_output:
                    output_result["content"] = self._session_output

                self.context.result = UiPathRuntimeResult(output=output_result)
                return self.context.result

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            return None
        except Exception as e:
            if isinstance(e, UiPathMcpRuntimeError):
                raise
            detail = f"Error: {str(e)}"
            raise UiPathMcpRuntimeError(
                "EXECUTION_ERROR",
                "MCP Runtime execution failed",
                detail,
                UiPathErrorCategory.USER,
            ) from e
        finally:
            await self.cleanup()
            if hasattr(self, "trace_provider") and self.trace_provider:
                self.trace_provider.shutdown()

    async def cleanup(self) -> None:
        """Clean up all resources."""

        await self._on_runtime_abort()

        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass

        for session_id, session_server in self._session_servers.items():
            try:
                await session_server.stop()
            except Exception as e:
                logger.error(f"Error cleaning up session server {session_id}: {str(e)}")

        if self._signalr_client and hasattr(self._signalr_client, "_transport"):
            transport = self._signalr_client._transport
            if transport and hasattr(transport, "_ws") and transport._ws:
                try:
                    await transport._ws.close()
                except Exception as e:
                    logger.error(f"Error closing SignalR WebSocket: {str(e)}")

        # Add a small delay to allow the server to shut down gracefully
        if sys.platform == "win32":
            await asyncio.sleep(0.5)

    async def _handle_signalr_session_closed(self, args: list[str]) -> None:
        """
        Handle session closed by server.
        """
        if len(args) < 1:
            logger.error(f"Received invalid websocket message arguments: {args}")
            return

        session_id = args[0]

        logger.info(f"Received closed signal for session {session_id}")

        try:
            session_server = self._session_servers.pop(session_id, None)
            if session_server:
                await session_server.stop()
                if session_server.output:
                    if self.sandboxed:
                        self._session_output = session_server.output
                    else:
                        logger.info(
                            f"Session {session_id} output: {session_server.output}"
                        )
            # If this is a sandboxed runtime for a specific session, cancel the execution
            if self.sandboxed:
                self._cancel_event.set()

        except Exception as e:
            logger.error(f"Error terminating session {session_id}: {str(e)}")

    async def _handle_signalr_message(self, args: list[str]) -> None:
        """
        Handle incoming SignalR messages.
        """
        if len(args) < 2:
            logger.error(f"Received invalid websocket message arguments: {args}")
            return

        session_id = args[0]
        request_id = args[1]

        logger.info(f"Received websocket notification... {session_id}")

        try:
            server = cast(McpServer, self._server)

            # Check if we have a session server for this session_id
            if session_id not in self._session_servers:
                # Create and start a new session server
                session_server = SessionServer(server, self.slug, session_id)
                try:
                    await session_server.start()
                except Exception as e:
                    logger.error(
                        f"Error starting session server for session {session_id}: {str(e)}"
                    )
                    await self._on_session_start_error(session_id)
                    raise
                self._session_servers[session_id] = session_server

            # Get the session server for this session
            session_server = self._session_servers[session_id]

            # Forward the message to the session's MCP server
            await session_server.on_message_received(request_id)

        except Exception as e:
            logger.error(
                f"Error handling websocket notification for session {session_id}: {str(e)}"
            )

    async def _handle_signalr_error(self, error: Any) -> None:
        """Handle SignalR errors."""
        logger.error(f"Websocket error: {error}")

    async def _handle_signalr_open(self) -> None:
        """Handle SignalR connection open event."""
        logger.info("Websocket connection established.")

    async def _handle_signalr_close(self) -> None:
        """Handle SignalR connection close event."""
        logger.info("Websocket connection closed.")

    async def _register(self) -> None:
        """Register the MCP server with UiPath."""
        server = cast(McpServer, self._server)

        initialization_successful = False
        tools_result: Optional[ListToolsResult] = None
        server_stderr_output = ""
        env_vars = dict(server.env)

        # if server is Coded, include environment variables
        if self.server_type is UiPathServerType.Coded:
            for name, value in os.environ.items():
                # config env variables should have precedence over system ones
                if name not in env_vars:
                    env_vars[name] = value

        try:
            # Create a temporary session to get tools
            server_params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=env_vars,
            )

            # Start a temporary stdio client to get tools
            # Use a temporary file to capture stderr
            with tempfile.TemporaryFile(mode="w+b") as stderr_temp_binary:
                stderr_temp = io.TextIOWrapper(stderr_temp_binary, encoding="utf-8")
                async with stdio_client(server_params, errlog=stderr_temp) as (
                    read,
                    write,
                ):
                    async with ClientSession(read, write) as session:
                        logger.info("Initializing client session...")
                        # Try to initialize with timeout
                        try:
                            await asyncio.wait_for(session.initialize(), timeout=30)
                            initialization_successful = True
                            logger.info("Initialization successful")

                            # Only proceed if initialization was successful
                            tools_result = await session.list_tools()
                            # logger.info(tools_result)
                        except asyncio.TimeoutError:
                            logger.error("Initialization timed out")
                            # Capture stderr output here, after the timeout
                            stderr_temp.seek(0)
                            server_stderr_output = stderr_temp.read()

        except* Exception as eg:
            for e in eg.exceptions:
                logger.error(
                    f"Unexpected error: {e}",
                    exc_info=True,
                )

        # Now that we're outside the context managers, check if initialization succeeded
        if not initialization_successful:
            await self._on_runtime_abort()
            error_message = "The server process failed to initialize. Verify environment variables are set correctly."
            if server_stderr_output:
                error_message += f"\nServer error output:\n{server_stderr_output}"
            raise UiPathMcpRuntimeError(
                "INITIALIZATION_ERROR",
                "Server initialization failed",
                error_message,
                UiPathErrorCategory.DEPLOYMENT,
            )

        # If we got here, initialization was successful and we have the tools
        # Now continue with registration
        logger.info("Registering server runtime ...")
        try:
            if not tools_result:
                raise UiPathMcpRuntimeError(
                    "INITIALIZATION_ERROR",
                    "Server initialization failed",
                    "Failed to get tools list from server",
                    UiPathErrorCategory.DEPLOYMENT,
                )

            tools_list: List[Dict[str, str | None]] = []
            client_info = {
                "server": {
                    "Name": self.slug,
                    "Slug": self.slug,
                    "Id": self.context.server_id,
                    "Version": "1.0.0",
                    "Type": self.server_type.value,
                },
                "tools": tools_list,
            }

            for tool in tools_result.tools:
                tool_info = {
                    "Name": tool.name,
                    "ProcessType": "Tool",
                    "Description": tool.description,
                    "InputSchema": json.dumps(tool.inputSchema)
                    if tool.inputSchema
                    else "{}",
                }
                tools_list.append(tool_info)

            # Register with UiPath MCP Server
            await self._uipath.api_client.request_async(
                "POST",
                f"agenthub_/mcp/{self.slug}/runtime/start?runtimeId={self._runtime_id}",
                json=client_info,
                headers={"X-UIPATH-FolderKey": self.context.folder_key},
            )
            logger.info("Registered MCP Server type successfully")
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            if isinstance(e, HTTPStatusError):
                logger.error(
                    f"HTTP error details: {e.response.text} status code: {e.response.status_code}"
                )

            raise UiPathMcpRuntimeError(
                "REGISTRATION_ERROR",
                "Failed to register MCP Server",
                str(e),
                UiPathErrorCategory.SYSTEM,
            ) from e

    async def _on_session_start_error(self, session_id: str) -> None:
        """
        Sends a dummy initialization failure message to abort the already connected client.
        Sandboxed runtimes are triggered by new client connections.
        """
        try:
            response = await self._uipath.api_client.request_async(
                "POST",
                f"agenthub_/mcp/{self.slug}/out/message?sessionId={session_id}",
                json=JSONRPCResponse(
                    jsonrpc="2.0",
                    id=0,
                    result={
                        "protocolVersion": "initialize-failure",
                        "capabilities": {},
                        "serverInfo": {"name": self.slug, "version": "1.0"},
                    },
                ).model_dump(),
            )
            if response.status_code == 202:
                logger.info(
                    f"Sent outgoing session dispose message to UiPath MCP Server: {session_id}"
                )
            else:
                logger.error(
                    f"Error sending session dispose message to UiPath MCP Server: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(
                f"Error sending session dispose signal to UiPath MCP Server: {e}"
            )

    async def _keep_alive(self) -> None:
        """
        Heartbeat to keep the runtime available.
        """
        try:
            while not self._cancel_event.is_set():
                try:

                    async def on_keep_alive_response(
                        response: CompletionMessage,
                    ) -> None:
                        if response.error:
                            logger.error(f"Error during keep-alive: {response.error}")
                            return
                        session_ids = response.result
                        logger.info(f"Active sessions: {session_ids}")
                        # If there are no active sessions and this is a sandbox environment
                        # We need to cancel the runtime
                        # eg: when user kills the agent that triggered the runtime, before we subscribe to events
                        if (
                            not session_ids
                            and self.sandboxed
                            and not self._cancel_event.is_set()
                        ):
                            logger.error(
                                "No active sessions, cancelling sandboxed runtime..."
                            )
                            self._cancel_event.set()

                    if self._signalr_client:
                        await self._signalr_client.send(
                            method="OnKeepAlive",
                            arguments=[],
                            on_invocation=on_keep_alive_response,  # type: ignore
                        )
                except Exception as e:
                    if not self._cancel_event.is_set():
                        logger.error(f"Error during keep-alive: {e}")

                try:
                    await asyncio.wait_for(self._cancel_event.wait(), timeout=60)
                    break
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("Keep-alive task cancelled")
            raise

    async def _on_runtime_abort(self) -> None:
        """
        Sends a runtime abort signalr to terminate all connected sessions.
        """
        try:
            response = await self._uipath.api_client.request_async(
                "POST",
                f"agenthub_/mcp/{self.slug}/runtime/abort?runtimeId={self._runtime_id}",
            )
            if response.status_code == 202:
                logger.info(
                    f"Sent runtime abort signal to UiPath MCP Server: {self._runtime_id}"
                )
            else:
                logger.error(
                    f"Error sending runtime abort signalr to UiPath MCP Server: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(
                f"Error sending runtime abort signal to UiPath MCP Server: {e}"
            )

    @property
    def sandboxed(self) -> bool:
        """
        Check if the runtime is sandboxed (created on-demand for a single agent execution).

        Returns:
            bool: True if this is an sandboxed runtime (has a job_id), False otherwise.
        """
        return self.context.job_id is not None

    @property
    def packaged(self) -> bool:
        """
        Check if the runtime is packaged (PackageType.MCPServer).

        Returns:
            bool: True if this is a packaged runtime (has a process), False otherwise.
        """
        process_key = None
        if self.context.trace_context is not None:
            process_key = self.context.trace_context.process_key

        return (
            process_key is not None
            and process_key != "00000000-0000-0000-0000-000000000000"
        )

    @property
    def slug(self) -> str:
        return self.context.server_slug or self._server.name  # type: ignore

    @property
    def server_type(self) -> UiPathServerType:
        """
        Determine the correct UiPathServerType for this runtime.

        Returns:
            UiPathServerType: The appropriate server type enum value based on the runtime configuration.
        """
        if self.packaged:
            # If it's a packaged runtime (has a process_key), it's a Coded server
            # Packaged runtimes are also sandboxed
            return UiPathServerType.Coded
        elif self.sandboxed:
            # If it's sandboxed but not packaged, it's a Command server
            return UiPathServerType.Command
        else:
            # If it's neither packaged nor sandboxed, it's a SelfHosted server
            return UiPathServerType.SelfHosted
