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
    A runtime class implementing the async context manager protocol.
    This allows using the class with 'async with' statements.
    """

    def __init__(self, context: UiPathMcpRuntimeContext):
        super().__init__(context)
        self.context: UiPathMcpRuntimeContext = context
        self.server: Optional[McpServer] = None
        self.signalr_client: Optional[SignalRClient] = None
        self.session_servers: Dict[str, SessionServer] = {}
        self._uipath = UiPath()

    async def execute(self) -> Optional[UiPathRuntimeResult]:
        """
        Start the runtime and connect to SignalR.

        Returns:
            Dictionary with execution results

        Raises:
            UiPathMcpRuntimeError: If execution fails
        """
        await self.validate()

        try:
            if self.server is None:
                return None

            # Set up SignalR client
            signalr_url = f"{os.environ.get('UIPATH_URL')}/mcp_/wsstunnel?slug={self.server.name}&sessionId={self.server.session_id}"

            self.cancel_event = asyncio.Event()

            with tracer.start_as_current_span(self.server.name) as root_span:
                root_span.set_attribute("session_id", self.server.session_id)
                root_span.set_attribute("command", self.server.command)
                root_span.set_attribute("args", self.server.args)
                root_span.set_attribute("span_type", "MCP Server")
                self.signalr_client = SignalRClient(
                    signalr_url,
                    headers={
                        "X-UiPath-Internal-TenantId": self.context.trace_context.tenant_id,
                        "X-UiPath-Internal-AccountId": self.context.trace_context.org_id,
                    },
                )
                self.signalr_client.on("MessageReceived", self.handle_signalr_message)
                self.signalr_client.on(
                    "SessionClosed", self.handle_signalr_session_closed
                )
                self.signalr_client.on_error(self.handle_signalr_error)
                self.signalr_client.on_open(self.handle_signalr_open)
                self.signalr_client.on_close(self.handle_signalr_close)

                # Register the server with UiPath MCP Server
                await self._register()

                # Keep the runtime alive
                # Start SignalR client and keep it running (this is a blocking call)
                logger.info("Starting websocket client...")

                run_task = asyncio.create_task(self.signalr_client.run())

                # Set up a task to wait for cancellation
                cancel_task = asyncio.create_task(self.cancel_event.wait())

                # Wait for either the run to complete or cancellation
                done, pending = await asyncio.wait(
                    [run_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()

                session_outputs = {}
                for session_id, session_server in self.session_servers.items():
                    try:
                        await session_server.cleanup()
                        stderr_output = session_server.get_server_stderr()
                        if stderr_output:
                            session_outputs[session_id] = stderr_output
                    except Exception as e:
                        logger.error(f"Error stopping session {session_id}: {str(e)}")

                output_result = {}
                if len(session_outputs) == 1:
                    # If there's only one session, use a single "output" key
                    first_session_id = next(iter(session_outputs))
                    output_result["output"] = session_outputs[first_session_id]
                elif session_outputs:
                    # If there are multiple sessions, use the sessionId as the key
                    output_result = session_outputs

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
        self.server = self.context.config.get_server(self.context.entrypoint)
        if not self.server:
            raise UiPathMcpRuntimeError(
                "SERVER_NOT_FOUND",
                "MCP server not found",
                f"Server '{self.context.entrypoint}' not found in configuration",
                UiPathErrorCategory.DEPLOYMENT,
            )

    async def handle_signalr_session_closed(self, args: list) -> None:
        """
        Handle session closed by server.
        """
        if len(args) < 1:
            logger.error(f"Received invalid SignalR message arguments: {args}")
            return

        session_id = args[0]

        logger.info(f"Received closed signal for session {session_id}")

        try:
            self.cancel_event.set()

        except Exception as e:
            logger.error(f"Error terminating session {session_id}: {str(e)}")

    async def handle_signalr_message(self, args: list) -> None:
        """
        Handle incoming SignalR messages.
        The SignalR client will call this with the arguments from the server.
        """
        if len(args) < 1:
            logger.error(f"Received invalid SignalR message arguments: {args}")
            return

        session_id = args[0]

        logger.info(f"Received websocket notification... {session_id}")

        try:
            # Check if we have a session server for this session_id
            if session_id not in self.session_servers:
                # Create and start a new session server
                session_server = SessionServer(self.server, session_id)
                self.session_servers[session_id] = session_server
                await session_server.start()

            # Get the session server for this session
            session_server = self.session_servers[session_id]

            # Forward the message to the session's MCP server
            await session_server.get_incoming_messages()

        except Exception as e:
            logger.error(
                f"Error handling websocket notification for session {session_id}: {str(e)}"
            )

    async def handle_signalr_error(self, error: Any) -> None:
        """Handle SignalR errors."""
        logger.error(f"SignalR error: {error}")

    async def handle_signalr_open(self) -> None:
        """Handle SignalR connection open event."""

        logger.info("Websocket connection established.")
        if self.server.session_id:
            try:
                session_server = SessionServer(self.server, self.server.session_id)
                await session_server.start()
                self.session_servers[self.server.session_id] = session_server
                await session_server.get_incoming_messages()
            except Exception as e:
                await self.dispose_session()
                logger.error(f"Error starting session server: {str(e)}")

    async def handle_signalr_close(self) -> None:
        """Handle SignalR connection close event."""
        logger.info("SignalR connection closed.")
        # Clean up all session servers when the connection closes
        await self.cleanup()

    async def _register(self) -> None:
        """Register the MCP server type with UiPath."""
        logger.info(f"Registering MCP server type: {self.server.name}")

        initialization_successful = False
        tools_result = None
        server_stderr_output = ""

        try:
            # Create a temporary session to get tools
            server_params = StdioServerParameters(
                command=self.server.command,
                args=self.server.args,
                env=self.server.env,
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
            await self.dispose_session()
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
                    "Name": self.server.name,
                    "Slug": self.server.name,
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
                f"mcp_/api/servers-with-tools/{self.server.name}",
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

    async def dispose_session(self) -> None:
        """Dispose of the session on the server."""
        try:
            response = self._uipath.api_client.request(
                "POST",
                f"mcp_/mcp/{self.server.name}/out/message?sessionId={self.server.session_id}",
                json=types.JSONRPCNotification(
                    jsonrpc="2.0",
                    method="notifications/cancelled",
                    params={"requestId": "*"},
                ).model_dump(),
            )
            if response.status_code == 202:
                logger.info(
                    f"Sent outgoing cancelled message to UiPath MCP Server: {self.server.session_id}"
                )
            else:
                logger.error(
                    f"Error sending outgoing cancelled message to to UiPath MCP Server: {response.status_code} - {response.text}"
                )

            response = self._uipath.api_client.request(
                "POST",
                f"mcp_/mcp/{self.server.name}/dispose?sessionId={self.server.session_id}",
            )
            if response.status_code == 202:
                logger.info(
                    f"Sent session dispose signalr to UiPath MCP Server: {self.server.session_id}"
                )
            else:
                logger.error(
                    f"Error sending session dispose signalr to UiPath MCP Server: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(
                f"Error sending session dispose signalr to UiPath MCP Server: {e}"
            )

    async def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up all resources")

        self.session_servers.clear()

        if self.signalr_client and hasattr(self.signalr_client, "_transport"):
            transport = self.signalr_client._transport
            if transport and hasattr(transport, "_ws") and transport._ws:
                try:
                    await transport._ws.close()
                except Exception as e:
                    logger.error(f"Error closing SignalR WebSocket: {str(e)}")

        # Add a small delay to allow the server to shut down gracefully
        if sys.platform == "win32":
            await asyncio.sleep(0.1)
