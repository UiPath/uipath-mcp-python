from enum import Enum

from uipath.runtime.errors import (
    UiPathBaseRuntimeError,
    UiPathErrorCategory,
    UiPathErrorCode,
)


class McpErrorCode(Enum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    SERVER_NOT_FOUND = "SERVER_NOT_FOUND"
    REGISTRATION_ERROR = "REGISTRATION_ERROR"
    INITIALIZATION_ERROR = "INITIALIZATION_ERROR"


class UiPathMcpRuntimeError(UiPathBaseRuntimeError):
    """Custom exception for MCP runtime errors with structured error information."""

    def __init__(
        self,
        code: McpErrorCode | UiPathErrorCode,
        title: str,
        detail: str,
        category: UiPathErrorCategory = UiPathErrorCategory.UNKNOWN,
        status: int | None = None,
    ):
        super().__init__(
            code.value, title, detail, category, status, prefix="UiPathMCP"
        )
