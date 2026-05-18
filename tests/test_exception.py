"""Tests for UiPathMcpRuntimeError."""

from uipath.runtime.errors import UiPathErrorCategory

from uipath_mcp._cli._runtime._exception import McpErrorCode, UiPathMcpRuntimeError


def test_error_code_values():
    assert McpErrorCode.CONFIGURATION_ERROR.value == "CONFIGURATION_ERROR"
    assert McpErrorCode.SERVER_NOT_FOUND.value == "SERVER_NOT_FOUND"
    assert McpErrorCode.REGISTRATION_ERROR.value == "REGISTRATION_ERROR"
    assert McpErrorCode.INITIALIZATION_ERROR.value == "INITIALIZATION_ERROR"


def test_runtime_error_constructs_with_defaults():
    err = UiPathMcpRuntimeError(McpErrorCode.CONFIGURATION_ERROR, "title", "detail")
    assert isinstance(err, Exception)


def test_runtime_error_constructs_with_all_args():
    err = UiPathMcpRuntimeError(
        McpErrorCode.SERVER_NOT_FOUND,
        "title",
        "detail",
        UiPathErrorCategory.USER,
        404,
    )
    assert isinstance(err, Exception)
