from enum import Enum
from typing import Optional

from uipath._cli._runtime._contracts import UiPathRuntimeContext

from .._utils._config import McpConfig


class UiPathMcpRuntimeContext(UiPathRuntimeContext):
    """Context information passed throughout the runtime execution."""

    config: Optional[McpConfig] = None


class UiPathServerType(Enum):
    UiPath = 0  # Processes, Agents, Activities
    External = 1  # npx, uvx
    Local = 2  # PackageType.MCPServer
    Hosted = 3  # tunnel to externally hosted server
