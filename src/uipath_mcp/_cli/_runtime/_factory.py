"""Factory for creating MCP runtime instances."""

import json
import logging
import os
import uuid
from typing import Any

from uipath.runtime import (
    UiPathRuntimeContext,
    UiPathRuntimeProtocol,
)
from uipath.runtime.errors import UiPathErrorCategory

from uipath_mcp._cli._runtime._exception import McpErrorCode, UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime
from uipath_mcp._cli._utils._config import McpConfig

logger = logging.getLogger(__name__)


class UiPathMcpRuntimeFactory:
    """Factory for creating MCP runtimes from mcp.json configuration."""

    def __init__(
        self,
        context: UiPathRuntimeContext,
    ):
        """Initialize the factory.

        Args:
            context: UiPathRuntimeContext to use for runtime creation.
        """
        self.context = context
        self._mcp_config: McpConfig | None = None
        self._server_id: str | None = None
        self._server_slug: str | None = None

        # Load fps context from uipath.json if available
        self._load_fps_context()

    def _load_fps_context(self) -> None:
        """
        Load fps context from uipath.json for server registration.
        """
        config_path = self.context.config_path or "uipath.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config: dict[str, Any] = json.load(f)

                config_runtime = config.get("runtime", {})
                if "fpsContext" in config_runtime:
                    fps_context = config_runtime["fpsContext"]
                    self._server_id = fps_context.get("Id")
                    self._server_slug = fps_context.get("Slug")
            except Exception as e:
                logger.warning(f"Failed to load fps context: {e}")

    def _load_mcp_config(self) -> McpConfig:
        """Load mcp.json configuration."""
        if self._mcp_config is None:
            self._mcp_config = McpConfig()
        return self._mcp_config

    def discover_entrypoints(self) -> list[str]:
        """Discover all MCP server entrypoints.

        Returns:
            List of server names that can be used as entrypoints.
        """
        mcp_config = self._load_mcp_config()
        if not mcp_config.exists:
            return []
        return mcp_config.get_server_names()

    async def discover_runtimes(self) -> list[UiPathRuntimeProtocol]:
        """Discover runtime instances for all entrypoints.
        This is not running as part of a job, but is intended for the dev machine.

        Returns:
            List of UiPathMcpRuntime instances, one per entrypoint.
        """
        entrypoints = self.discover_entrypoints()
        runtimes: list[UiPathRuntimeProtocol] = []

        for entrypoint in entrypoints:
            runtime = await self.new_runtime(entrypoint, entrypoint)
            runtimes.append(runtime)

        return runtimes

    async def new_runtime(
        self, entrypoint: str, runtime_id: str
    ) -> UiPathRuntimeProtocol:
        """Create a new MCP runtime instance.

        Args:
            entrypoint: Server name from mcp.json.
            runtime_id: Unique identifier for the runtime instance.

        Returns:
            Configured UiPathMcpRuntime instance.

        Raises:
            UiPathMcpRuntimeError: If configuration is invalid or server not found.
        """
        mcp_config = self._load_mcp_config()

        if not mcp_config.exists:
            raise UiPathMcpRuntimeError(
                McpErrorCode.CONFIGURATION_ERROR,
                "Invalid configuration",
                "mcp.json not found",
                UiPathErrorCategory.DEPLOYMENT,
            )

        server = mcp_config.get_server(entrypoint)
        if not server:
            available = ", ".join(mcp_config.get_server_names())
            raise UiPathMcpRuntimeError(
                McpErrorCode.SERVER_NOT_FOUND,
                "MCP server not found",
                f"Server '{entrypoint}' not found. Available: {available}",
                UiPathErrorCategory.DEPLOYMENT,
            )

        # Validate runtime_id is a valid UUID, generate new one if not
        try:
            uuid.UUID(runtime_id)
        except ValueError:
            runtime_id = str(uuid.uuid4())

        return UiPathMcpRuntime(
            server=server,
            runtime_id=runtime_id,
            entrypoint=entrypoint,
            folder_key=self.context.folder_key,
            server_id=self._server_id,
            server_slug=self._server_slug,
        )

    async def dispose(self) -> None:
        """Cleanup factory resources."""
        self._mcp_config = None
