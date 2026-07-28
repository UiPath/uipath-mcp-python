"""Additional session-server tests: relay loop, consume paths, start/run flows.

Structural unit tests with the stdio/streamable-http transports mocked; they
assert observable effects (stream wiring, queue draining, error swallowing)
rather than log text. The agenthub wire protocol is exercised by the
integration suite (integration_tests.yml), not here.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import (
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCResponse,
)

from uipath_mcp._cli._runtime._session import (
    StdioSessionServer,
    StreamableHttpSessionServer,
)

SMODULE = "uipath_mcp._cli._runtime._session"


def _make_server_config(url: str | None = None) -> MagicMock:
    cfg = MagicMock()
    cfg.command = "cmd"
    cfg.args = []
    cfg.env = {}
    cfg.url = url
    return cfg


@pytest.fixture
def uipath_mock() -> MagicMock:
    m = MagicMock()
    m.api_client.request_async = AsyncMock()
    return m


@pytest.fixture
def stdio_session(uipath_mock) -> StdioSessionServer:
    return StdioSessionServer(_make_server_config(), "slug", "sess-id", uipath_mock)


@pytest.fixture
def http_session(uipath_mock) -> StreamableHttpSessionServer:
    return StreamableHttpSessionServer(
        _make_server_config(url="https://x"), "slug", "sess-id", uipath_mock
    )


def test_is_response_without_root_returns_false(stdio_session):
    assert stdio_session._is_response(object()) is False


@pytest.mark.asyncio
async def test_stop_logs_unexpected_error(stdio_session):
    """stop() swallows and logs a non-cancel/timeout error from task teardown."""
    task = MagicMock()
    task.done.return_value = False
    stdio_session._run_task = task
    # Force wait_for to raise a non-cancel/timeout error so the generic `except`
    # branch runs; patching the primitive is the least-bad way to reach it.
    with (
        patch(f"{SMODULE}.asyncio.shield", return_value=MagicMock()),
        patch(
            f"{SMODULE}.asyncio.wait_for", new=AsyncMock(side_effect=RuntimeError("x"))
        ),
    ):
        await stdio_session.stop()
    assert stdio_session._run_task is None


@pytest.mark.asyncio
async def test_relay_messages_routes_and_reports_errors(stdio_session):
    s = stdio_session
    s._send_message = AsyncMock()
    s._last_request_id = "reqLast"
    s._last_message_id = "9"
    s._active_requests = {"5": "reqMapped"}

    resp_mapped = MagicMock()
    resp_mapped.message = JSONRPCMessage(
        JSONRPCResponse(jsonrpc="2.0", id=5, result={})
    )
    resp_unmapped = MagicMock()
    resp_unmapped.message = JSONRPCMessage(
        JSONRPCResponse(jsonrpc="2.0", id=99, result={})
    )
    req_msg = MagicMock()
    req_msg.message = JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=1, method="m"))
    error_item = ValueError("received-as-error")

    queue = [resp_mapped, resp_unmapped, req_msg, error_item]

    async def fake_receive():
        if queue:
            return queue.pop(0)
        s._read_stream = None
        raise RuntimeError("stop loop")

    s._read_stream = MagicMock()
    s._read_stream.receive = fake_receive

    await s._relay_messages()

    # mapped response consumed the stored mapping
    assert "5" not in s._active_requests
    # mapped + unmapped + request + final error report
    assert s._send_message.await_count >= 4


@pytest.mark.asyncio
async def test_consume_messages_send_error_does_not_hang(stdio_session):
    s = stdio_session
    s._write_stream = MagicMock()
    s._write_stream.send = AsyncMock(side_effect=RuntimeError("send fail"))
    await s._message_queue.put(
        JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=1, method="m"))
    )
    task = asyncio.create_task(s._consume_messages())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    # a failing send still marks the message done -> the consumer never blocks
    assert s._message_queue.empty()


@pytest.mark.asyncio
async def test_consume_messages_drains_queue_on_cancel(stdio_session):
    s = stdio_session
    block = asyncio.Event()

    async def slow_send(_message):
        await block.wait()

    s._write_stream = MagicMock()
    s._write_stream.send = slow_send
    for i in range(2):
        await s._message_queue.put(
            JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=i, method="m"))
        )
    task = asyncio.create_task(s._consume_messages())
    await asyncio.sleep(0.05)  # first message in-flight, second still queued
    task.cancel()
    await task  # CancelledError is handled internally; drains remaining
    assert s._message_queue.empty()


@pytest.mark.asyncio
async def test_stdio_start_error_calls_stop_and_raises(stdio_session):
    with patch(f"{SMODULE}.StdioServerParameters", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            await stdio_session.start()


@pytest.mark.asyncio
async def test_http_start_error_calls_stop_and_raises(http_session):
    with patch(f"{SMODULE}.asyncio.create_task", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            await http_session.start()


class _FakeCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_a):
        return False


@pytest.mark.asyncio
async def test_stdio_run_server_success(stdio_session):
    s = stdio_session
    read, write = MagicMock(), MagicMock()
    with (
        patch(f"{SMODULE}.stdio_client", return_value=_FakeCM((read, write))),
        patch.object(s, "_relay_messages", new=AsyncMock()) as relay,
    ):
        await s._run_server(MagicMock())
    # streams from stdio_client were wired in and the relay loop was driven
    relay.assert_awaited_once()
    assert s._read_stream is read
    assert s._write_stream is write
    assert s._server_stderr_output is not None


@pytest.mark.asyncio
async def test_stdio_run_server_handles_exception_group(stdio_session):
    s = stdio_session
    with (
        patch(
            f"{SMODULE}.stdio_client",
            return_value=_FakeCM((MagicMock(), MagicMock())),
        ),
        patch.object(
            s, "_relay_messages", new=AsyncMock(side_effect=RuntimeError("relay boom"))
        ),
    ):
        # the except* group handler swallows the error; finally still captures stderr
        await s._run_server(MagicMock())
    assert s._server_stderr_output is not None


@pytest.mark.asyncio
async def test_http_run_session_success(http_session):
    s = http_session
    read, write = MagicMock(), MagicMock()
    with (
        patch(
            f"{SMODULE}.streamable_http_client",
            return_value=_FakeCM((read, write, MagicMock())),
        ),
        patch.object(s, "_relay_messages", new=AsyncMock()) as relay,
    ):
        await s._run_http_session()
    relay.assert_awaited_once()
    assert s._read_stream is read
    assert s._write_stream is write


@pytest.mark.asyncio
async def test_http_run_session_swallows_exception(http_session):
    s = http_session
    read = MagicMock()
    with (
        patch(
            f"{SMODULE}.streamable_http_client",
            return_value=_FakeCM((read, MagicMock(), MagicMock())),
        ),
        patch.object(
            s, "_relay_messages", new=AsyncMock(side_effect=RuntimeError("http boom"))
        ),
    ):
        await s._run_http_session()  # exception is caught, not propagated
    # the connection was established (streams wired) before the failure
    assert s._read_stream is read
