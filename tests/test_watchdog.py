import asyncio
import time

import pytest

from uipath_mcp._cli._runtime._session import SessionHealthInfo
from uipath_mcp._cli._runtime._watchdog import SessionWatchdog


class MockSessionProvider:
    """Mock provider for testing the watchdog."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionHealthInfo] = {}
        self.removed: list[tuple[str, str]] = []

    def get_sessions(self) -> dict[str, SessionHealthInfo]:
        return dict(self.sessions)

    async def remove_session(self, session_id: str, reason: str) -> None:
        self.removed.append((session_id, reason))
        self.sessions.pop(session_id, None)


def _make_health(
    session_id: str = "test-session",
    transport_type: str = "stdio",
    task_done: bool = False,
    task_exception: BaseException | None = None,
    last_activity_time: float | None = None,
    queue_size: int = 0,
) -> SessionHealthInfo:
    return SessionHealthInfo(
        session_id=session_id,
        transport_type=transport_type,
        task_done=task_done,
        task_exception=task_exception,
        last_activity_time=last_activity_time
        if last_activity_time is not None
        else time.monotonic(),
        queue_size=queue_size,
    )


@pytest.mark.asyncio
async def test_detects_dead_task_with_exception() -> None:
    """Watchdog should remove sessions whose task has finished with an exception."""
    provider = MockSessionProvider()
    provider.sessions["s1"] = _make_health(
        session_id="s1",
        task_done=True,
        task_exception=RuntimeError("boom"),
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 1
    assert provider.removed[0] == ("s1", "dead task")


@pytest.mark.asyncio
async def test_detects_dead_task_without_exception() -> None:
    """Watchdog should remove sessions whose task completed without exception."""
    provider = MockSessionProvider()
    provider.sessions["s1"] = _make_health(
        session_id="s1",
        task_done=True,
        task_exception=None,
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 1
    assert provider.removed[0] == ("s1", "dead task")


@pytest.mark.asyncio
async def test_detects_idle_timeout() -> None:
    """Watchdog should remove sessions that exceed the idle timeout."""
    provider = MockSessionProvider()
    provider.sessions["s1"] = _make_health(
        session_id="s1",
        task_done=False,
        last_activity_time=time.monotonic() - 1000,  # idle for 1000s
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 1
    assert provider.removed[0] == ("s1", "idle timeout")


@pytest.mark.asyncio
async def test_healthy_session_not_removed() -> None:
    """Watchdog should leave healthy, active sessions alone."""
    provider = MockSessionProvider()
    provider.sessions["s1"] = _make_health(
        session_id="s1",
        task_done=False,
        last_activity_time=time.monotonic(),  # just active
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 0
    assert "s1" in provider.sessions


@pytest.mark.asyncio
async def test_no_sessions_is_noop() -> None:
    """Watchdog should handle empty session list gracefully."""
    provider = MockSessionProvider()
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 0


@pytest.mark.asyncio
async def test_multiple_sessions_mixed() -> None:
    """Watchdog should handle a mix of healthy, dead, and idle sessions."""
    provider = MockSessionProvider()
    provider.sessions["healthy"] = _make_health(
        session_id="healthy", task_done=False, last_activity_time=time.monotonic()
    )
    provider.sessions["dead"] = _make_health(
        session_id="dead", task_done=True, task_exception=RuntimeError("crash")
    )
    provider.sessions["idle"] = _make_health(
        session_id="idle", task_done=False, last_activity_time=time.monotonic() - 2000
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    removed_ids = {r[0] for r in provider.removed}
    assert removed_ids == {"dead", "idle"}
    assert "healthy" in provider.sessions


@pytest.mark.asyncio
async def test_start_stop_lifecycle() -> None:
    """Watchdog should start and stop cleanly."""
    provider = MockSessionProvider()
    watchdog = SessionWatchdog(provider, check_interval=0.1, idle_timeout=900)

    watchdog.start()
    assert watchdog._task is not None
    assert not watchdog._task.done()

    await asyncio.sleep(0.15)  # let at least one cycle run

    await watchdog.stop()
    assert watchdog._task is None


@pytest.mark.asyncio
async def test_stop_when_not_started() -> None:
    """Stopping a watchdog that was never started should be a no-op."""
    provider = MockSessionProvider()
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog.stop()  # should not raise


@pytest.mark.asyncio
async def test_start_idempotent() -> None:
    """Calling start() twice should not create a second task."""
    provider = MockSessionProvider()
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    watchdog.start()
    first_task = watchdog._task
    watchdog.start()
    assert watchdog._task is first_task
    await watchdog.stop()


@pytest.mark.asyncio
async def test_error_in_remove_session_does_not_crash_watchdog() -> None:
    """Watchdog should survive errors from remove_session."""

    class FailingProvider(MockSessionProvider):
        async def remove_session(self, session_id: str, reason: str) -> None:
            raise RuntimeError("removal failed")

    provider = FailingProvider()
    provider.sessions["s1"] = _make_health(session_id="s1", task_done=True)
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)

    # Should not raise
    await watchdog._check_sessions()


@pytest.mark.asyncio
async def test_dead_task_prioritized_over_idle() -> None:
    """A dead task should be detected even if the session is also idle."""
    provider = MockSessionProvider()
    provider.sessions["s1"] = _make_health(
        session_id="s1",
        task_done=True,
        last_activity_time=time.monotonic() - 2000,
    )
    watchdog = SessionWatchdog(provider, check_interval=1, idle_timeout=900)
    await watchdog._check_sessions()

    assert len(provider.removed) == 1
    assert provider.removed[0] == ("s1", "dead task")  # dead task, not idle timeout


@pytest.mark.asyncio
async def test_transport_type_in_health_info() -> None:
    """SessionHealthInfo should carry the transport type."""
    stdio_health = _make_health(session_id="s1", transport_type="stdio")
    http_health = _make_health(session_id="s2", transport_type="streamable-http")

    assert stdio_health.transport_type == "stdio"
    assert http_health.transport_type == "streamable-http"
