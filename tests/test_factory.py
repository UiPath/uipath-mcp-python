"""Tests for UiPathMcpRuntimeFactory."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uipath_mcp._cli._runtime import register_runtime_factory
from uipath_mcp._cli._runtime._exception import UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._factory import UiPathMcpRuntimeFactory


def _make_context(tmp_path: Path, config: dict[str, object] | None = None) -> MagicMock:
    ctx = MagicMock()
    cfg_path = tmp_path / "uipath.json"
    if config is not None:
        cfg_path.write_text(json.dumps(config))
    ctx.config_path = str(cfg_path)
    ctx.folder_key = "folder-key"
    ctx.mcp_server_id = "server-id"
    return ctx


@pytest.fixture
def factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    return UiPathMcpRuntimeFactory(context=_make_context(tmp_path))


@pytest.mark.asyncio
async def test_discover_entrypoints_empty_when_no_mcp_json(factory):
    assert factory.discover_entrypoints() == []


@pytest.mark.asyncio
async def test_discover_entrypoints_returns_names(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"a": {}, "b": {}}}))
    assert set(factory.discover_entrypoints()) == {"a", "b"}


@pytest.mark.asyncio
async def test_new_runtime_raises_when_no_config(factory):
    with pytest.raises(UiPathMcpRuntimeError):
        await factory.new_runtime("a", "id")


@pytest.mark.asyncio
async def test_new_runtime_raises_when_server_missing(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"a": {}, "b": {}}}))
    factory._mcp_config = None
    with pytest.raises(UiPathMcpRuntimeError):
        await factory.new_runtime("missing", "id")


@pytest.mark.asyncio
async def test_new_runtime_streamable_http_requires_url(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "a": {
                        "transport": "streamable-http",
                        "command": "node",
                    }
                }
            }
        )
    )
    factory._mcp_config = None
    with pytest.raises(UiPathMcpRuntimeError, match="url"):
        await factory.new_runtime("a", "id")


@pytest.mark.asyncio
async def test_new_runtime_streamable_http_requires_command(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "a": {
                        "transport": "streamable-http",
                        "url": "https://x",
                    }
                }
            }
        )
    )
    factory._mcp_config = None
    with pytest.raises(UiPathMcpRuntimeError, match="command"):
        await factory.new_runtime("a", "id")


@pytest.mark.asyncio
async def test_new_runtime_returns_runtime(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"a": {"command": "x"}}}))
    factory._mcp_config = None
    with patch("uipath_mcp._cli._runtime._factory.UiPathMcpRuntime") as rt_cls:
        rt_cls.return_value = "RUNTIME"
        result = await factory.new_runtime("a", "00000000-0000-0000-0000-000000000000")
    assert result == "RUNTIME"
    rt_cls.assert_called_once()


@pytest.mark.asyncio
async def test_new_runtime_invalid_uuid_is_regenerated(tmp_path: Path, factory):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"a": {"command": "x"}}}))
    factory._mcp_config = None
    with patch("uipath_mcp._cli._runtime._factory.UiPathMcpRuntime") as rt_cls:
        await factory.new_runtime("a", "not-a-uuid")
    kwargs = rt_cls.call_args.kwargs
    # generated uuid should differ from the bad input
    assert kwargs["runtime_id"] != "not-a-uuid"


@pytest.mark.asyncio
async def test_get_storage_returns_none(factory):
    assert await factory.get_storage() is None


@pytest.mark.asyncio
async def test_get_settings_returns_none(factory):
    assert await factory.get_settings() is None


@pytest.mark.asyncio
async def test_dispose_clears_config(factory):
    factory._mcp_config = MagicMock()
    await factory.dispose()
    assert factory._mcp_config is None


def test_mcp_slug_from_config(tmp_path: Path):
    ctx = _make_context(
        tmp_path,
        {"runtime": {"fpsContext": {"mcpServer.slug": "from-config"}}},
    )
    factory = UiPathMcpRuntimeFactory(context=ctx)
    assert factory._mcp_slug("entry") == "from-config"


def test_mcp_slug_fallback_to_entrypoint(tmp_path: Path):
    ctx = _make_context(tmp_path, {})
    factory = UiPathMcpRuntimeFactory(context=ctx)
    assert factory._mcp_slug("entry") == "entry"


def test_mcp_slug_no_config_file(tmp_path: Path):
    ctx = MagicMock()
    ctx.config_path = str(tmp_path / "nope.json")
    factory = UiPathMcpRuntimeFactory(context=ctx)
    assert factory._mcp_slug("entry") == "entry"


def test_register_runtime_factory_invokes_registry():
    with patch("uipath_mcp._cli._runtime.UiPathRuntimeFactoryRegistry") as reg:
        register_runtime_factory()
    reg.register.assert_called_once()
    args, _ = reg.register.call_args
    assert args[0] == "mcp"
    assert args[2] == "mcp.json"
    # invoke the factory builder with and without a context
    create_factory = args[1]
    with patch("uipath_mcp._cli._runtime.UiPathMcpRuntimeFactory") as fc:
        create_factory(None)
        create_factory(MagicMock())
    assert fc.call_count == 2
