import asyncio
import logging
import os
import sys
import tempfile
from typing import Any, Dict, Optional

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from opentelemetry import trace
from pysignalr.client import SignalRClient
from uipath import UiPath
from uipath._cli._runtime._contracts import (
    UiPathBaseRuntime,
    UiPathErrorCategory,
    UiPathRuntimeResult,
)
from uipath.tracing import wait_for_tracers

from .._utils._config import McpServer
from ._context import UiPathMcpRuntimeContext
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
        self._signalr_client: Optional[SignalRClient] = None
        self._session_servers: Dict[str, SessionServer] = {}
        self._session_outputs: Dict[str, str] = {}
        self._cancel_event = asyncio.Event()
        self._uipath = UiPath()

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

            # Set up SignalR client
            signalr_url = f"{os.environ.get('UIPATH_URL')}/mcp_/wsstunnel?slug={self._server.name}&sessionId={self._server.session_id}"

            with tracer.start_as_current_span(self._server.name) as root_span:
                root_span.set_attribute("session_id", self._server.session_id)
                root_span.set_attribute("command", self._server.command)
                root_span.set_attribute("args", self._server.args)
                root_span.set_attribute("span_type", "MCP Server")
                self._signalr_client = SignalRClient(
                    signalr_url,
                    headers={
                        "X-UiPath-Internal-TenantId": self.context.trace_context.tenant_id,
                        "X-UiPath-Internal-AccountId": self.context.trace_context.org_id,
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

                # Set up a task to wait for cancellation
                cancel_task = asyncio.create_task(self._cancel_event.wait())

                # Keep the runtime alive
                # Wait for either the run to complete or cancellation
                done, pending = await asyncio.wait(
                    [run_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()

                output_result = {}
                if len(self._session_outputs) == 1:
                    # If there's only one session, use a single "content" key
                    single_session_id = next(iter(self._session_outputs))
                    output_result["content"] = self._session_outputs[single_session_id]
                elif self._session_outputs:
                    # If there are multiple sessions, use the session_id as the key
                    output_result = self._session_outputs

                self.context.result = UiPathRuntimeResult(output=output_result)

                return self.context.result

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
            wait_for_tracers()

    async def validate(self) -> None:
        """Validate runtime inputs and load MCP server configuration."""
        self._server = self.context.config.get_server(self.context.entrypoint)
        if not self._server:
            raise UiPathMcpRuntimeError(
                "SERVER_NOT_FOUND",
                "MCP server not found",
                f"Server '{self.context.entrypoint}' not found in configuration",
                UiPathErrorCategory.DEPLOYMENT,
            )

    async def cleanup(self) -> None:
        """Clean up all resources."""
        if self._signalr_client and hasattr(self._signalr_client, "_transport"):
            transport = self._signalr_client._transport
            if transport and hasattr(transport, "_ws") and transport._ws:
                try:
                    await transport._ws.close()
                except Exception as e:
                    logger.error(f"Error closing SignalR WebSocket: {str(e)}")

        # Add a small delay to allow the server to shut down gracefully
        if sys.platform == "win32":
            await asyncio.sleep(0.1)

    async def _handle_signalr_session_closed(self, args: list) -> None:
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
                    self._session_outputs[session_id] = session_server.output

            # If this is an ephemeral runtime for a specific session, cancel the execution
            if self._is_ephemeral():
                self._cancel_event.set()

        except Exception as e:
            logger.error(f"Error terminating session {session_id}: {str(e)}")

    async def _handle_signalr_message(self, args: list) -> None:
        """
        Handle incoming SignalR messages.
        """
        if len(args) < 1:
            logger.error(f"Received invalid websocket message arguments: {args}")
            return

        session_id = args[0]

        logger.info(f"Received websocket notification... {session_id}")

        try:
            # Check if we have a session server for this session_id
            if session_id not in self._session_servers:
                # Create and start a new session server
                session_server = SessionServer(self._server, session_id)
                self._session_servers[session_id] = session_server
                await session_server.start()

            # Get the session server for this session
            session_server = self._session_servers[session_id]

            # Forward the message to the session's MCP server
            await session_server.on_message_received()

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
        # If this is an ephemeral runtime we need to start the local MCP session
        if self._is_ephemeral():
            try:
                # Check if we have a session server for this session_id
                # Websocket reconnection may occur, so we need to check if the session server already exists
                if self._server.session_id not in self._session_servers:
                    # Create and start a new session server
                    session_server = SessionServer(self._server, self._server.session_id)
                    self._session_servers[self._server.session_id] = session_server
                    await session_server.start()
                # Get the session server for this session
                session_server = self._session_servers[self._server.session_id]
                # Check for existing messages from the connected client
                await session_server.on_message_received()
            except Exception as e:
                await self._on_initialization_failure()
                logger.error(f"Error starting session server: {str(e)}")

    async def _handle_signalr_close(self) -> None:
        """Handle SignalR connection close event."""
        logger.info("Websocket connection closed.")

    async def _register(self) -> None:
        """Register the MCP server with UiPath."""
        logger.info(f"Registering MCP server: {self._server.name}")

        initialization_successful = False
        tools_result = None
        server_stderr_output = ""

        try:
            # Create a temporary session to get tools
            server_params = StdioServerParameters(
                command=self._server.command,
                args=self._server.args,
                env=self._server.env,
            )

            # Start a temporary stdio client to get tools
            # Use a temporary file to capture stderr
            with tempfile.TemporaryFile(mode="w+") as stderr_temp:
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
                            logger.info(tools_result)
                        except asyncio.TimeoutError:
                            logger.error("Initialization timed out")
                            # Capture stderr output here, after the timeout
                            stderr_temp.seek(0)
                            server_stderr_output = stderr_temp.read()
                            # We'll handle this after exiting the context managers

                        # We don't continue with registration here - we'll do it after the context managers

        except BaseException as e:
            logger.error(f"Error during server initialization: {e}")

        # Now that we're outside the context managers, check if initialization succeeded
        if not initialization_successful:
            await self._on_initialization_failure()
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
        try:
            client_info = {
                "server": {
                    "Name": self._server.name,
                    "Slug": self._server.name,
                    "Version": "1.0.0",
                    "Type": 1,
                },
                "tools": [],
            }

            for tool in tools_result.tools:
                tool_info = {
                    "Type": 1,
                    "Name": tool.name,
                    "ProcessType": "Tool",
                    "Description": tool.description,
                }
                client_info["tools"].append(tool_info)

            # Register with UiPath MCP Server
            self._uipath.api_client.request(
                "POST",
                f"mcp_/api/servers-with-tools/{self._server.name}",
                json=client_info,
            )
            logger.info("Registered MCP Server type successfully")
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            raise UiPathMcpRuntimeError(
                "REGISTRATION_ERROR",
                "Failed to register MCP Server",
                str(e),
                UiPathErrorCategory.SYSTEM,
            ) from e

    async def _on_initialization_failure(self) -> None:
        """
        Sends a dummy initialization failure message to abort the already connected client.
        Ephemeral runtimes are triggered by new client connections.
        """

        if self._is_ephemeral() is False:
            return

        try:
            response = self._uipath.api_client.request(
                "POST",
                f"mcp_/mcp/{self._server.name}/out/message?sessionId={self._server.session_id}",
                json=types.JSONRPCResponse(
                    jsonrpc="2.0",
                    id=0,
                    result={
                        "protocolVersion": "initiliaze-failure",
                        "capabilities": {},
                        "serverInfo": {"name": self._server.name, "version": "1.0"},
                    },
                ).model_dump(),
            )
            if response.status_code == 202:
                logger.info(
                    f"Sent outgoing session dispose message to UiPath MCP Server: {self._server.session_id}"
                )
            else:
                logger.error(
                    f"Error sending session dispose message to UiPath MCP Server: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(
                f"Error sending session dispose signal to UiPath MCP Server: {e}"
            )

    def _is_ephemeral(self) -> bool:
        """
        Check if the runtime is ephemeral (created on-demand for a single agent execution).

        Returns:
            bool: True if this is an ephemeral runtime (has a session_id), False otherwise.
        """
        return self._server.session_id is not None
