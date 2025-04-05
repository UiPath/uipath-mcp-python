import asyncio
import json

from uipath_sdk._cli.middlewares import MiddlewareResult


async def mcp_init_middleware_async(entrypoint: str) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    config = {
        "path": entrypoint,
        "exists": False,
    }
    if not config["exists"]:
        return MiddlewareResult(
            should_continue=True
        )  # Continue with normal flow if no mcp.json

    try:
        with open(config.path, "r") as f:
            mcp_config = json.load(f)
    except Exception as e:
        return MiddlewareResult(
            should_continue=False,
            error_message=f"Error processing MCP server configuration: {str(e)}",
            should_include_stacktrace=True,
        )


def mcp_init_middleware(entrypoint: str) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    return asyncio.run(mcp_init_middleware_async(entrypoint))
