"""Tests for BaseSessionServer and concrete session servers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import (
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)

from uipath_mcp._cli._runtime import _session as session_mod
from uipath_mcp._cli._runtime._session import (
    StdioSessionServer,
    StreamableHttpSessionServer,
)


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
def stdio_session(uipath_mock):
    return StdioSessionServer(_make_server_config(), "slug", "sess-id", uipath_mock)


@pytest.fixture
def http_session(uipath_mock):
    return StreamableHttpSessionServer(
        _make_server_config(url="https://x"), "slug", "sess-id", uipath_mock
    )


def test_is_response_for_response(stdio_session):
    msg = JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
    assert stdio_session._is_response(msg) is True


def test_is_response_for_error(stdio_session):
    msg = JSONRPCMessage(
        JSONRPCError(jsonrpc="2.0", id=1, error=ErrorData(code=-1, message="x"))
    )
    assert stdio_session._is_response(msg) is True


def test_is_response_for_request(stdio_session):
    msg = JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=1, method="m"))
    assert stdio_session._is_response(msg) is False


def test_get_message_id_request(stdio_session):
    msg = JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=42, method="m"))
    assert stdio_session._get_message_id(msg) == "42"


def test_get_message_id_notification_no_id(stdio_session):
    msg = JSONRPCMessage(JSONRPCNotification(jsonrpc="2.0", method="m"))
    assert stdio_session._get_message_id(msg) == ""


def test_stdio_output_property(stdio_session):
    assert stdio_session.output is None
    stdio_session._server_stderr_output = "boom"
    assert stdio_session.output == "boom"


def test_http_output_property(http_session):
    assert http_session.output is None


@pytest.mark.asyncio
async def test_stop_when_no_task(stdio_session):
    await stdio_session.stop()
    assert stdio_session._run_task is None


@pytest.mark.asyncio
async def test_send_message_internal_202(stdio_session, uipath_mock):
    uipath_mock.api_client.request_async.return_value = MagicMock(status_code=202)
    msg = JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
    await stdio_session._send_message_internal(msg, "req-1")


@pytest.mark.asyncio
async def test_send_message_internal_5xx_raises(stdio_session, uipath_mock):
    uipath_mock.api_client.request_async.return_value = MagicMock(
        status_code=500, text="err"
    )
    msg = JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
    with pytest.raises(Exception, match="500"):
        await stdio_session._send_message_internal(msg, "req-1")


@pytest.mark.asyncio
async def test_get_messages_internal_200_with_request(stdio_session, uipath_mock):
    msg = JSONRPCRequest(jsonrpc="2.0", id=7, method="tools/call").model_dump()
    uipath_mock.api_client.request_async.return_value = MagicMock(
        status_code=200, json=MagicMock(return_value=[msg])
    )
    await stdio_session._get_messages_internal("req-1")
    assert stdio_session._last_request_id == "req-1"
    assert stdio_session._active_requests.get("7") == "req-1"


@pytest.mark.asyncio
async def test_get_messages_internal_200_with_response(stdio_session, uipath_mock):
    msg = JSONRPCResponse(jsonrpc="2.0", id=8, result={}).model_dump()
    uipath_mock.api_client.request_async.return_value = MagicMock(
        status_code=200, json=MagicMock(return_value=[msg])
    )
    await stdio_session._get_messages_internal("req-2")
    assert stdio_session._last_request_id == "req-2"


@pytest.mark.asyncio
async def test_get_messages_internal_5xx_raises(stdio_session, uipath_mock):
    uipath_mock.api_client.request_async.return_value = MagicMock(
        status_code=503, text="bad"
    )
    with pytest.raises(Exception, match="503"):
        await stdio_session._get_messages_internal("req-1")


@pytest.mark.asyncio
async def test_on_message_received_success_first_try(stdio_session):
    with patch.object(stdio_session, "_get_messages_internal", new=AsyncMock()) as gi:
        await stdio_session.on_message_received("r")
    gi.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_received_retries_then_succeeds(stdio_session, monkeypatch):
    monkeypatch.setattr(session_mod, "RETRY_DELAY", 0)
    calls = {"n": 0}

    async def flaky(_):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")

    with patch.object(stdio_session, "_get_messages_internal", side_effect=flaky):
        await stdio_session.on_message_received("r")
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_on_message_received_raises_after_max_retries(stdio_session, monkeypatch):
    monkeypatch.setattr(session_mod, "RETRY_DELAY", 0)
    with patch.object(
        stdio_session,
        "_get_messages_internal",
        side_effect=RuntimeError("nope"),
    ):
        with pytest.raises(RuntimeError, match="nope"):
            await stdio_session.on_message_received("r")


@pytest.mark.asyncio
async def test_send_message_succeeds(stdio_session):
    with patch.object(stdio_session, "_send_message_internal", new=AsyncMock()) as si:
        msg = JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
        await stdio_session._send_message(msg, "r")
    si.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_raises_after_max_retries(stdio_session, monkeypatch):
    monkeypatch.setattr(session_mod, "RETRY_DELAY", 0)
    with patch.object(
        stdio_session, "_send_message_internal", side_effect=RuntimeError("nope")
    ):
        msg = JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
        with pytest.raises(RuntimeError):
            await stdio_session._send_message(msg, "r")


@pytest.mark.asyncio
async def test_stdio_start_creates_task(stdio_session):
    with patch.object(stdio_session, "_run_server", new=AsyncMock()):
        await stdio_session.start()
        assert stdio_session._run_task is not None
        await stdio_session.stop()


@pytest.mark.asyncio
async def test_http_start_creates_task(http_session):
    with patch.object(http_session, "_run_http_session", new=AsyncMock()):
        await http_session.start()
        assert http_session._run_task is not None
        await http_session.stop()


@pytest.mark.asyncio
async def test_http_run_session_requires_url(uipath_mock):
    cfg = _make_server_config(url=None)
    s = StreamableHttpSessionServer(cfg, "slug", "sid", uipath_mock)
    with pytest.raises(ValueError, match="url"):
        await s._run_http_session()


def test_run_server_callback_swallows_cancel(stdio_session):
    import asyncio

    task = MagicMock()
    task.result.side_effect = asyncio.CancelledError()
    stdio_session._run_server_callback(task)


def test_run_server_callback_logs_other(stdio_session):
    task = MagicMock()
    task.result.side_effect = RuntimeError("boom")
    stdio_session._run_server_callback(task)


@pytest.mark.asyncio
async def test_consume_messages_processes_and_exits(stdio_session):
    import asyncio

    stdio_session._write_stream = MagicMock()
    stdio_session._write_stream.send = AsyncMock()
    msg = JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=1, method="m"))
    await stdio_session._message_queue.put(msg)

    task = asyncio.create_task(stdio_session._consume_messages())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    stdio_session._write_stream.send.assert_awaited()
