import asyncio
import io
import json
import logging
import os
import sys
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from httpx import HTTPStatusError
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import JSONRPCResponse, ListToolsResult
from opentelemetry import trace
from pysignalr.client import SignalRClient
from pysignalr.messages import CompletionMessage
from uipath._utils.constants import (
    ENV_FOLDER_PATH,
    ENV_TENANT_ID,
)
from uipath.platform import UiPath
from uipath.platform.common import UiPathConfig
from uipath.runtime import (
    UiPathExecuteOptions,
    UiPathRuntimeEvent,
    UiPathRuntimeResult,
    UiPathRuntimeSchema,
    UiPathRuntimeStatus,
    UiPathStreamOptions,
)
from uipath.runtime.errors import (
    UiPathErrorCategory,
    UiPathErrorCode,
)

from .._utils._config import McpServer
from ._context import UiPathServerType
from ._exception import McpErrorCode, UiPathMcpRuntimeError
from ._session import BaseSessionServer, StdioSessionServer, StreamableHttpSessionServer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class UiPathMcpRuntime:
    """A runtime class for hosting UiPath MCP servers.

    Implements UiPathRuntimeProtocol for compatibility with the UiPath runtime framework.
    """

    def __init__(
        self,
        server: McpServer,
        runtime_id: str,
        entrypoint: str,
        folder_key: str | None = None,
        server_id: str | None = None,
        server_slug: str | None = None,
    ):
        """Initialize the MCP runtime.

        Args:
            server: The MCP server configuration.
            runtime_id: Unique identifier for this runtime instance. (Job Key)
            entrypoint: Entrypoint name (for schema generation).
            folder_key: UiPath folder key for registration.
            server_id: Server ID for registration.
            server_slug: Server slug for registration.
        """
        self._server: McpServer = server
        self._runtime_id = runtime_id or str(uuid.uuid4())
        self._entrypoint = entrypoint
        self._folder_key = folder_key
        self._server_id = server_id
        self._server_slug = server_slug

        self._signalr_client: SignalRClient | None = None
        self._session_servers: dict[str, BaseSessionServer] = {}
        self._session_output: str | None = None
        self._cancel_event = asyncio.Event()
        self._keep_alive_task: asyncio.Task[None] | None = None
        self._http_server_process: asyncio.subprocess.Process | None = None
        self._http_monitor_task: asyncio.Task[None] | None = None
        self._http_stderr_drain_task: asyncio.Task[None] | None = None
        self._http_server_stderr_lines: list[str] = []
        self._uipath = UiPath()
        self._cleanup_done = False

        # Context fields from UiPathConfig
        self._job_id = UiPathConfig.job_key
        self._tenant_id = os.environ.get(ENV_TENANT_ID)
        self._org_id = UiPathConfig.organization_id
        self._process_key = UiPathConfig.process_uuid

    def _validate_auth(self) -> None:
        """Validate authentication-related configuration.

        Raises:
            UiPathMcpRuntimeError: If any required authentication values are missing.
        """
        uipath_url = UiPathConfig.base_url
        if not uipath_url:
            raise UiPathMcpRuntimeError(
                McpErrorCode.CONFIGURATION_ERROR,
                "Missing UIPATH_URL environment variable",
                "Please run 'uipath auth'.",
                UiPathErrorCategory.USER,
            )

        if not (self._tenant_id and self._org_id):
            raise UiPathMcpRuntimeError(
                McpErrorCode.CONFIGURATION_ERROR,
                "Missing tenant ID or organization ID",
                "Please run 'uipath auth'.",
                UiPathErrorCategory.SYSTEM,
            )

    async def get_schema(self) -> UiPathRuntimeSchema:
        """Get schema for this MCP runtime.

        Returns:
            UiPathRuntimeSchema with MCP server information.
        """
        return UiPathRuntimeSchema(
            filePath=self._entrypoint,
            uniqueId=str(uuid.uuid4()),
            type="mcpserver",
            input={"type": "object", "properties": {}},
            output={"type": "object", "properties": {}},
            graph=None,  # No graph for MCP servers
        )

    async def execute(
        self,
        input: dict[str, Any] | None = None,
        options: UiPathExecuteOptions | None = None,
    ) -> UiPathRuntimeResult:
        """Start the MCP Server runtime.

        Args:
            input: Optional input dictionary (unused for MCP servers).
            options: Optional execution options.

        Returns:
            UiPathRuntimeResult with execution results.

        Raises:
            UiPathMcpRuntimeError: If execution fails.
        """
        return await self._run_server()

    async def stream(
        self,
        input: dict[str, Any] | None = None,
        options: UiPathStreamOptions | None = None,
    ) -> AsyncGenerator[UiPathRuntimeEvent, None]:
        """Stream execution for MCP server runtime.

        MCP servers don't emit intermediate events, so this just yields the final result.
        """
        result = await self._run_server()
        yield result

    async def _run_server(self) -> UiPathRuntimeResult:
        """Core server execution logic.

        Returns:
            UiPathRuntimeResult with execution results.

        Raises:
            UiPathMcpRuntimeError: If execution fails.
        """
        try:
            # Validate authentication configuration
            self._validate_auth()

            # Set up SignalR client
            uipath_url = UiPathConfig.base_url
            signalr_url = f"{uipath_url}/agenthub_/wsstunnel?slug={self.slug}&runtimeId={self._runtime_id}"

            if not self._folder_key:
                folder_path = os.environ.get(ENV_FOLDER_PATH)
                if not folder_path:
                    raise UiPathMcpRuntimeError(
                        McpErrorCode.REGISTRATION_ERROR,
                        "No UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable set.",
                        "Please set the UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable.",
                        UiPathErrorCategory.USER,
                    )
                self._folder_key = self._uipath.folders.retrieve_key(
                    folder_path=folder_path
                )
                if not self._folder_key:
                    raise UiPathMcpRuntimeError(
                        McpErrorCode.REGISTRATION_ERROR,
                        "Folder NOT FOUND. Invalid UIPATH_FOLDER_PATH environment variable.",
                        "Please set the UIPATH_FOLDER_PATH or UIPATH_FOLDER_KEY environment variable.",
                        UiPathErrorCategory.USER,
                    )

            logger.info(f"Folder key: {self._folder_key}")

            with tracer.start_as_current_span(self.slug) as root_span:
                root_span.set_attribute("runtime_id", self._runtime_id)
                root_span.set_attribute("command", str(self._server.command))
                root_span.set_attribute("args", json.dumps(self._server.args))
                root_span.set_attribute("span_type", "MCP Server")
                bearer_token = self._uipath._config.secret
                self._signalr_client = SignalRClient(
                    signalr_url,
                    headers={
                        "X-UiPath-Internal-TenantId": str(self._tenant_id),
                        "X-UiPath-Internal-AccountId": str(self._org_id),
                        "X-UIPATH-FolderKey": self._folder_key,
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

                # Start HTTP server process monitor if using streamable-http
                if self._server.is_streamable_http:
                    self._http_monitor_task = asyncio.create_task(
                        self._monitor_http_server_process()
                    )

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

                output_result: dict[str, Any] = {}
                if self._session_output:
                    output_result["content"] = self._session_output

                return UiPathRuntimeResult(
                    output=output_result,
                    status=UiPathRuntimeStatus.SUCCESSFUL,
                )

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            return UiPathRuntimeResult(
                output={},
                status=UiPathRuntimeStatus.SUCCESSFUL,
            )
        except Exception as e:
            if isinstance(e, UiPathMcpRuntimeError):
                raise
            detail = f"Error: {str(e)}"
            raise UiPathMcpRuntimeError(
                UiPathErrorCode.EXECUTION_ERROR,
                "MCP Runtime execution failed",
                detail,
                UiPathErrorCategory.USER,
            ) from e
        finally:
            await self._cleanup()

    async def dispose(self) -> None:
        """Cleanup runtime resources."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up all resources."""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        await self._on_runtime_abort()

        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass

        for session_id, session_server in list(self._session_servers.items()):
            try:
                await session_server.stop()
            except Exception as e:
                logger.error(f"Error cleaning up session server {session_id}: {str(e)}")

        # Stop the shared HTTP server process (streamable-http only)
        await self._stop_http_server_process()

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
            # Check if we have a session server for this session_id
            if session_id not in self._session_servers:
                session_server: BaseSessionServer
                if self._server.is_streamable_http:
                    session_server = StreamableHttpSessionServer(
                        self._server, self.slug, session_id
                    )
                else:
                    session_server = StdioSessionServer(
                        self._server, self.slug, session_id
                    )
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

    async def _start_http_server_process(self) -> None:
        """Spawn the streamable-http server process.

        The process is started once and shared across all sessions.
        """
        env_vars = self._server.env.copy()
        if self.server_type is UiPathServerType.Coded:
            for name, value in os.environ.items():
                if name not in env_vars:
                    env_vars[name] = value

        merged_env = {**os.environ, **env_vars} if env_vars else None
        self._http_server_stderr_lines = []
        self._http_server_process = await asyncio.create_subprocess_exec(
            self._server.command,
            *self._server.args,
            env=merged_env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._http_stderr_drain_task = asyncio.create_task(self._drain_http_stderr())
        logger.info(
            f"Started HTTP server process (PID: {self._http_server_process.pid}) "
            f"for {self._server.url}"
        )

    async def _drain_http_stderr(self) -> None:
        """Continuously read and log stderr from the HTTP server process.

        Accumulates output in _http_server_stderr_lines for error reporting.
        """
        if not self._http_server_process or not self._http_server_process.stderr:
            return
        try:
            async for line in self._http_server_process.stderr:
                decoded = line.decode("utf-8", errors="replace").rstrip()
                self._http_server_stderr_lines.append(decoded)
                logger.debug(f"HTTP server stderr: {decoded}")
        except asyncio.CancelledError:
            pass

    async def _wait_for_http_server_ready(
        self,
        max_retries: int = 30,
        retry_delay: float = 1.0,
    ) -> None:
        """Wait for the HTTP server to start accepting connections."""
        import httpx

        url = self._server.url
        if not url:
            raise ValueError("streamable-http transport requires url in config")

        for attempt in range(max_retries):
            # Check if process has crashed
            if (
                self._http_server_process
                and self._http_server_process.returncode is not None
            ):
                stderr_output = "\n".join(self._http_server_stderr_lines)
                raise UiPathMcpRuntimeError(
                    McpErrorCode.INITIALIZATION_ERROR,
                    "HTTP server process exited unexpectedly",
                    f"Exit code: {self._http_server_process.returncode}\n{stderr_output}",
                    UiPathErrorCategory.SYSTEM,
                )

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=2.0)
                    logger.info(
                        f"HTTP server is ready (status: {response.status_code})"
                    )
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout) as err:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"HTTP server not ready yet, retrying in {retry_delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    raise UiPathMcpRuntimeError(
                        McpErrorCode.INITIALIZATION_ERROR,
                        "HTTP server failed to start",
                        f"Server at {url} did not become ready after {max_retries} attempts",
                        UiPathErrorCategory.SYSTEM,
                    ) from err
            except httpx.HTTPStatusError:
                # Server responded with an error status code
                logger.info("HTTP server is ready (responded with error, but is up)")
                return

    async def _stop_http_server_process(self) -> None:
        """Stop the shared HTTP server process."""
        if self._http_monitor_task and not self._http_monitor_task.done():
            self._http_monitor_task.cancel()
            try:
                await self._http_monitor_task
            except asyncio.CancelledError:
                pass
            self._http_monitor_task = None

        if self._http_server_process:
            try:
                self._http_server_process.terminate()
                try:
                    await asyncio.wait_for(
                        self._http_server_process.wait(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    self._http_server_process.kill()
                    await self._http_server_process.wait()
            except ProcessLookupError:
                pass
            finally:
                logger.info("HTTP server process stopped")
                self._http_server_process = None

        if self._http_stderr_drain_task and not self._http_stderr_drain_task.done():
            self._http_stderr_drain_task.cancel()
            try:
                await self._http_stderr_drain_task
            except asyncio.CancelledError:
                pass
            self._http_stderr_drain_task = None

    async def _monitor_http_server_process(self) -> None:
        """Monitor the HTTP server process and handle unexpected exits."""
        if not self._http_server_process:
            return
        try:
            returncode = await self._http_server_process.wait()
            if not self._cancel_event.is_set():
                logger.error(
                    f"HTTP server process exited unexpectedly with code {returncode}"
                )
                # Stop all HTTP sessions, they will fail on next request anyway
                for session_id, session_server in list(self._session_servers.items()):
                    if isinstance(session_server, StreamableHttpSessionServer):
                        try:
                            await session_server.stop()
                        except Exception as e:
                            logger.error(
                                f"Error stopping session {session_id} after process crash: {e}"
                            )
                        self._session_servers.pop(session_id, None)
        except asyncio.CancelledError:
            pass

    async def _register(self) -> None:
        """Register the MCP server with UiPath."""

        initialization_successful = False
        tools_result: ListToolsResult | None = None
        server_stderr_output = ""
        env_vars = self._server.env

        # if server is Coded, include environment variables
        if self.server_type is UiPathServerType.Coded:
            for name, value in os.environ.items():
                # config env variables should have precedence over system ones
                if name not in env_vars:
                    env_vars[name] = value

        try:
            if self._server.is_streamable_http:
                # spawn process, wait for readiness, connect via HTTP
                await self._start_http_server_process()
                await self._wait_for_http_server_ready()

                from mcp.client.streamable_http import streamable_http_client

                if self._server.url is None:
                    raise UiPathMcpRuntimeError(
                        McpErrorCode.CONFIGURATION_ERROR,
                        "Missing URL for streamable-http server",
                        "Please specify a 'url' in the server configuration for streamable-http transport.",
                        UiPathErrorCategory.SYSTEM,
                    )
                async with streamable_http_client(self._server.url) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        logger.info("Initializing client session (streamable-http)...")
                        try:
                            await asyncio.wait_for(session.initialize(), timeout=30)
                            initialization_successful = True
                            tools_result = await session.list_tools()
                            logger.info(f"Discovered {len(tools_result.tools)} tool(s)")
                        except Exception as err:
                            logger.error(f"Initialization error: {err}")
                            server_stderr_output = "\n".join(
                                self._http_server_stderr_lines
                            )
                logger.info("Registration session closed (DELETE sent to server)")
            else:
                # spawn temporary process, discover tools, process dies with context
                server_params = StdioServerParameters(
                    command=self._server.command,
                    args=self._server.args,
                    env=env_vars,
                )

                with tempfile.TemporaryFile(mode="w+b") as stderr_temp_binary:
                    stderr_temp = io.TextIOWrapper(stderr_temp_binary, encoding="utf-8")
                    async with stdio_client(server_params, errlog=stderr_temp) as (
                        read,
                        write,
                    ):
                        async with ClientSession(read, write) as session:
                            logger.info("Initializing client session...")
                            try:
                                await asyncio.wait_for(session.initialize(), timeout=30)
                                initialization_successful = True
                                logger.info("Initialization successful")
                                tools_result = await session.list_tools()
                            except Exception as err:
                                logger.error(f"Initialization error: {err}")
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
            error_message = "The server process failed to initialize."
            if server_stderr_output:
                error_message += f"\nServer error output:\n{server_stderr_output}"
            raise UiPathMcpRuntimeError(
                McpErrorCode.INITIALIZATION_ERROR,
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
                    McpErrorCode.INITIALIZATION_ERROR,
                    "Server initialization failed",
                    "Failed to get tools list from server",
                    UiPathErrorCategory.DEPLOYMENT,
                )

            tools_list: list[dict[str, str | None]] = []
            client_info = {
                "server": {
                    "Name": self.slug,
                    "Slug": self.slug,
                    "Id": self._server_id,
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
                headers={"X-UIPATH-FolderKey": self._folder_key},
            )
            logger.info("Registered MCP Server type successfully")
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            if isinstance(e, HTTPStatusError):
                logger.error(
                    f"HTTP error details: {e.response.text} status code: {e.response.status_code}"
                )

            raise UiPathMcpRuntimeError(
                McpErrorCode.REGISTRATION_ERROR,
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
                        logger.info("Sending keep-alive ping...")
                        await self._signalr_client.send(
                            method="OnKeepAlive",
                            arguments=[],
                            on_invocation=on_keep_alive_response,  # type: ignore
                        )
                    else:
                        logger.error("SignalR client not initialized during keep-alive")
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
                headers={"X-UIPATH-FolderKey": self._folder_key},
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
        return self._job_id is not None

    @property
    def packaged(self) -> bool:
        """
        Check if the runtime is packaged (PackageType.MCPServer).

        Returns:
            bool: True if this is a packaged runtime (has a process), False otherwise.
        """
        return (
            self._process_key is not None
            and self._process_key != "00000000-0000-0000-0000-000000000000"
        )

    @property
    def slug(self) -> str:
        return self._server_slug or self._server.name

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
