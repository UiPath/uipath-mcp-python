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
    during runtime registration and execution. Using these enum values instead of
    magic numbers improves code readability and maintainability.
    
    Attributes:
        UiPath (0): Standard UiPath server for Processes, Agents, and Activities
        External (1): External server types like npx, uvx
        Local (2): Local MCP server (PackageType.MCPServer)
        Hosted (3): Tunnel to externally hosted server
    """
    UiPath = 0  # Processes, Agents, Activities
    External = 1  # npx, uvx
    Local = 2  # PackageType.MCPServer
    Hosted = 3  # tunnel to externally hosted server
