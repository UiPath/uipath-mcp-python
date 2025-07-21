import asyncio
import io
import logging
import tempfile
from typing import Dict, Optional

from mcp import StdioServerParameters, stdio_client
from mcp.shared.message import SessionMessage
from mcp.types import (
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCResponse,
)
from opentelemetry import trace
from uipath import UiPath

from .._utils._config import McpServer
from ._tracer import McpTracer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1


class SessionServer:
    """Manages a server process for a specific session."""

    def __init__(self, server_config: McpServer, server_slug: str, session_id: str):
        self._server_config = server_config
        self._server_slug = server_slug
        self._session_id = session_id
        self._read_stream = None
        self._write_stream = None
        self._mcp_session = None
        self._run_task: Optional[asyncio.Task[None]] = None
        self._message_queue: asyncio.Queue[JSONRPCMessage] = asyncio.Queue()
        self._active_requests: Dict[str, str] = {}
        self._last_request_id: Optional[str] = None
        self._last_message_id: Optional[str] = None
        self._uipath = UiPath()
        self._mcp_tracer = McpTracer(tracer, logger)
        self._server_stderr_output: Optional[str] = None

    @property
    def output(self) -> Optional[str]:
        """Returns the captured stderr output from the MCP server process."""
        return self._server_stderr_output

    async def start(self) -> None:
        """Start the server process in a separate task."""
        try:
            server_params = StdioServerParameters(
                command=self._server_config.command,
                args=self._server_config.args,
                env=self._server_config.env,
            )

            # Start the server process in a separate task
            self._run_task = asyncio.create_task(self._run_server(server_params))
            self._run_task.add_done_callback(self._run_server_callback)

        except Exception as e:
            logger.error(
                f"Error starting session {self._session_id}: {e}", exc_info=True
            )
            await self.stop()
            raise

    async def on_message_received(self, request_id: str) -> None:
        """Get new incoming messages from UiPath MCP Server."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                await self._get_messages_internal(request_id)
                break
            except Exception as e:
                logger.error(
                    f"Error receiving messages for session {self._session_id}: {e}",
                    exc_info=True,
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(
                        f"Max retries reached for receiving messages in session {self._session_id}"
                    )
                    raise

    async def stop(self) -> None:
        """Clean up resources and stop the server."""
        # Cancel the context task if it exists
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._run_task), timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception as e:
                logger.error(
                    f"Error during task cancellation for session {self._session_id}: {e}"
                )

        # The context managers in _run_server will handle resource cleanup
        self._run_task = None
        self._read_stream = None
        self._write_stream = None
        self._mcp_session = None

    async def _run_server(self, server_params: StdioServerParameters) -> None:
        """Run the local MCP server process."""
        logger.info(f"Starting local MCP Server process for session {self._session_id}")
        self._server_stderr_output = None
        with tempfile.TemporaryFile(mode="w+b") as stderr_temp_binary:
            stderr_temp = io.TextIOWrapper(stderr_temp_binary, encoding="utf-8")
            try:
                async with stdio_client(server_params, errlog=stderr_temp) as (
                    read,
                    write,
                ):
                    self._read_stream, self._write_stream = read, write

                    # Start the message consumer task
                    consumer_task = asyncio.create_task(self._consume_messages())

                    # Process incoming messages from the local server
                    try:
                        while True:
                            # Get message from local server
                            session_message = None
                            try:
                                if self._read_stream is None:
                                    logger.error("Read stream is not initialized")
                                    break

                                session_message = await self._read_stream.receive()
                                if isinstance(session_message, Exception):
                                    logger.error(f"Received error: {session_message}")
                                    continue
                                message = session_message.message
                                # For responses, determine which request_id to use
                                if self._is_response(message):
                                    message_id = self._get_message_id(message)
                                    if (
                                        message_id
                                        and message_id in self._active_requests
                                    ):
                                        # Use the stored request_id for this response
                                        request_id = self._active_requests[message_id]
                                        # Send with the matched request_id
                                        await self._send_message(message, request_id)
                                        # Clean up the mapping after use
                                        del self._active_requests[message_id]
                                    else:
                                        # If no mapping found, use the last known request_id
                                        if self._last_request_id is not None:
                                            await self._send_message(
                                                message, self._last_request_id
                                            )
                                else:
                                    # For non-responses, use the last known request_id
                                    if self._last_request_id is not None:
                                        await self._send_message(
                                            message, self._last_request_id
                                        )
                            except Exception as e:
                                if session_message:
                                    logger.info(session_message)
                                logger.error(
                                    f"Error processing message for session {self._session_id}: {e}",
                                    exc_info=True,
                                )
                                if self._last_request_id is not None:
                                    await self._send_message(
                                        JSONRPCMessage(
                                            root=JSONRPCError(
                                                jsonrpc="2.0",
                                                # Use the last known message id for error reporting
                                                id=self._last_message_id,
                                                error=ErrorData(
                                                    code=-32000,
                                                    message=f"Error processing message: {e}",
                                                ),
                                            )
                                        ),
                                        self._last_request_id,
                                    )
                                continue
                    finally:
                        # Cancel the consumer when we exit the loop
                        consumer_task.cancel()
                        try:
                            await asyncio.wait_for(consumer_task, timeout=2.0)
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass

            except* Exception as eg:
                for exception in eg.exceptions:
                    logger.error(
                        f"Unexpected error for session {self._session_id}: {exception}",
                        exc_info=True,
                    )
            finally:
                stderr_temp.seek(0)
                self._server_stderr_output = stderr_temp.read()
                logger.error(self._server_stderr_output)

    def _run_server_callback(self, task):
        """Handle task completion."""
        try:
            # Get the result to propagate any exceptions
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Server task for session {self._session_id} failed: {e}", exc_info=True
            )

    async def _consume_messages(self):
        """Consume messages from the queue and send them to the local server."""
        try:
            while True:
                message = await self._message_queue.get()
                try:
                    if self._write_stream:
                        logger.info(
                            f"Session {self._session_id} - processing queued message: {message}..."
                        )
                        await self._write_stream.send(SessionMessage(message=message))
                except Exception as e:
                    logger.error(
                        f"Error processing message for session {self._session_id}: {e}"
                    )
                finally:
                    self._message_queue.task_done()
        except asyncio.CancelledError:
            # Process any remaining messages in the queue
            while not self._message_queue.empty():
                try:
                    message = self._message_queue.get_nowait()
                    self._message_queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def _send_message(self, message: JSONRPCMessage, request_id: str) -> None:
        """Send new message to UiPath MCP Server."""
        with self._mcp_tracer.create_span_for_message(
            message,
            session_id=self._session_id,
            request_id=request_id,
            server_name=self._server_slug,
        ) as _:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    await self._send_message_internal(message, request_id)
                    break
                except Exception as e:
                    logger.error(
                        f"Error sending message to UiPath MCP Server for session {self._session_id}: {e}",
                        exc_info=True,
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(
                            f"Max retries reached for sending message in session {self._session_id}"
                        )
                        raise

    async def _send_message_internal(
        self, message: JSONRPCMessage, request_id: str
    ) -> None:
        response = await self._uipath.api_client.request_async(
            "POST",
            f"agenthub_/mcp/{self._server_slug}/out/message?sessionId={self._session_id}&requestId={request_id}",
            json=message.model_dump(),
        )
        if response.status_code == 202:
            logger.info(f"Outgoing message sent to UiPath MCP Server: {message}")
        elif 500 <= response.status_code < 600:
            raise Exception(f"{response.status_code} - {response.text}")

    async def _get_messages_internal(self, request_id: str) -> None:
        response = await self._uipath.api_client.request_async(
            "GET",
            f"agenthub_/mcp/{self._server_slug}/in/messages?sessionId={self._session_id}&requestId={request_id}",
        )
        if response.status_code == 200:
            self._last_request_id = request_id
            messages = response.json()
            for message in messages:
                logger.info(f"Received message: {message}")
                json_message = JSONRPCMessage.model_validate(message)
                if self._is_request(json_message):
                    message_id = self._get_message_id(json_message)
                    if message_id:
                        self._last_message_id = message_id
                        self._active_requests[message_id] = request_id
                with self._mcp_tracer.create_span_for_message(
                    json_message,
                    session_id=self._session_id,
                    request_id=request_id,
                    server_name=self._server_slug,
                ) as _:
                    await self._message_queue.put(json_message)
        elif 500 <= response.status_code < 600:
            raise Exception(f"{response.status_code} - {response.text}")

    def _is_request(self, message: JSONRPCMessage) -> bool:
        """Check if a message is a JSONRPCRequest."""
        if hasattr(message, "root"):
            root = message.root
            return isinstance(root, JSONRPCRequest)
        return False

    def _is_response(self, message: JSONRPCMessage) -> bool:
        """Check if a message is a JSONRPCResponse or JSONRPCError."""
        if hasattr(message, "root"):
            root = message.root
            return isinstance(root, JSONRPCResponse) or isinstance(root, JSONRPCError)
        return False

    def _get_message_id(self, message: JSONRPCMessage) -> str:
        """Extract the message id from a JSONRPCMessage."""
        if hasattr(message, "root") and hasattr(message.root, "id"):
            return str(message.root.id)
        return ""
