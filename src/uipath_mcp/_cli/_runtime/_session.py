import asyncio
import logging
import tempfile
from typing import Optional

import mcp.types as types
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from opentelemetry import trace
from uipath import UiPath

from .._utils._config import McpServer
from ._tracer import McpTracer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class SessionServer:
    """Manages a server process for a specific session."""

    def __init__(self, server_config: McpServer, session_id: str):
        self._server_config = server_config
        self._session_id = session_id
        self._read_stream = None
        self._write_stream = None
        self._mcp_session = None
        self._run_task = None
        self._message_queue = asyncio.Queue()
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

    async def on_message_received(self) -> None:
        """Get new incoming messages from UiPath MCP Server."""
        response = self._uipath.api_client.request(
            "GET",
            f"mcp_/mcp/{self._server_config.name}/in/messages?sessionId={self._session_id}",
        )
        if response.status_code == 200:
            messages = response.json()
            for message in messages:
                logger.info(f"Received message: {message}")
                json_message = types.JSONRPCMessage.model_validate(message)
                with self._mcp_tracer.create_span_for_message(
                    json_message,
                    session_id=self._session_id,
                    server_name=self._server_config.name,
                ) as _:
                    await self._message_queue.put(json_message)

    async def stop(self) -> None:
        """Clean up resources and stop the server."""
        # Cancel the context task if it exists
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._run_task), timeout=2.0)
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
        with tempfile.TemporaryFile(mode='w+b') as stderr_temp:
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
                            message = await self._read_stream.receive()
                            await self._send_message(message)
                    finally:
                        # Cancel the consumer when we exit the loop
                        consumer_task.cancel()
                        try:
                            await consumer_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                logger.error(
                    f"Error in server process for session {self._session_id}: {e}",
                    exc_info=True,
                )
            finally:
                stderr_temp.seek(0)
                self._server_stderr_output = stderr_temp.read().decode('utf-8', errors='replace')
                # The context managers will handle cleanup of resources

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
                        await self._write_stream.send(message)
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

    async def _send_message(self, message: types.JSONRPCMessage) -> None:
        """Send new message to UiPath MCP Server."""
        with self._mcp_tracer.create_span_for_message(
            message, session_id=self._session_id, server_name=self._server_config.name
        ) as span:
            try:
                response = self._uipath.api_client.request(
                    "POST",
                    f"mcp_/mcp/{self._server_config.name}/out/message?sessionId={self._session_id}",
                    json=message.model_dump(),
                )
                if response.status_code == 202:
                    logger.info(
                        f"Outgoing message sent to UiPath MCP Server: {message}"
                    )
                else:
                    self._mcp_tracer.record_http_error(
                        span, response.status_code, response.text
                    )
            except Exception as e:
                self._mcp_tracer.record_exception(span, e)
                raise
