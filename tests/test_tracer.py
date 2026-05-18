"""Tests for McpTracer."""

import logging
from unittest.mock import MagicMock

import mcp.types as types
import pytest

from uipath_mcp._cli._runtime._tracer import McpTracer


@pytest.fixture
def fake_span() -> MagicMock:
    return MagicMock()


@pytest.fixture
def tracer_with_fake_span(fake_span: MagicMock) -> McpTracer:
    fake_tracer = MagicMock()
    fake_tracer.start_span.return_value = fake_span
    return McpTracer(tracer=fake_tracer, logger=logging.getLogger("test"))


def _req(id_: int, method: str, params=None) -> types.JSONRPCMessage:
    return types.JSONRPCMessage(
        types.JSONRPCRequest(jsonrpc="2.0", id=id_, method=method, params=params)
    )


def _notif(method: str, params=None) -> types.JSONRPCMessage:
    return types.JSONRPCMessage(
        types.JSONRPCNotification(jsonrpc="2.0", method=method, params=params)
    )


def _resp(id_: int, result=None) -> types.JSONRPCMessage:
    return types.JSONRPCMessage(
        types.JSONRPCResponse(jsonrpc="2.0", id=id_, result=result or {})
    )


def _err(id_: int) -> types.JSONRPCMessage:
    return types.JSONRPCMessage(
        types.JSONRPCError(
            jsonrpc="2.0",
            id=id_,
            error=types.ErrorData(code=-1, message="boom"),
        )
    )


def test_default_init():
    t = McpTracer()
    assert t._tracer is not None
    assert t._logger is not None
    assert t._active_request_spans == {}


def test_request_span(tracer_with_fake_span):
    span = tracer_with_fake_span.create_span_for_message(
        _req(1, "tools/call", {"name": "x", "arguments": {"k": "v"}}),
        custom="ctx",
    )
    assert span is not None
    assert "1" in tracer_with_fake_span._active_request_spans


def test_request_span_resources_read(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(
        _req(2, "resources/read", {"uri": "file://x"})
    )


def test_request_span_prompts_get(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(_req(3, "prompts/get", {"name": "p"}))


def test_notification_span(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(
        _notif(
            "notifications/progress",
            {"progress": 0.5, "total": 1.0},
        )
    )


def test_notification_resource_updated(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(
        _notif("notifications/resources/updated", {"uri": "file://x"})
    )


def test_notification_cancelled(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(
        _notif("notifications/cancelled", {"requestId": "1", "reason": "user"})
    )


def test_response_creates_orphan_span(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(_resp(99, {"ok": True}))


def test_response_attaches_to_active_request(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(_req(7, "tools/call"))
    tracer_with_fake_span.create_span_for_message(_resp(7, {"ok": True}))
    assert "7" not in tracer_with_fake_span._active_request_spans


def test_error_orphan_span(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(_err(50))


def test_error_correlates_with_active_request(tracer_with_fake_span):
    tracer_with_fake_span.create_span_for_message(_req(8, "tools/call"))
    tracer_with_fake_span.create_span_for_message(_err(8))
    assert "8" not in tracer_with_fake_span._active_request_spans


def test_record_http_error(tracer_with_fake_span, fake_span):
    tracer_with_fake_span.record_http_error(fake_span, 500, "oops")
    fake_span.set_status.assert_called()


def test_record_exception(tracer_with_fake_span, fake_span):
    tracer_with_fake_span.record_exception(fake_span, RuntimeError("x"))
    fake_span.set_status.assert_called()


def test_create_operation_span(tracer_with_fake_span):
    span = tracer_with_fake_span.create_operation_span("op", k="v")
    assert span is not None


def test_get_current_span(tracer_with_fake_span):
    assert tracer_with_fake_span.get_current_span() is not None


def test_add_event_to_current_span(tracer_with_fake_span):
    tracer_with_fake_span.add_event_to_current_span("evt", k="v")
