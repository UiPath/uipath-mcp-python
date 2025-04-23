import asyncio
import json
import uuid

from uipath._cli.middlewares import MiddlewareResult

from ._utils._config import McpConfig


async def mcp_init_middleware_async(entrypoint: str) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    config = McpConfig()
    if not config.exists:
        return MiddlewareResult(
            should_continue=True
        )  # Continue with normal flow if no mcp.json

    try:
        config.load_config()

        entrypoints = []

        for server in config.get_servers():

            if entrypoint and server.name != entrypoint:
                continue

            entrypoint_data = {
                "filePath": server.name,
                "uniqueId": str(uuid.uuid4()),
                "type": "mcpserver",
                "input": {},
                "output": {}
            }

            entrypoints.append(entrypoint_data)

        uipath_data = {
            "entryPoints": entrypoints
        }

        config_path = "uipath.json"

        with open(config_path, "w") as f:
            json.dump(uipath_data, f, indent=4)

        return MiddlewareResult(
            should_continue=False,
            info_message=f"Configuration file {config_path} created successfully.",
        )

    except Exception as e:
        return MiddlewareResult(
            should_continue=False,
            error_message=f"Error processing MCP server configuration: {str(e)}",
            should_include_stacktrace=True,
        )


def mcp_init_middleware(entrypoint: str) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    return asyncio.run(mcp_init_middleware_async(entrypoint))
