"""Factory for creating MCP runtime instances."""

import json
import logging
import os
import uuid
from typing import Any

from uipath.runtime import (
    UiPathRuntimeContext,
    UiPathRuntimeFactorySettings,
    UiPathRuntimeProtocol,
)
from uipath.runtime.errors import UiPathErrorCategory
from uipath.runtime.storage import UiPathRuntimeStorageProtocol

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

    def _mcp_slug(self, entrypoint: str) -> str:
        """Loads the mcp slug from the uipath.config if available, otherwise it will use the entrypoint."""

        logger.info(f"Loading slug from config {self.context.config_path}")
        if os.path.exists(self.context.config_path):
            config: dict[str, Any] = {}
            with open(self.context.config_path, "r") as f:
                config = json.load(f)

            server_slug = (
                config.get("runtime", {})
                .get("fpsContext", {})
                .get("mcpServer.slug", None)
            )
            if server_slug is not None:
                logger.info(f"Server slug in config '{server_slug}'.")
                return server_slug

        logger.info(
            f"No server slug found in config, using entrypoint '{entrypoint}' as slug."
        )
        return entrypoint

    async def new_runtime(
        self, entrypoint: str, runtime_id: str, **kwargs: Any
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
        logger.info("Creating MCP runtime for entrypoint '%s'", entrypoint)
        logger.info(server)
        if not server:
            available = ", ".join(mcp_config.get_server_names())
            raise UiPathMcpRuntimeError(
                McpErrorCode.SERVER_NOT_FOUND,
                "MCP server not found",
                f"Server '{entrypoint}' not found. Available: {available}",
                UiPathErrorCategory.USER,
            )

        # Validate streamable-http configuration
        if server.is_streamable_http:
            if not server.url:
                raise UiPathMcpRuntimeError(
                    McpErrorCode.CONFIGURATION_ERROR,
                    "Invalid configuration",
                    f"Server '{entrypoint}' uses streamable-http transport but 'url' is not specified in mcp.json",
                    UiPathErrorCategory.USER,
                )
            if not server.command or server.command == "None":
                raise UiPathMcpRuntimeError(
                    McpErrorCode.CONFIGURATION_ERROR,
                    "Invalid configuration",
                    f"Server '{entrypoint}' uses streamable-http transport but 'command' is not specified in mcp.json",
                    UiPathErrorCategory.USER,
                )

        # Validate runtime_id is a valid UUID, generate new one if not
        try:
            uuid.UUID(runtime_id)
        except ValueError:
            new_id = str(uuid.uuid4())
            logger.warning(
                "Invalid runtime_id '%s' is not a valid UUID; generated '%s'",
                runtime_id,
                new_id,
            )
            runtime_id = new_id

        return UiPathMcpRuntime(
            server=server,
            runtime_id=runtime_id,
            entrypoint=entrypoint,
            folder_key=self.context.folder_key,
            server_id=self.context.mcp_server_id,
            server_slug=self._mcp_slug(entrypoint),
        )

    async def get_storage(self) -> UiPathRuntimeStorageProtocol | None:
        """Get factory storage.

        MCP servers are long-running processes and don't need
        cross-invocation state persistence.
        """
        return None

    async def get_settings(self) -> UiPathRuntimeFactorySettings | None:
        """Get factory settings."""
        return None

    async def dispose(self) -> None:
        """Cleanup factory resources."""
        self._mcp_config = None
