import asyncio
import logging

import mcp.types as types
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from pysignalr.client import SignalRClient

from .._utils._config import McpServer

logger = logging.getLogger(__name__)


class SessionServer:
    """Manages a server process for a specific session."""

    def __init__(self, server_config: McpServer, session_id: str):
        self.server_config = server_config
        self.session_id = session_id
        self.read_stream = None
        self.write_stream = None
        self.mcp_session = None
        self.running = False
        self.context_task = None
        self._message_queue = asyncio.Queue()

    async def start(self, signalr_client: SignalRClient) -> None:
        """Start the server process in a separate task."""
        if self.running:
            logger.info(f"Session {self.session_id} already running")
            return

        logger.info(f"Starting session {self.session_id}")
        try:
            server_params = StdioServerParameters(
                command=self.server_config.command,
                args=self.server_config.args,
                env=None,
            )

            # Start the server process in a separate task
            self.running = True
            self.context_task = asyncio.create_task(
                self._run_server(server_params, signalr_client)
            )
            self.context_task.add_done_callback(self._on_task_done)

        except Exception as e:
            logger.error(
                f"Error starting session {self.session_id}: {e}", exc_info=True
            )
            await self.cleanup()
            raise

    async def _run_server(
        self, server_params: StdioServerParameters, signalr_client: SignalRClient
    ) -> None:
        """Run the server in proper context managers."""
        logger.info(f"Starting server process for session {self.session_id}")
        try:
            async with stdio_client(server_params) as (read, write):
                self.read_stream, self.write_stream = read, write
                logger.info(f"Session {self.session_id} - stdio client started")

                logger.info(f"Session {self.session_id} - MCP session initialized")

                # Start the message consumer task
                consumer_task = asyncio.create_task(self._consume_messages())

                # Process incoming messages from the server
                try:
                    while True:
                        print("Waiting for messages...")
                        message = await self.read_stream.receive()
                        json_str = message.model_dump_json()
                        print(f"Received message from local server: {json_str}")
                        logger.debug(
                            f"Session {self.session_id} - sending to SignalR: {json_str[:100]}..."
                        )
                        await signalr_client.send(
                            "OnMessageReceived", [self.session_id, json_str]
                        )
                finally:
                    # Cancel the consumer when we exit the loop
                    consumer_task.cancel()
                    try:
                        await consumer_task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            logger.error(
                f"Error in server process for session {self.session_id}: {e}",
                exc_info=True,
            )
        finally:
            # The context managers will handle cleanup of resources
            logger.info(f"Server process for session {self.session_id} has ended")
            self.read_stream = None
            self.write_stream = None
            self.mcp_session = None

    def _on_task_done(self, task):
        """Handle task completion."""
        try:
            # Get the result to propagate any exceptions
            task.result()
        except asyncio.CancelledError:
            logger.info(f"Server task for session {self.session_id} was cancelled")
        except Exception as e:
            logger.error(
                f"Server task for session {self.session_id} failed: {e}", exc_info=True
            )
        finally:
            # Mark as not running when the task is done
            self.running = False

    async def _consume_messages(self):
        """Consume messages from the queue and send them to the server."""
        try:
            while True:
                message = await self._message_queue.get()
                try:
                    if self.write_stream:
                        if isinstance(message, dict):
                            json_message = types.JSONRPCMessage.model_validate(message)
                        elif isinstance(message, str):
                            json_message = types.JSONRPCMessage.model_validate_json(
                                message
                            )
                        logger.info(
                            f"Session {self.session_id} - processing queued message: {json_message}..."
                        )
                        await self.write_stream.send(json_message)
                        logger.info(
                            f"Session {self.session_id} - message sent to local server"
                        )
                except Exception as e:
                    logger.error(
                        f"Error processing message for session {self.session_id}: {e}"
                    )
                finally:
                    self._message_queue.task_done()
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            logger.info(f"Message consumer for session {self.session_id} was cancelled")
            # Process any remaining messages in the queue
            while not self._message_queue.empty():
                try:
                    message = self._message_queue.get_nowait()
                    self._message_queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def send_message(self, message: str) -> None:
        """Queue a message to be sent to the server."""
        if not self.running:
            logger.warning(
                f"Cannot send message: session {self.session_id} is not running"
            )
            return

        # Add the message to the queue for processing
        await self._message_queue.put(message)
        logger.debug(f"Session {self.session_id} - message queued for processing")

    async def cleanup(self) -> None:
        """Clean up resources and stop the server."""
        logger.info(f"Cleaning up session {self.session_id}")

        # Mark as not running first
        self.running = False

        # Cancel the context task if it exists
        if self.context_task and not self.context_task.done():
            logger.info(f"Cancelling server task for session {self.session_id}")
            self.context_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.context_task), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning(
                    f"Timed out waiting for server task to cancel for session {self.session_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error during task cancellation for session {self.session_id}: {e}"
                )

        # The context managers in _run_server will handle resource cleanup
        self.context_task = None
        self.read_stream = None
        self.write_stream = None
        self.mcp_session = None
        logger.info(f"Cleanup completed for session {self.session_id}")
