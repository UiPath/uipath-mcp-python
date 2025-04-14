import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pysignalr.client import SignalRClient
from uipath import UiPath
from uipath._cli._runtime._contracts import (
    UiPathBaseRuntime,
    UiPathErrorCategory,
    UiPathRuntimeResult,
)

from .._utils._config import McpServer
from ._context import UiPathMcpRuntimeContext
from ._exception import UiPathMcpRuntimeError
from ._session import SessionServer

logger = logging.getLogger(__name__)


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
            signalr_url = (
                f"{os.environ.get('UIPATH_URL')}/mcp_/wsstunnel?slug={self.server.name}&jobKey={self.context.job_id}"
            )

            self.cancel_event = asyncio.Event()

            self.signalr_client = SignalRClient(signalr_url)
            self.signalr_client.on("MessageReceived", self.handle_signalr_message)
            self.signalr_client.on("SessionClosed", self.handle_signalr_session_closed)
            self.signalr_client.on_error(self.handle_signalr_error)
            self.signalr_client.on_open(self.handle_signalr_open)
            self.signalr_client.on_close(self.handle_signalr_close)

            # Register the server with UiPath MCP Server
            await self._register()

            # Keep the runtime alive
            # Start SignalR client and keep it running (this is a blocking call)
            logger.info("Starting SignalR client...")

            run_task = asyncio.create_task(self.signalr_client.run())

            # Set up a task to wait for cancellation
            cancel_task = asyncio.create_task(self.cancel_event.wait())

            # Wait for either the run to complete or cancellation
            done, pending = await asyncio.wait(
                [run_task, cancel_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

            return UiPathRuntimeResult()

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
            logger.error(
                f"Error terminating session {session_id}: {str(e)}"
            )

    async def handle_signalr_message(self, args: list) -> None:
        """
        Handle incoming SignalR messages.
        The SignalR client will call this with the arguments from the server.
        """
        if len(args) < 2:
            logger.error(f"Received invalid SignalR message arguments: {args}")
            return

        session_id = args[0]
        message = args[1]

        logger.info(f"Received message for session {session_id}: {message}")

        try:
            # Check if we have a session server for this session_id
            if session_id not in self.session_servers:
                # Create and start a new session server
                session_server = SessionServer(self.server, session_id)
                self.session_servers[session_id] = session_server
                await session_server.start(self.signalr_client)

            # Get the session server for this session
            session_server = self.session_servers[session_id]

            # Forward the message to the session's MCP server
            await session_server.send_message(message)

        except Exception as e:
            logger.error(
                f"Error handling SignalR message for session {session_id}: {str(e)}"
            )

    async def handle_signalr_error(self, error: Any) -> None:
        """Handle SignalR errors."""
        logger.error(f"SignalR error: {error}")

    async def handle_signalr_open(self) -> None:
        """Handle SignalR connection open event."""
        logger.info("SignalR connection established")
        uipath = UiPath()
        response = uipath.api_client.request(
            "GET",
            f"mcp_/mcp/{self.server.name}/message?jobKey={self.context.job_id}"
        )
        if response.status_code == 200:
            data = response.json()
            session_id = data["sessionId"]
            message = data["message"]
            logger.info(f"Received message from UiPath MCP: {message}")
            if session_id not in self.session_servers:
                # Create and start a new session server
                session_server = SessionServer(self.server, session_id)
                self.session_servers[session_id] = session_server
                await session_server.start(self.signalr_client)

            # Get the session server for this session
            session_server = self.session_servers[session_id]

            # Forward the message to the session's MCP server
            await session_server.send_message(message)

    async def handle_signalr_close(self) -> None:
        """Handle SignalR connection close event."""
        logger.info("SignalR connection closed")

        # Clean up all session servers when the connection closes
        await self.cleanup()

    async def _register(self) -> None:
        """Register the MCP server type with UiPath."""
        logger.info(f"Registering MCP server type: {self.server.name}")

        try:
            # Create a temporary session to get tools
            server_params = StdioServerParameters(
                command=self.server.command,
                args=self.server.args,
                env=None,
            )

            # Start a temporary stdio client to get tools
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    print(tools_result)
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
                    uipath = UiPath()
                    uipath.api_client.request(
                        "POST",
                        f"mcp_/api/servers-with-tools/{self.server.name}",
                        json=client_info,
                    )
                    logger.info("Registered MCP Server type successfully")

        except Exception as e:
            raise UiPathMcpRuntimeError(
                "NETWORK_ERROR",
                "Failed to register with UiPath MCP Server",
                str(e),
                UiPathErrorCategory.SYSTEM,
            ) from e

    async def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up all resources")

        # Clean up all session servers
        for session_id, session_server in list(self.session_servers.items()):
            try:
                await session_server.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {str(e)}")

        self.session_servers.clear()

        if self.signalr_client:
            # Close the SignalR connection
            await self.signalr_client._transport._ws.close()

        # Add a small delay to allow the server to shut down gracefully
        if sys.platform == "win32":
            await asyncio.sleep(0.1)
