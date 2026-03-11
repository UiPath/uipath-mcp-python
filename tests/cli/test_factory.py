import json
from unittest.mock import MagicMock, patch

import pytest

from uipath_mcp._cli._runtime._exception import UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._factory import UiPathMcpRuntimeFactory

# Patch UiPath() constructor which requires auth env vars
_UIPATH_PATCH = patch("uipath_mcp._cli._runtime._runtime.UiPath")


@pytest.fixture
def mcp_json_single(tmp_path):
    """Create a temporary mcp.json with a single server."""
    config = {
        "servers": {
            "math-server": {
                "transport": "stdio",
                "command": "python",
                "args": ["server.py"],
            }
        }
    }
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps(config))
    return str(config_path)


@pytest.fixture
def factory(tmp_path):
    context = MagicMock()
    context.config_path = str(tmp_path / "uipath.json")
    context.folder_key = "test-folder-key"
    context.mcp_server_id = "test-server-id"
    return UiPathMcpRuntimeFactory(context=context)


@pytest.mark.asyncio
async def test_exact_match_works(factory, mcp_json_single):
    """Server found by exact name match."""
    factory._mcp_config = None
    with _UIPATH_PATCH, patch.object(factory, "_load_mcp_config") as mock_load:
        from uipath_mcp._cli._utils._config import McpConfig

        mock_load.return_value = McpConfig(mcp_json_single)
        runtime = await factory.new_runtime(
            "math-server", "00000000-0000-0000-0000-000000000001"
        )
    assert runtime._entrypoint == "math-server"


@pytest.mark.asyncio
async def test_wrong_name_raises(factory, mcp_json_single):
    """Wrong entrypoint raises SERVER_NOT_FOUND."""
    with patch.object(factory, "_load_mcp_config") as mock_load:
        from uipath_mcp._cli._utils._config import McpConfig

        mock_load.return_value = McpConfig(mcp_json_single)
        with pytest.raises(UiPathMcpRuntimeError) as exc_info:
            await factory.new_runtime("my-mcp2", "00000000-0000-0000-0000-000000000001")
    assert "not found" in str(exc_info.value).lower()
