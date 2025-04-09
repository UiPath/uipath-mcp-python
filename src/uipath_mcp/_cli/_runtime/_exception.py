from typing import Optional

from uipath._cli._runtime._contracts import UiPathErrorCategory, UiPathRuntimeError


class UiPathMcpRuntimeError(UiPathRuntimeError):
    """Custom exception for MCP runtime errors with structured error information."""

    def __init__(
        self,
        code: str,
        title: str,
        detail: str,
        category: UiPathErrorCategory = UiPathErrorCategory.UNKNOWN,
        status: Optional[int] = None,
    ):
        super().__init__(code, title, detail, category, status, prefix="MCP")
