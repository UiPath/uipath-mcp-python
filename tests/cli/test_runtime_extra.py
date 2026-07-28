"""Extended runtime tests: HTTP process lifecycle, register, run loop, keep-alive.

These are structural unit tests: the SignalR transport, HTTP client, subprocess
layer and TokenRefresher are all mocked, so they assert how ``UiPathMcpRuntime``
wires itself together and handles local error/lifecycle paths. They deliberately
do NOT verify the agenthub wire protocol (URLs, headers, status-code semantics,
message framing) -- that is covered by the integration suite (integration_tests.yml
/ the testcases/* cloud+alpha jobs). Prefer asserting observable effects over log
text.
"""

import asyncio
import contextlib
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from uipath.runtime import UiPathRuntimeStatus

from uipath_mcp._cli._runtime._exception import UiPathMcpRuntimeError
from uipath_mcp._cli._runtime._runtime import UiPathMcpRuntime
from uipath_mcp._cli._runtime._session import StreamableHttpSessionServer

RMODULE = "uipath_mcp._cli._runtime._runtime"
CODED_KEY = "11111111-2222-3333-4444-555555555555"


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
    with patch(f"{RMODULE}.UiPath"):
        rt = UiPathMcpRuntime(server=server, runtime_id="rid", entrypoint="ep", **extra)
        rt._uipath = MagicMock()
        return rt


@pytest.fixture
def runtime() -> UiPathMcpRuntime:
    return _make_runtime()


