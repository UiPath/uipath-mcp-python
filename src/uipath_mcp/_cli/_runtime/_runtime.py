import asyncio
import logging
import sys
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from uipath import UiPath
from uipath._cli._runtime._contracts import (
    UiPathBaseRuntime,
    UiPathErrorCategory,
    UiPathRuntimeResult,
)

from .._utils._config import McpServer
from ._context import UiPathMcpRuntimeContext
from ._exception import UiPathMcpRuntimeError

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

    async def execute(self) -> Optional[UiPathRuntimeResult]:
        """
        Start the MCP server.

        Returns:
            Dictionary with execution results

        Raises:
            UiPathMcpRuntimeError: If execution fails
        """

        await self.validate()

        try:

            if self.server is None:
                return None

            server_params = StdioServerParameters(
                command=self.server.command,
                args=self.server.args,
                env=None,
            )

            print(f"Starting MCP server.. {self.server.command} {self.server.args}")
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(
                    read, write
                ) as session:

                    print("Connected to MCP server")
                    # Initialize the connection
                    await session.initialize()
                    print("MCP server initialized")
                    # List available prompts
                    #prompts = await session.list_prompts()

                    # Get a prompt
                    #prompt = await session.get_prompt(
                    #    "example-prompt", arguments={"arg1": "value"}
                    #)

                    # List available resources
                    #resources = await session.list_resources()

                    # List available tools
                    toolsResult = await session.list_tools()

                    print(toolsResult)

                    # Register with UiPath MCP Server
                    client_info = {
                        "server": {
                            "Name": self.server.name,
                            "Slug": self.server.name,
                            "Version": "1.0.0",
                            "Type": 1
                        },
                        "tools": []
                    }

                    for tool in toolsResult.tools:
                        tool_info = {
                            "Type": 1,
                            "Name": tool.name,
                            "ProcessType": "Tool",
                            "Description": tool.description,
                        }
                        client_info["tools"].append(tool_info)

                    print(client_info)
                    print("Registering client...")

                    uipath = UiPath()
                    sseUrl: str
                    try:
                        response = uipath.api_client.request(
                            "POST",
                            f"/mcp_/api/servers-with-tools/{self.server.name}",
                            json=client_info,
                        )
                        #data = response.json()
                        #sseUrl = data.get("url")
                        print("Registered client successfully")
                    except Exception as e:
                        raise UiPathMcpRuntimeError(
                            "NETWORK_ERROR",
                            "Failed to register with UiPath MCP Server",
                            str(e),
                            UiPathErrorCategory.SYSTEM,
                        ) from e

            return UiPathRuntimeResult()

        except Exception as e:
            if isinstance(e, UiPathMcpRuntimeError):
                raise

            detail = f"Error: {str(e)}"

            raise UiPathMcpRuntimeError(
                "EXECUTION_ERROR",
                "MCP Server execution failed",
                detail,
                UiPathErrorCategory.USER,
            ) from e

        finally:
            # Add a small delay to allow the server to shut down gracefully
            if sys.platform == 'win32':
                await asyncio.sleep(0.1)

    async def validate(self) -> None:
        """Validate runtime inputs."""
        """Load and validate the MCP server configuration ."""
        self.server = self.context.config.get_server(self.context.entrypoint)
        if not self.server:
            raise UiPathMcpRuntimeError(
                "SERVER_NOT_FOUND",
                "MCP server not found",
                f"Server '{self.context.entrypoint}' not found in configuration",
                UiPathErrorCategory.DEPLOYMENT,
            )

    async def cleanup(self):
        pass
