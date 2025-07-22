from enum import Enum
from typing import Optional

from uipath._cli._runtime._contracts import UiPathRuntimeContext

from .._utils._config import McpConfig


class UiPathMcpRuntimeContext(UiPathRuntimeContext):
    """Context information passed throughout the runtime execution."""

    config: Optional[McpConfig] = None
    folder_key: Optional[str] = None
    server_id: Optional[str] = None
    server_slug: Optional[str] = None

    @classmethod
    def from_config(cls, config_path=None):
        """Load configuration from uipath.json file with MCP-specific handling."""
        # Use the parent's implementation
        instance = super().from_config(config_path)

        # Convert to our type (since parent returns UiPathRuntimeContext)
        mcp_instance = cls(**instance.model_dump())

        # Add AgentHub-specific configuration handling
        import json
        import os

        path = config_path or "uipath.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                config = json.load(f)

            config_runtime = config.get("runtime", {})
            if "fpsContext" in config_runtime:
                fps_context = config_runtime["fpsContext"]
                mcp_instance.server_id = fps_context.get("Id")
                mcp_instance.server_slug = fps_context.get("Slug")
        return mcp_instance


class UiPathServerType(Enum):
    """Defines the different types of UiPath servers used in the MCP ecosystem.

    This enum is used to identify and configure the behavior of different server types
    during runtime registration and execution.

    Attributes:
        UiPath (0): Standard UiPath server for Processes, Agents, and Activities
        Command (1): Command server types like npx, uvx
        Coded (2): Coded MCP server (PackageType.MCPServer)
        SelfHosted (3): Tunnel to externally hosted server
    """

    UiPath = 0  # Processes, Agents, Activities
    Command = 1  # npx, uvx
    Coded = 2  # PackageType.MCPServer
    SelfHosted = 3  # tunnel to externally hosted server

    @classmethod
    def from_string(cls, name: str) -> "UiPathServerType":
        """Get enum value from string name."""
        try:
            return cls[name]
        except KeyError as e:
            raise ValueError(f"Unknown server type: {name}") from e

    @classmethod
    def get_description(cls, server_type: "UiPathServerType") -> str:
        """Get description for a server type."""
        descriptions = {
            cls.UiPath: "Standard UiPath server for Processes, Agents, and Activities",
            cls.Command: "Command server types like npx, uvx",
            cls.Coded: "Coded MCP server (PackageType.MCPServer)",
            cls.SelfHosted: "Tunnel to externally hosted server",
        }
        return descriptions.get(server_type, "Unknown server type")