class _FakeCM:
    """Minimal async context manager yielding a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_a):
        return False


class _FakeStderr:
    def __init__(self, lines):
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._lines:
            return self._lines.pop(0)
        raise StopAsyncIteration


def _http_client_cm(client: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# --------------------------------------------------------------------------- #
# _start_http_server_process / _drain_http_stderr
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_start_http_server_process_coded(runtime):
    runtime._process_key = CODED_KEY  # Coded -> merges os.environ
    proc = MagicMock(pid=4321, stderr=None)
    with patch(
        f"{RMODULE}.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)
    ):
        await runtime._start_http_server_process()
    assert runtime._http_server_process is proc
    if runtime._http_stderr_drain_task:
        runtime._http_stderr_drain_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runtime._http_stderr_drain_task


@pytest.mark.asyncio
async def test_drain_http_stderr_reads_lines(runtime):
    runtime._http_server_process = MagicMock(
        stderr=_FakeStderr([b"err line 1\n", b"err line 2\n"])
    )
    await runtime._drain_http_stderr()
    assert any("err line 1" in line for line in runtime._http_server_stderr_lines)


# --------------------------------------------------------------------------- #
# _wait_for_http_server_ready
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_wait_for_http_ready_success(runtime):
    runtime._server.url = "http://localhost:9"
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200))
    with patch("httpx.AsyncClient", return_value=_http_client_cm(client)):
        await runtime._wait_for_http_server_ready(max_retries=1, retry_delay=0)
    client.get.assert_awaited_once()  # readiness probe was actually issued


@pytest.mark.asyncio
async def test_wait_for_http_ready_no_url(runtime):
    runtime._server.url = None
    with pytest.raises(ValueError):
        await runtime._wait_for_http_server_ready()


@pytest.mark.asyncio
async def test_wait_for_http_ready_process_crashed(runtime):
    runtime._server.url = "http://x"
    runtime._http_server_process = MagicMock(returncode=1)
    runtime._http_server_stderr_lines = ["boom"]
    with pytest.raises(UiPathMcpRuntimeError):
        await runtime._wait_for_http_server_ready(max_retries=2, retry_delay=0)


@pytest.mark.asyncio
async def test_wait_for_http_ready_retries_exhausted(runtime):
    runtime._server.url = "http://x"
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("no"))
    with (
        patch("httpx.AsyncClient", return_value=_http_client_cm(client)),
        patch(f"{RMODULE}.asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(UiPathMcpRuntimeError):
            await runtime._wait_for_http_server_ready(max_retries=2, retry_delay=0)


@pytest.mark.asyncio
async def test_wait_for_http_ready_status_error(runtime):
    runtime._server.url = "http://x"
    client = MagicMock()
    client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "e", request=MagicMock(), response=MagicMock()
        )
    )
    with patch("httpx.AsyncClient", return_value=_http_client_cm(client)):
        # an HTTP error status still means the server is up -> returns, no raise
        await runtime._wait_for_http_server_ready(max_retries=1, retry_delay=0)
    client.get.assert_awaited_once()


# --------------------------------------------------------------------------- #
# _stop_http_server_process
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_stop_http_server_process_full(runtime):
    async def _run():
        await asyncio.sleep(10)

    runtime._http_monitor_task = asyncio.create_task(_run())
    runtime._http_stderr_drain_task = asyncio.create_task(_run())
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    runtime._http_server_process = proc
    await runtime._stop_http_server_process()
    assert runtime._http_server_process is None
    assert runtime._http_monitor_task is None
    assert runtime._http_stderr_drain_task is None


@pytest.mark.asyncio
async def test_stop_http_process_timeout_kills(runtime):
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    runtime._http_server_process = proc
    # patch wait_for -> TimeoutError to drive the "graceful terminate timed out,
    # escalate to kill()" branch deterministically.
    with patch(
        f"{RMODULE}.asyncio.wait_for", new=AsyncMock(side_effect=asyncio.TimeoutError())
    ):
        await runtime._stop_http_server_process()
    proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_stop_http_process_lookup_error(runtime):
    proc = MagicMock()
    proc.terminate = MagicMock(side_effect=ProcessLookupError())
    runtime._http_server_process = proc
    await runtime._stop_http_server_process()
    assert runtime._http_server_process is None


# --------------------------------------------------------------------------- #
# _monitor_http_server_process
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_monitor_http_process_exit_stops_sessions(runtime):
    runtime._http_server_process = MagicMock(wait=AsyncMock(return_value=1))
    http_sess = MagicMock(spec=StreamableHttpSessionServer)
    http_sess.stop = AsyncMock()
    runtime._session_servers = {"s1": http_sess}
    await runtime._monitor_http_server_process()
    http_sess.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_http_process_stop_error(runtime):
    runtime._http_server_process = MagicMock(wait=AsyncMock(return_value=1))
    http_sess = MagicMock(spec=StreamableHttpSessionServer)
    http_sess.stop = AsyncMock(side_effect=RuntimeError("stop fail"))
    runtime._session_servers = {"s1": http_sess}
    await runtime._monitor_http_server_process()
    # a failing stop() still drops the crashed session from the map
    assert "s1" not in runtime._session_servers


@pytest.mark.asyncio
async def test_monitor_http_process_cancelled(runtime):
    proc = MagicMock(wait=AsyncMock(side_effect=asyncio.CancelledError()))
    runtime._http_server_process = proc
    await runtime._monitor_http_server_process()
    proc.wait.assert_awaited_once()  # reached the await before being cancelled


# --------------------------------------------------------------------------- #
# _handle_signalr_session_closed
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_session_closed_non_sandboxed_logs_output(runtime):
    sess = MagicMock(output="out")
    sess.stop = AsyncMock()
    runtime._session_servers["s1"] = sess
    runtime._job_id = None  # not sandboxed
    await runtime._handle_signalr_session_closed(["s1"])
    sess.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_closed_handles_stop_error(runtime):
    # the session is popped from the map before stop() is awaited, so a failing
    # stop() must not leave a dangling entry behind.
    sess = MagicMock(output=None)
    sess.stop = AsyncMock(side_effect=RuntimeError("boom-close"))
    runtime._session_servers["s1"] = sess
    await runtime._handle_signalr_session_closed(["s1"])
    assert "s1" not in runtime._session_servers


# --------------------------------------------------------------------------- #
# _handle_signalr_message start-error path
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_handle_message_start_error(runtime):
    runtime._server.is_streamable_http = False
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=RuntimeError("start boom"))
    with (
        patch(f"{RMODULE}.StdioSessionServer", return_value=fake),
        patch.object(runtime, "_on_session_start_error", new=AsyncMock()) as ose,
    ):
        await runtime._handle_signalr_message(["sNew", "req"])
    ose.assert_awaited_once_with("sNew")


# --------------------------------------------------------------------------- #
# _cleanup extended paths
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cleanup_full(runtime):
    async def _run():
        await asyncio.sleep(10)

    runtime._token_refresher = MagicMock(stop=AsyncMock())
    runtime._keep_alive_task = asyncio.create_task(_run())
    good = MagicMock()
    good.stop = AsyncMock()
    bad = MagicMock()
    bad.stop = AsyncMock(side_effect=RuntimeError("x"))
    runtime._session_servers = {"g": good, "b": bad}
    ws = MagicMock()
    ws.close = AsyncMock()
    transport = MagicMock(_ws=ws)
    runtime._signalr_client = MagicMock(_transport=transport)
    with (
        patch.object(runtime, "_on_runtime_abort", new=AsyncMock()),
        patch.object(runtime, "_stop_http_server_process", new=AsyncMock()),
    ):
        await runtime._cleanup()
    good.stop.assert_awaited_once()
    ws.close.assert_awaited_once()
    assert runtime._cleanup_done is True


@pytest.mark.asyncio
async def test_cleanup_ws_close_error(runtime):
    ws = MagicMock()
    ws.close = AsyncMock(side_effect=RuntimeError("close fail"))
    transport = MagicMock(_ws=ws)
    runtime._signalr_client = MagicMock(_transport=transport)
    with (
        patch.object(runtime, "_on_runtime_abort", new=AsyncMock()),
        patch.object(runtime, "_stop_http_server_process", new=AsyncMock()),
    ):
        await runtime._cleanup()
    # close was attempted, and its failure does not abort cleanup
    ws.close.assert_awaited_once()
    assert runtime._cleanup_done is True


# --------------------------------------------------------------------------- #
# _run_server orchestration
# --------------------------------------------------------------------------- #
def _run_server_patches(runtime, cfg):
    sig = MagicMock()
    sig.run = AsyncMock()
    refresher = MagicMock()
    refresher.start = MagicMock()
    refresher.stop = AsyncMock()
    return sig, refresher


@pytest.mark.asyncio
async def test_run_server_happy_path(runtime):
    runtime._tenant_id = "t"
    runtime._org_id = "o"
    runtime._folder_key = "fk"
    runtime._server.is_streamable_http = False
    runtime._session_output = "final-out"
    cfg = MagicMock(base_url="https://x")
    sig, refresher = _run_server_patches(runtime, cfg)
    with (
        patch(f"{RMODULE}.UiPathConfig", cfg),
        patch(f"{RMODULE}.SignalRClient", return_value=sig),
        patch(f"{RMODULE}.TokenRefresher", return_value=refresher),
        patch.object(runtime, "_register", new=AsyncMock()),
        patch.object(runtime, "_keep_alive", new=AsyncMock()),
        patch.object(runtime, "_cleanup", new=AsyncMock()),
    ):
        result = await runtime._run_server()
    assert result.status == UiPathRuntimeStatus.SUCCESSFUL
    assert result.output.get("content") == "final-out"


@pytest.mark.asyncio
async def test_run_server_keyboard_interrupt_during_wait(runtime):
    runtime._tenant_id = "t"
    runtime._org_id = "o"
    runtime._folder_key = "fk"
    runtime._server.is_streamable_http = False
    cfg = MagicMock(base_url="https://x")
    sig, refresher = _run_server_patches(runtime, cfg)
    with (
        patch(f"{RMODULE}.UiPathConfig", cfg),
        patch(f"{RMODULE}.SignalRClient", return_value=sig),
        patch(f"{RMODULE}.TokenRefresher", return_value=refresher),
        patch.object(runtime, "_register", new=AsyncMock()),
        patch.object(runtime, "_keep_alive", new=AsyncMock()),
        patch.object(runtime, "_cleanup", new=AsyncMock()),
        # simulate Ctrl-C while awaiting the run/cancel tasks
        patch(f"{RMODULE}.asyncio.wait", side_effect=KeyboardInterrupt()),
    ):
        result = await runtime._run_server()
    assert result.status == UiPathRuntimeStatus.SUCCESSFUL


@pytest.mark.asyncio
async def test_run_server_outer_keyboard_interrupt(runtime):
    with (
        patch.object(runtime, "_validate_auth", side_effect=KeyboardInterrupt()),
        patch.object(runtime, "_cleanup", new=AsyncMock()),
    ):
        result = await runtime._run_server()
    assert result.status == UiPathRuntimeStatus.SUCCESSFUL


@pytest.mark.asyncio
async def test_run_server_wraps_generic_error(runtime):
    with (
        patch.object(runtime, "_validate_auth", side_effect=ValueError("bad")),
        patch.object(runtime, "_cleanup", new=AsyncMock()),
    ):
        with pytest.raises(UiPathMcpRuntimeError):
            await runtime._run_server()


# --------------------------------------------------------------------------- #
# _register
# --------------------------------------------------------------------------- #
def _tool(name="t", description="d", input_schema=None):
    # NB: `name` is a reserved MagicMock ctor kwarg, so it must be set explicitly
    # afterwards rather than passed to the constructor.
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = input_schema
    return tool


@pytest.mark.asyncio
async def test_register_stdio_success(runtime):
    runtime._server.is_streamable_http = False
    runtime._job_id = None
    runtime._process_key = None  # SelfHosted
    tools_result = MagicMock(tools=[_tool(input_schema={"type": "object"})])
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=tools_result)
    runtime._uipath.api_client.request_async = AsyncMock()
    with (
        patch(
            f"{RMODULE}.stdio_client",
            return_value=_FakeCM((MagicMock(), MagicMock())),
        ),
        patch(f"{RMODULE}.ClientSession", return_value=_FakeCM(session)),
    ):
        await runtime._register()
    runtime._uipath.api_client.request_async.assert_awaited_once()
    # the registration payload carries the discovered tool with its schema
    _args, kwargs = runtime._uipath.api_client.request_async.call_args
    payload = kwargs["json"]
    assert payload["server"]["Slug"] == runtime.slug
    assert payload["tools"][0]["Name"] == "t"
    # assert the schema by value, not by exact serialized string
    assert json.loads(payload["tools"][0]["InputSchema"]) == {"type": "object"}


@pytest.mark.asyncio
async def test_register_stdio_init_failure(runtime):
    runtime._server.is_streamable_http = False
    runtime._job_id = None
    runtime._process_key = None
    session = MagicMock()
    session.initialize = AsyncMock(side_effect=RuntimeError("init boom"))
    with (
        patch(
            f"{RMODULE}.stdio_client",
            return_value=_FakeCM((MagicMock(), MagicMock())),
        ),
        patch(f"{RMODULE}.ClientSession", return_value=_FakeCM(session)),
        patch.object(runtime, "_on_runtime_abort", new=AsyncMock()),
    ):
        with pytest.raises(UiPathMcpRuntimeError):
            await runtime._register()


@pytest.mark.asyncio
async def test_register_http_success_coded(runtime):
    runtime._server.is_streamable_http = True
    runtime._server.url = "http://localhost:9"
    runtime._process_key = CODED_KEY  # Coded -> include env
    tools_result = MagicMock(tools=[_tool(description=None, input_schema=None)])
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=tools_result)
    runtime._uipath.api_client.request_async = AsyncMock()
    with (
        patch.object(runtime, "_start_http_server_process", new=AsyncMock()),
        patch.object(runtime, "_wait_for_http_server_ready", new=AsyncMock()),
        patch(
            "mcp.client.streamable_http.streamable_http_client",
            return_value=_FakeCM((MagicMock(), MagicMock(), MagicMock())),
        ),
        patch(f"{RMODULE}.ClientSession", return_value=_FakeCM(session)),
    ):
        await runtime._register()
    runtime._uipath.api_client.request_async.assert_awaited_once()
    # tool with no input schema serializes to an empty-object schema
    _args, kwargs = runtime._uipath.api_client.request_async.call_args
    payload = kwargs["json"]
    assert payload["tools"][0]["Name"] == "t"
    assert json.loads(payload["tools"][0]["InputSchema"]) == {}


@pytest.mark.asyncio
async def test_register_registration_http_error(runtime):
    runtime._server.is_streamable_http = False
    runtime._job_id = None
    runtime._process_key = None
    tools_result = MagicMock(tools=[])
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=tools_result)
    err = httpx.HTTPStatusError(
        "e", request=MagicMock(), response=MagicMock(status_code=500, text="server err")
    )
    runtime._uipath.api_client.request_async = AsyncMock(side_effect=err)
    with (
        patch(
            f"{RMODULE}.stdio_client",
            return_value=_FakeCM((MagicMock(), MagicMock())),
        ),
        patch(f"{RMODULE}.ClientSession", return_value=_FakeCM(session)),
    ):
        with pytest.raises(UiPathMcpRuntimeError):
            await runtime._register()


# --------------------------------------------------------------------------- #
# _keep_alive
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_keep_alive_pings_and_cancels_sandbox(runtime):
    runtime._job_id = "job"  # sandboxed

    async def fake_send(method, arguments, on_invocation):
        await on_invocation(MagicMock(error=None, result=[]))

    runtime._signalr_client = MagicMock(send=fake_send)
    with patch(f"{RMODULE}.asyncio.wait_for", new=AsyncMock(return_value=None)):
        await runtime._keep_alive()
    assert runtime._cancel_event.is_set()


@pytest.mark.asyncio
async def test_keep_alive_error_response_does_not_cancel(runtime):
    # A sandboxed runtime with an *empty* session list would normally self-cancel;
    # an error response must short-circuit before that check, leaving it running.
    runtime._job_id = "job"  # sandboxed

    async def fake_send(method, arguments, on_invocation):
        await on_invocation(MagicMock(error="ka-boom", result=[]))

    runtime._signalr_client = MagicMock(send=fake_send)
    with patch(f"{RMODULE}.asyncio.wait_for", new=AsyncMock(return_value=None)):
        await runtime._keep_alive()
    assert not runtime._cancel_event.is_set()


@pytest.mark.asyncio
async def test_keep_alive_no_signalr_client(runtime, caplog):
    # This branch has no observable effect other than the log line (there is no
    # client to act on), so a log assertion is the honest check here.
    runtime._signalr_client = None
    with (
        patch(f"{RMODULE}.asyncio.wait_for", new=AsyncMock(return_value=None)),
        caplog.at_level(logging.ERROR),
    ):
        await runtime._keep_alive()
    assert "SignalR client not initialized" in caplog.text


@pytest.mark.asyncio
async def test_keep_alive_send_error_is_swallowed(runtime):
    send = AsyncMock(side_effect=RuntimeError("send-nope"))
    runtime._signalr_client = MagicMock(send=send)
    with patch(f"{RMODULE}.asyncio.wait_for", new=AsyncMock(return_value=None)):
        # a send failure must not break the heartbeat loop or cancel the runtime
        await runtime._keep_alive()
    send.assert_awaited_once()
    assert not runtime._cancel_event.is_set()


@pytest.mark.asyncio
async def test_keep_alive_cancelled(runtime):
    runtime._signalr_client = MagicMock(send=AsyncMock())
    with patch(
        f"{RMODULE}.asyncio.wait_for",
        new=AsyncMock(side_effect=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await runtime._keep_alive()
