import json
import logging
from typing import Dict, Optional, TypeVar

import mcp.types as types
from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

T = TypeVar("T")


class McpTracer:
    """Helper class to create and manage spans for MCP messages."""

    def __init__(
        self,
        tracer: Optional[trace.Tracer] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self._tracer = tracer or trace.get_tracer(__name__)
        self._logger = logger or logging.getLogger(__name__)
        # Dictionary to store active request spans
        self._active_request_spans: Dict[str, Span] = {}

    def create_span_for_message(self, message: types.JSONRPCMessage, **context) -> Span:
        """Create and configure a span for a message.

        Args:
            message: The JSON-RPC message
            **context: Additional context attributes to add to the span

        Returns:
            A configured OpenTelemetry span
        """
        root_value = message.root

        # Check if this is a response to a tracked request
        parent_span = None
        if (
            isinstance(root_value, types.JSONRPCResponse)
            or isinstance(root_value, types.JSONRPCError)
        ) and hasattr(root_value, "id"):
            request_id = str(root_value.id)
            parent_span = self._active_request_spans.get(request_id)

        # Create span with appropriate context
        if parent_span:
            # This is a response to a tracked request - create as child span
            span_context = trace.set_span_in_context(parent_span)

            if isinstance(root_value, types.JSONRPCResponse):
                span = self._tracer.start_span("response", context=span_context)
                span.set_attribute("type", "response")
                span.set_attribute("span_type", "MCP response")
                span.set_attribute("id", str(root_value.id))
                # if isinstance(root_value.result, dict):
                # parent_span.set_attribute("output", json.dumps(root_value.result))
                self._add_response_attributes(span, root_value)
            elif isinstance(root_value, types.JSONRPCError):  # JSONRPCError
                span = self._tracer.start_span("error", context=span_context)
                span.set_attribute("type", "error")
                span.set_attribute("span_type", "MCP error")
                span.set_attribute("id", str(root_value.id))
                span.set_attribute("error_code", root_value.error.code)
                span.set_attribute("error", root_value.error.message)
                span.set_status(StatusCode.ERROR)

            # Remove the request from active tracking
            self._active_request_spans.pop(request_id, None)
        else:
            # Create standard span based on message type
            if isinstance(root_value, types.JSONRPCRequest):
                span = self._tracer.start_span(f"{root_value.method}")
                span.set_attribute("type", "request")
                span.set_attribute("span_type", "MCP request")
                span.set_attribute("id", str(root_value.id))
                span.set_attribute("method", root_value.method)
                self._add_request_attributes(span, root_value)

                # Store for future response correlation
                self._active_request_spans[str(root_value.id)] = span

            elif isinstance(root_value, types.JSONRPCNotification):
                span = self._tracer.start_span(root_value.method)
                span.set_attribute("type", "notification")
                span.set_attribute("span_type", "MCP notification")
                span.set_attribute("method", root_value.method)
                self._add_notification_attributes(span, root_value)

            elif isinstance(root_value, types.JSONRPCResponse):
                span = self._tracer.start_span("response")
                span.set_attribute("type", "response")
                span.set_attribute("span_type", "MCP response")
                span.set_attribute("id", str(root_value.id))
                self._add_response_attributes(span, root_value)

            elif isinstance(root_value, types.JSONRPCError):
                span = self._tracer.start_span("error")
                span.set_attribute("type", "error")
                span.set_attribute("span_type", "MCP error")
                span.set_attribute("id", str(root_value.id))
                span.set_attribute("error_code", root_value.error.code)
                span.set_attribute("error", root_value.error.message)
                span.set_status(StatusCode.ERROR)
            else:
                span = self._tracer.start_span("unknown")
                span.set_attribute("span_type", str(type(root_value).__name__))
                span.set_attribute("type", str(type(root_value).__name__))

        # Add context attributes
        for key, value in context.items():
            span.set_attribute(key, str(value))

        return span

    def _add_request_attributes(
        self, span: Span, request: types.JSONRPCRequest
    ) -> None:
        """Add request-specific attributes to the span."""
        if request.params:
            # Add basic param information
            if isinstance(request.params, dict):
                span.set_attribute("input", json.dumps(request.params))

            # Handle specific request types based on method
            if request.method == "tools/call" and isinstance(request.params, dict):
                if "name" in request.params:
                    span.set_attribute("name", request.params["name"])
                    span.update_name(f"{request.method}/{request.params['name']}")
                if "arguments" in request.params and isinstance(
                    request.params["arguments"], dict
                ):
                    span.set_attribute("input", json.dumps(request.params["arguments"]))

            # Handle specific tracing for other method types
            elif request.method == "resources/read" and isinstance(
                request.params, dict
            ):
                if "uri" in request.params:
                    span.set_attribute("resource_uri", str(request.params["uri"]))

            elif request.method == "prompts/get" and isinstance(request.params, dict):
                if "name" in request.params:
                    span.set_attribute("prompt_name", str(request.params["name"]))

    def _add_notification_attributes(
        self, span: Span, notification: types.JSONRPCNotification
    ) -> None:
        """Add notification-specific attributes to the span."""
        if notification.params:
            # Add general params attribute
            if isinstance(notification.params, dict):
                span.set_attribute(
                    "notification_params", json.dumps(notification.params)
                )

            # Handle specific notification types
            if notification.method == "notifications/resources/updated" and isinstance(
                notification.params, dict
            ):
                if "uri" in notification.params:
                    span.set_attribute("resource_uri", str(notification.params["uri"]))

            elif notification.method == "notifications/progress" and isinstance(
                notification.params, dict
            ):
                if "progress" in notification.params:
                    span.set_attribute(
                        "progress_value", float(notification.params["progress"])
                    )
                if "total" in notification.params:
                    span.set_attribute(
                        "progress_total", float(notification.params["total"])
                    )

            elif notification.method == "notifications/cancelled" and isinstance(
                notification.params, dict
            ):
                if "requestId" in notification.params:
                    span.set_attribute(
                        "cancelled_requestId", str(notification.params["requestId"])
                    )
                if "reason" in notification.params:
                    span.set_attribute(
                        "cancelled_reason", str(notification.params["reason"])
                    )

    def _add_response_attributes(
        self, span: Span, response: types.JSONRPCResponse
    ) -> None:
        """Add response-specific attributes to the span."""
        # Add any relevant attributes from the response result
        if isinstance(response.result, dict):
            span.set_attribute("result", json.dumps(response.result))

    def record_http_error(self, span: Span, status_code: int, text: str) -> None:
        """Record HTTP error details in a span."""
        span.set_status(StatusCode.ERROR, f"HTTP status {status_code}")
        span.set_attribute("error_type", "http")
        span.set_attribute("error_status_code", status_code)
        span.set_attribute(
            "error_message", text[:1000] if text else ""
        )  # Limit error message length
        self._logger.error(f"HTTP error: {status_code} {text}")

    def record_exception(self, span: Span, exception: Exception) -> None:
        """Record exception details in a span."""
        span.set_status(StatusCode.ERROR, str(exception))
        span.set_attribute("error_type", "exception")
        span.set_attribute("error_class", exception.__class__.__name__)
        span.set_attribute(
            "error_message", str(exception)[:1000]
        )  # Limit error message length
        span.record_exception(exception)
        self._logger.error(f"Exception: {exception}", exc_info=True)

    def create_operation_span(self, operation_name: str, **context) -> Span:
        """Create a span for a general operation (not directly tied to a message)."""
        span = self._tracer.start_span(operation_name)

        for key, value in context.items():
            span.set_attribute(key, str(value))

        return span

    def get_current_span(self) -> Span:
        """Get the current active span."""
        return trace.get_current_span()

    def add_event_to_current_span(self, name: str, **attributes) -> None:
        """Add an event to the current span."""
        current_span = trace.get_current_span()
        current_span.add_event(name, attributes)
