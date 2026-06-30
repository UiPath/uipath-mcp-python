"""Tests for container-mode lifetime override via UIPATH_MCP_CONTAINER_RUNTIME."""

from unittest.mock import MagicMock, patch

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
