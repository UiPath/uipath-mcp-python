import asyncio
import json
import uuid
from typing import Any, Callable, overload

from uipath._cli._utils._console import ConsoleLogger
from uipath._cli.middlewares import MiddlewareResult

from ._utils._config import McpConfig

console = ConsoleLogger()


async def mcp_init_middleware_async(
    entrypoint: str,
    options: dict[str, Any] | None = None,
    write_config: Callable[[Any], str] | None = None,
) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    options = options or {}

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
                "output": {},
            }

            entrypoints.append(entrypoint_data)

        uipath_data = {"entryPoints": entrypoints}

        if write_config:
            config_path = write_config(uipath_data)
        else:
            # Save the uipath.json file
            config_path = "uipath.json"
            with open(config_path, "w") as f:
                json.dump(uipath_data, f, indent=2)

        console.success(f"Created '{config_path}' file.")
        return MiddlewareResult(should_continue=False)

    except Exception as e:
        return MiddlewareResult(
            should_continue=False,
            error_message=f"Error processing MCP server configuration: {str(e)}",
            should_include_stacktrace=True,
        )


@overload
def mcp_init_middleware(entrypoint: str) -> MiddlewareResult: ...


@overload
def mcp_init_middleware(
    entrypoint: str,
    options: dict[str, Any],
    write_config: Callable[[Any], str],
) -> MiddlewareResult: ...


def mcp_init_middleware(
    entrypoint: str,
    options: dict[str, Any] | None = None,
    write_config: Callable[[Any], str] | None = None,
) -> MiddlewareResult:
    """Middleware to check for mcp.json and create uipath.json with schemas"""
    return asyncio.run(mcp_init_middleware_async(entrypoint, options, write_config))
