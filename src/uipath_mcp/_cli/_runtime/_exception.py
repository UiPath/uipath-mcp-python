from enum import Enum
from typing import Optional, Union

from uipath._cli._runtime._contracts import (
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
        code: Union[McpErrorCode, UiPathErrorCode],
        title: str,
        detail: str,
        category: UiPathErrorCategory = UiPathErrorCategory.UNKNOWN,
        status: Optional[int] = None,
    ):
        super().__init__(
            code.value, title, detail, category, status, prefix="LlamaIndex"
        )
