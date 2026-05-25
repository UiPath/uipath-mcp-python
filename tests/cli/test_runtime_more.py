"""Extra runtime tests targeting properties, handlers, and shallow paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uipath_mcp._cli._runtime._context import UiPathServerType
from uipath_mcp._cli._runtime._exception import UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime


def _make_runtime(server: MagicMock | None = None, **extra) -> UiPathMcpRuntime:
    server = server or MagicMock(
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


@pytest.fixture
def runtime() -> UiPathMcpRuntime:
    return _make_runtime()


@pytest.mark.asyncio
async def test_get_schema(runtime):
    schema = await runtime.get_schema()
    assert schema.file_path == "ep"
    assert schema.type == "mcpserver"


def test_slug_defaults_to_server_name(runtime):
    assert runtime.slug == "svc"


def test_slug_uses_server_slug_when_set():
    rt = _make_runtime(server_slug="explicit-slug")
    assert rt.slug == "explicit-slug"


def test_sandboxed_property(runtime):
    runtime._job_id = None
    assert runtime.sandboxed is False
    runtime._job_id = "job-1"
    assert runtime.sandboxed is True


def test_packaged_property(runtime):
    runtime._process_key = None
    assert runtime.packaged is False
    runtime._process_key = "00000000-0000-0000-0000-000000000000"
    assert runtime.packaged is False
    runtime._process_key = "11111111-2222-3333-4444-555555555555"
    assert runtime.packaged is True


def test_server_type_selfhosted(runtime):
    runtime._job_id = None
    runtime._process_key = None
    assert runtime.server_type is UiPathServerType.SelfHosted


def test_server_type_command(runtime):
    runtime._job_id = "j"
    runtime._process_key = None
    assert runtime.server_type is UiPathServerType.Command


def test_server_type_coded(runtime):
    runtime._job_id = "j"
    runtime._process_key = "11111111-2222-3333-4444-555555555555"
    assert runtime.server_type is UiPathServerType.Coded


@pytest.mark.asyncio
async def test_validate_auth_missing_url(runtime):
    fake_cfg = MagicMock()
    fake_cfg.base_url = None
    with patch("uipath_mcp._cli._runtime._runtime.UiPathConfig", fake_cfg):
        with pytest.raises(UiPathMcpRuntimeError):
            runtime._validate_auth()


@pytest.mark.asyncio
async def test_validate_auth_missing_tenant_or_org(runtime):
    fake_cfg = MagicMock()
    fake_cfg.base_url = "https://x"
    runtime._tenant_id = None
    runtime._org_id = None
    with patch("uipath_mcp._cli._runtime._runtime.UiPathConfig", fake_cfg):
        with pytest.raises(UiPathMcpRuntimeError):
            runtime._validate_auth()


@pytest.mark.asyncio
async def test_validate_auth_ok(runtime):
    fake_cfg = MagicMock()
    fake_cfg.base_url = "https://x"
    runtime._tenant_id = "t"
    runtime._org_id = "o"
    with patch("uipath_mcp._cli._runtime._runtime.UiPathConfig", fake_cfg):
        runtime._validate_auth()  # should not raise


@pytest.mark.asyncio
async def test_handle_signalr_error_open_close(runtime):
    await runtime._handle_signalr_error("e")
    await runtime._handle_signalr_open()
    await runtime._handle_signalr_close()


@pytest.mark.asyncio
async def test_handle_signalr_session_closed_invalid_args(runtime):
    await runtime._handle_signalr_session_closed([])


@pytest.mark.asyncio
async def test_handle_signalr_session_closed_unknown_session(runtime):
    runtime._job_id = None
    await runtime._handle_signalr_session_closed(["unknown"])


@pytest.mark.asyncio
async def test_handle_signalr_session_closed_with_session(runtime):
    sess = MagicMock()
    sess.stop = AsyncMock()
    sess.output = "out"
    runtime._session_servers["s1"] = sess
    runtime._job_id = "j"  # sandboxed
    await runtime._handle_signalr_session_closed(["s1"])
    sess.stop.assert_awaited_once()
    assert runtime._session_output == "out"
    assert runtime._cancel_event.is_set()


@pytest.mark.asyncio
async def test_handle_signalr_message_invalid_args(runtime):
    await runtime._handle_signalr_message([])


@pytest.mark.asyncio
async def test_handle_signalr_message_existing_session(runtime):
    sess = MagicMock()
    sess.on_message_received = AsyncMock()
    runtime._session_servers["s1"] = sess
    await runtime._handle_signalr_message(["s1", "req1"])
    sess.on_message_received.assert_awaited_once_with("req1")


@pytest.mark.asyncio
async def test_handle_signalr_message_new_session(runtime):
    runtime._server.is_streamable_http = False
    fake_sess = MagicMock()
    fake_sess.start = AsyncMock()
    fake_sess.on_message_received = AsyncMock()
    with patch(
        "uipath_mcp._cli._runtime._runtime.StdioSessionServer", return_value=fake_sess
    ):
        await runtime._handle_signalr_message(["sNew", "r"])
    fake_sess.start.assert_awaited_once()
    fake_sess.on_message_received.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_signalr_message_new_http_session(runtime):
    runtime._server.is_streamable_http = True
    fake_sess = MagicMock()
    fake_sess.start = AsyncMock()
    fake_sess.on_message_received = AsyncMock()
    with patch(
        "uipath_mcp._cli._runtime._runtime.StreamableHttpSessionServer",
        return_value=fake_sess,
    ):
        await runtime._handle_signalr_message(["sNew", "r"])
    fake_sess.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_runtime_abort_logs_when_non_202(runtime):
    response = MagicMock(status_code=500, text="oops")
    runtime._uipath.api_client.request_async = AsyncMock(return_value=response)
    await runtime._on_runtime_abort()


@pytest.mark.asyncio
async def test_on_runtime_abort_success(runtime):
    response = MagicMock(status_code=202)
    runtime._uipath.api_client.request_async = AsyncMock(return_value=response)
    await runtime._on_runtime_abort()


@pytest.mark.asyncio
async def test_on_runtime_abort_swallows_exception(runtime):
    runtime._uipath.api_client.request_async = AsyncMock(side_effect=RuntimeError("x"))
    await runtime._on_runtime_abort()


@pytest.mark.asyncio
async def test_on_session_start_error_success(runtime):
    response = MagicMock(status_code=202)
    runtime._uipath.api_client.request_async = AsyncMock(return_value=response)
    await runtime._on_session_start_error("s1")


@pytest.mark.asyncio
async def test_on_session_start_error_non_202(runtime):
    response = MagicMock(status_code=400, text="bad")
    runtime._uipath.api_client.request_async = AsyncMock(return_value=response)
    await runtime._on_session_start_error("s1")


@pytest.mark.asyncio
async def test_on_session_start_error_exception(runtime):
    runtime._uipath.api_client.request_async = AsyncMock(side_effect=RuntimeError("x"))
    await runtime._on_session_start_error("s1")


@pytest.mark.asyncio
async def test_dispose_calls_cleanup(runtime):
    with patch.object(runtime, "_cleanup", new=AsyncMock()) as cu:
        await runtime.dispose()
    cu.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_idempotent(runtime):
    runtime._cleanup_done = True
    await runtime._cleanup()


@pytest.mark.asyncio
async def test_cleanup_runs(runtime):
    runtime._token_refresher = MagicMock(stop=AsyncMock())
    with patch.object(runtime, "_on_runtime_abort", new=AsyncMock()):
        await runtime._cleanup()
    assert runtime._cleanup_done is True


@pytest.mark.asyncio
async def test_execute_calls_run_server(runtime):
    with patch.object(runtime, "_run_server", new=AsyncMock(return_value="R")) as rs:
        result = await runtime.execute()
    assert result == "R"
    rs.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_yields_result(runtime):
    with patch.object(runtime, "_run_server", new=AsyncMock(return_value="R")):
        results = [r async for r in runtime.stream()]
    assert results == ["R"]


@pytest.mark.asyncio
async def test_stop_http_server_process_no_process(runtime):
    await runtime._stop_http_server_process()


@pytest.mark.asyncio
async def test_monitor_http_server_process_no_process(runtime):
    await runtime._monitor_http_server_process()


@pytest.mark.asyncio
async def test_drain_http_stderr_no_process(runtime):
    await runtime._drain_http_stderr()
