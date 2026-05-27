import asyncio
import logging
import time
from typing import Protocol

from opentelemetry import trace

from ._session import SessionHealthInfo

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

WATCHDOG_CHECK_INTERVAL = 30  # seconds
SESSION_IDLE_TIMEOUT = 3600  # 1 hour


class SessionProvider(Protocol):
    """Protocol for accessing and managing sessions."""

    def get_sessions(self) -> dict[str, SessionHealthInfo]: ...

    async def remove_session(self, session_id: str, reason: str) -> None: ...


class SessionWatchdog:
    """Periodically checks session health and removes dead or idle sessions."""

    def __init__(
        self,
        provider: SessionProvider,
        check_interval: float = WATCHDOG_CHECK_INTERVAL,
        idle_timeout: float = SESSION_IDLE_TIMEOUT,
    ):
        self._provider = provider
        self._check_interval = check_interval
        self._idle_timeout = idle_timeout
        self._task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()

    def start(self) -> None:
        """Start the watchdog background task."""
        if self._task is not None:
            return
        self._cancel_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("Session watchdog started")

    async def stop(self) -> None:
        """Stop the watchdog background task."""
        if self._task is None:
            return
        self._cancel_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Session watchdog stopped")

    async def _run(self) -> None:
        """Main watchdog loop."""
        try:
            while not self._cancel_event.is_set():
                try:
                    await self._check_sessions()
                except Exception:
                    logger.error("Error during watchdog check cycle", exc_info=True)

                try:
                    await asyncio.wait_for(
                        self._cancel_event.wait(), timeout=self._check_interval
                    )
                    break  # cancel_event was set
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("Session watchdog task cancelled")
            raise

    async def _check_sessions(self) -> None:
        """Inspect all sessions and remove dead or idle ones."""
        with tracer.start_as_current_span("watchdog.check_sessions") as span:
            sessions = self._provider.get_sessions()

            if not sessions:
                logger.debug("Watchdog check: no active sessions")
                span.set_attribute("session_count", 0)
                return

            now = time.monotonic()
            removed_count = 0

            for session_id, health in sessions.items():
                try:
                    transport = health.transport_type
                    if health.task_done:
                        if health.task_exception is not None:
                            logger.error(
                                f"Watchdog: {transport} session {session_id} task failed "
                                f"with exception: {health.task_exception}"
                            )
                        else:
                            logger.info(
                                f"Watchdog: {transport} session {session_id} task "
                                f"completed, cleaning up"
                            )
                        await self._provider.remove_session(
                            session_id, reason="dead task"
                        )
                        removed_count += 1
                        continue

                    idle_duration = now - health.last_activity_time
                    if idle_duration > self._idle_timeout:
                        logger.warning(
                            f"Watchdog: {transport} session {session_id} idle for "
                            f"{idle_duration:.0f}s (timeout: {self._idle_timeout}s)"
                        )
                        await self._provider.remove_session(
                            session_id, reason="idle timeout"
                        )
                        removed_count += 1
                except Exception:
                    logger.error(
                        f"Watchdog: error checking session {session_id}",
                        exc_info=True,
                    )

            span.set_attribute("session_count", len(sessions))
            span.set_attribute("removed_count", removed_count)
            logger.info(
                f"Watchdog check: {len(sessions)} session(s), {removed_count} removed"
            )
