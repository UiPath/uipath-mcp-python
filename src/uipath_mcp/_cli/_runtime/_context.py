from enum import Enum
from typing import Optional

from uipath._cli._runtime._contracts import UiPathRuntimeContext

from .._utils._config import McpConfig


class UiPathMcpRuntimeContext(UiPathRuntimeContext):
    """Context information passed throughout the runtime execution."""

    config: Optional[McpConfig] = None


class UiPathServerType(Enum):
    """Defines the different types of UiPath servers used in the MCP ecosystem.

    This enum is used to identify and configure the behavior of different server types
    during runtime registration and execution.

    Attributes:
        UiPath (0): Standard UiPath server for Processes, Agents, and Activities
        External (1): External server types like npx, uvx
        Local (2): Local MCP server (PackageType.MCPServer)
        Hosted (3): Tunnel to externally hosted server
    """

    UiPath = 0  # type: int # Processes, Agents, Activities
    External = 1  # type: int # npx, uvx
    Local = 2  # type: int # PackageType.MCPServer
    Hosted = 3  # type: int # tunnel to externally hosted server

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
            cls.External: "External server types like npx, uvx",
            cls.Local: "Local MCP server (PackageType.MCPServer)",
            cls.Hosted: "Tunnel to externally hosted server",
        }
        return descriptions.get(server_type, "Unknown server type")
