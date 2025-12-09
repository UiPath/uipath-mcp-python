"""UiPath MCP Runtime package."""

from uipath.runtime import (
    UiPathRuntimeContext,
    UiPathRuntimeFactoryProtocol,
    UiPathRuntimeFactoryRegistry,
)

from uipath_mcp._cli._runtime._factory import UiPathMcpRuntimeFactory
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime


def register_runtime_factory() -> None:
    """Register the MCP factory. Called automatically via entry point."""

    def create_factory(
        context: UiPathRuntimeContext | None = None,
    ) -> UiPathRuntimeFactoryProtocol:
        return UiPathMcpRuntimeFactory(
            context=context if context else UiPathRuntimeContext(),
        )

    UiPathRuntimeFactoryRegistry.register("mcp", create_factory, "mcp.json")


__all__ = [
    "register_runtime_factory",
    "UiPathMcpRuntimeFactory",
    "UiPathMcpRuntime",
]
