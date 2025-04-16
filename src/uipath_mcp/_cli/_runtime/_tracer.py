import json
import logging
from typing import Optional, TypeVar

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
        self.tracer = tracer or trace.get_tracer(__name__)
        self.logger = logger or logging.getLogger(__name__)

    def create_span_for_message(
        self, message: types.JSONRPCMessage, **context
    ) -> Span:
        """Create and configure a span for a message.

        Args:
            message: The JSON-RPC message
            span_name: The name to use for the span
            **context: Additional context attributes to add to the span

        Returns:
            A configured OpenTelemetry span
        """
        root_value = message.root

        if isinstance(root_value, types.JSONRPCRequest):
            span = self.tracer.start_span(root_value.method)
            span.set_attribute("type", "request")
            span.set_attribute("id", str(root_value.id))
            span.set_attribute("method", root_value.method)
            self._add_request_attributes(span, root_value)

        elif isinstance(root_value, types.JSONRPCNotification):
            span = self.tracer.start_span(root_value.method)
            span.set_attribute("type", "notification")
            span.set_attribute("method", root_value.method)
            self._add_notification_attributes(span, root_value)

        elif isinstance(root_value, types.JSONRPCResponse):
            span = self.tracer.start_span("response")
            span.set_attribute("type", "response")
            span.set_attribute("id", str(root_value.id))
            self._add_response_attributes(span, root_value)

        elif isinstance(root_value, types.JSONRPCError):
            span = self.tracer.start_span("error")
            span.set_attribute("type", "error")
            span.set_attribute("id", str(root_value.id))
            span.set_attribute("error_code", root_value.error.code)
            span.set_attribute("error_message", root_value.error.message)
        else:
            span = self.tracer.start_span("unknown")
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
                span.set_attribute("params", json.dumps(request.params))

            # Handle specific request types based on method
            if request.method == "tools/call" and isinstance(request.params, dict):
                if "name" in request.params:
                    span.set_attribute("tool_name", request.params["name"])
                if "arguments" in request.params and isinstance(
                    request.params["arguments"], dict
                ):
                    span.set_attribute(
                        "tool_args", json.dumps(request.params["arguments"])
                    )

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
        self.logger.error(f"HTTP error: {status_code} {text}")

    def record_exception(self, span: Span, exception: Exception) -> None:
        """Record exception details in a span."""
        span.set_status(StatusCode.ERROR, str(exception))
        span.set_attribute("error_type", "exception")
        span.set_attribute("error_class", exception.__class__.__name__)
        span.set_attribute(
            "error_message", str(exception)[:1000]
        )  # Limit error message length
        span.record_exception(exception)
        self.logger.error(f"Exception: {exception}", exc_info=True)

    def create_operation_span(self, operation_name: str, **context) -> Span:
        """Create a span for a general operation (not directly tied to a message)."""
        span = self.tracer.start_span(operation_name)

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
