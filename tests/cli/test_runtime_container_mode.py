"""Tests for container-mode lifetime override via UIPATH_MCP_CONTAINER_RUNTIME."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from uipath_mcp._cli._runtime._context import UiPathServerType
from uipath_mcp._cli._runtime._factory import UiPathMcpRuntimeFactory
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime


def _make_runtime(**extra) -> UiPathMcpRuntime:
    server = MagicMock(
        name="server",
        is_streamable_http=False,
        args=[],
        command="cmd",
        env={},
        url=None,
    )
    server.name = "svc"
    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        rt = UiPathMcpRuntime(
            server=server,
            runtime_id="rid",
            entrypoint="ep",
            **extra,
        )
        rt._uipath = MagicMock()
        return rt


def test_container_runtime_is_not_sandboxed(monkeypatch):
    """When UIPATH_MCP_CONTAINER_RUNTIME is set, sandboxed must be False even with a job key."""
    monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", "true")
    monkeypatch.setenv("UIPATH_JOB_KEY", "00000000-0000-0000-0000-000000000001")
    with patch("uipath_mcp._cli._runtime._runtime.UiPathConfig") as mock_cfg:
        mock_cfg.job_key = "00000000-0000-0000-0000-000000000001"
        mock_cfg.organization_id = "org-1"
        mock_cfg.process_uuid = None
        rt = _make_runtime()
    # _job_id should be set from mock_cfg.job_key
    assert rt._job_id == "00000000-0000-0000-0000-000000000001"
    # But sandboxed must be False because UIPATH_MCP_CONTAINER_RUNTIME is set
    assert rt.sandboxed is False


def test_container_runtime_false_value_does_not_override(monkeypatch):
    """When UIPATH_MCP_CONTAINER_RUNTIME is not set, sandboxed follows job_id presence."""
    monkeypatch.delenv("UIPATH_MCP_CONTAINER_RUNTIME", raising=False)
    rt = _make_runtime()
    rt._job_id = "some-job-id"
    assert rt.sandboxed is True

    rt._job_id = None
    assert rt.sandboxed is False


def test_container_runtime_various_truthy_values(monkeypatch):
    """Accept '1', 'true', 'yes' case-insensitively as truthy values."""
    for value in ("1", "true", "True", "TRUE", "yes", "YES", "Yes"):
        monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", value)
        rt = _make_runtime()
        rt._job_id = "some-job-id"
        assert rt.sandboxed is False, (
            f"Expected sandboxed=False for env var value={value!r}"
        )


def test_container_runtime_non_truthy_does_not_override(monkeypatch):
    """Non-truthy values for UIPATH_MCP_CONTAINER_RUNTIME do not override sandboxed."""
    for value in ("0", "false", "no", ""):
        monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", value)
        rt = _make_runtime()
        rt._job_id = "some-job-id"
        assert rt.sandboxed is True, (
            f"Expected sandboxed=True for env var value={value!r}"
        )


# ---------------------------------------------------------------------------
# server_type: container mode must declare Coded
# ---------------------------------------------------------------------------


def test_server_type_coded_in_container_mode(monkeypatch):
    """In container mode, server_type must be Coded regardless of job/process keys."""
    monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", "true")
    rt = _make_runtime()
    rt._job_id = None
    rt._process_key = None
    assert rt.server_type is UiPathServerType.Coded


def test_server_type_coded_in_container_mode_various_values(monkeypatch):
    """All truthy UIPATH_MCP_CONTAINER_RUNTIME values yield Coded server type."""
    for value in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", value)
        rt = _make_runtime()
        rt._job_id = None
        rt._process_key = None
        assert rt.server_type is UiPathServerType.Coded, (
            f"Expected Coded for env var value={value!r}"
        )


def test_server_type_selfhosted_without_container_mode(monkeypatch):
    """Without container mode, non-packaged non-sandboxed runtime is SelfHosted."""
    monkeypatch.delenv("UIPATH_MCP_CONTAINER_RUNTIME", raising=False)
    rt = _make_runtime()
    rt._job_id = None
    rt._process_key = None
    assert rt.server_type is UiPathServerType.SelfHosted


def test_server_type_packaged_overrides_container_mode(monkeypatch):
    """Packaged runtimes are always Coded, even without container mode."""
    monkeypatch.delenv("UIPATH_MCP_CONTAINER_RUNTIME", raising=False)
    rt = _make_runtime()
    rt._process_key = "11111111-2222-3333-4444-555555555555"
    assert rt.server_type is UiPathServerType.Coded


# ---------------------------------------------------------------------------
# runtime_id: container mode must honour UIPATH_RUNTIME_ID
# ---------------------------------------------------------------------------

_VALID_GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_GUID2 = "11111111-2222-3333-4444-555555555555"


def _make_factory_context(**overrides) -> MagicMock:
    ctx = MagicMock()
    ctx.config_path = "/nonexistent/uipath.json"
    ctx.folder_key = "fk"
    ctx.mcp_server_id = "sid"
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _make_mcp_server(name: str = "svc") -> MagicMock:
    srv = MagicMock(is_streamable_http=False, url=None, command="cmd")
    srv.name = name
    return srv


@pytest.mark.asyncio
async def test_factory_container_uses_env_runtime_id(monkeypatch):
    """In container mode, factory must use UIPATH_RUNTIME_ID when it is a valid GUID."""
    monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", "true")
    monkeypatch.setenv("UIPATH_RUNTIME_ID", _VALID_GUID)

    ctx = _make_factory_context()
    factory = UiPathMcpRuntimeFactory(context=ctx)
    factory._mcp_config = MagicMock(exists=True)
    factory._mcp_config.get_server.return_value = _make_mcp_server()

    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        runtime = await factory.new_runtime("svc", "default")

    assert runtime._runtime_id == _VALID_GUID


@pytest.mark.asyncio
async def test_factory_container_ignores_invalid_env_runtime_id(monkeypatch):
    """In container mode, if UIPATH_RUNTIME_ID is not a valid UUID, fall back to generate."""
    monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", "true")
    monkeypatch.setenv("UIPATH_RUNTIME_ID", "not-a-guid")

    ctx = _make_factory_context()
    factory = UiPathMcpRuntimeFactory(context=ctx)
    factory._mcp_config = MagicMock(exists=True)
    factory._mcp_config.get_server.return_value = _make_mcp_server()

    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        runtime = await factory.new_runtime("svc", "default")

    # Should have fallen back to a freshly generated UUID (not "default", not "not-a-guid")
    assert runtime._runtime_id != "default"
    assert runtime._runtime_id != "not-a-guid"
    uuid.UUID(runtime._runtime_id)  # must be valid UUID


@pytest.mark.asyncio
async def test_factory_no_container_mode_ignores_env_runtime_id(monkeypatch):
    """Without container mode, UIPATH_RUNTIME_ID env var is NOT used."""
    monkeypatch.delenv("UIPATH_MCP_CONTAINER_RUNTIME", raising=False)
    monkeypatch.setenv("UIPATH_RUNTIME_ID", _VALID_GUID)

    ctx = _make_factory_context()
    factory = UiPathMcpRuntimeFactory(context=ctx)
    factory._mcp_config = MagicMock(exists=True)
    factory._mcp_config.get_server.return_value = _make_mcp_server()

    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        runtime = await factory.new_runtime("svc", _VALID_GUID2)

    # Should keep the explicitly passed runtime_id, not override with env var
    assert runtime._runtime_id == _VALID_GUID2


@pytest.mark.asyncio
async def test_factory_container_valid_passed_id_plus_matching_env(monkeypatch):
    """In container mode, if passed runtime_id is already the env UIPATH_RUNTIME_ID, use it."""
    monkeypatch.setenv("UIPATH_MCP_CONTAINER_RUNTIME", "true")
    monkeypatch.setenv("UIPATH_RUNTIME_ID", _VALID_GUID)

    ctx = _make_factory_context()
    factory = UiPathMcpRuntimeFactory(context=ctx)
    factory._mcp_config = MagicMock(exists=True)
    factory._mcp_config.get_server.return_value = _make_mcp_server()

    with patch("uipath_mcp._cli._runtime._runtime.UiPath"):
        runtime = await factory.new_runtime("svc", _VALID_GUID)

    assert runtime._runtime_id == _VALID_GUID
