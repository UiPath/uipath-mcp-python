from unittest.mock import MagicMock, patch

import pytest
from uipath._utils.constants import ENV_FOLDER_PATH

from uipath_mcp._cli._runtime._exception import UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime


@pytest.fixture
def runtime():
    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        rt = UiPathMcpRuntime(
            server=MagicMock(),
            runtime_id="test-runtime-id",
            entrypoint="test-entrypoint",
        )
        rt._uipath = MagicMock()
        return rt


@pytest.mark.asyncio
async def test_folder_path_missing_raises_error(runtime):
    """Error when UIPATH_FOLDER_PATH is not set at all."""
    with (
        patch.object(runtime, "_validate_auth"),
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(UiPathMcpRuntimeError) as exc_info,
    ):
        await runtime._run_server()

    assert "Please set the UIPATH_FOLDER_PATH" in str(exc_info.value)


@pytest.mark.asyncio
async def test_folder_path_not_found_raises_error(runtime):
    """Error when UIPATH_FOLDER_PATH is set but the folder doesn't exist."""
    runtime._uipath.folders.retrieve_key.return_value = None

    with (
        patch.object(runtime, "_validate_auth"),
        patch.dict("os.environ", {ENV_FOLDER_PATH: "NonExistent/Folder"}, clear=True),
        pytest.raises(UiPathMcpRuntimeError) as exc_info,
    ):
        await runtime._run_server()

    error_msg = str(exc_info.value)
    assert "NonExistent/Folder" in error_msg
    assert "not found" in error_msg.lower()
