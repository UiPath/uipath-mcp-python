"""Additional TokenRefresher tests covering loop, refresh flows, and lifecycle.

Identity/OAuth endpoints and the HTTP client are mocked; these assert the
refresher's own decision logic (strategy selection, retry/cancel, propagation),
not the real identity service contract.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from uipath.platform.common import TokenData
from uipath.platform.common._config import UiPathApiConfig

from uipath_mcp._cli._runtime._token_refresh import (
    AuthStrategy,
    TokenRefresher,
)

MODULE = "uipath_mcp._cli._runtime._token_refresh"


def _make_uipath_mock(
    base_url: str = "https://cloud.uipath.com/org/tenant",
    secret: str = "mock_token",
) -> MagicMock:
    mock = MagicMock()
    mock._config = UiPathApiConfig(base_url=base_url, secret=secret)
    return mock


def _client_creds_refresher(
    monkeypatch, *, token_url="https://id/token"
) -> TokenRefresher:
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "csecret")
    with patch(f"{MODULE}.build_service_url", return_value=token_url):
        return TokenRefresher(_make_uipath_mock())


def test_client_credentials_without_token_url_disables_refresh(monkeypatch):
    """CLIENT_CREDENTIALS with unresolvable token URL falls back to NONE."""
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "csecret")
    with patch(f"{MODULE}.build_service_url", side_effect=RuntimeError("no url")):
        refresher = TokenRefresher(_make_uipath_mock())
    assert refresher.strategy == AuthStrategy.NONE
    assert refresher._token_url is None


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle(monkeypatch):
    """start() spawns a task for a live strategy and stop() cancels it."""
    refresher = _client_creds_refresher(monkeypatch)
    assert refresher.strategy == AuthStrategy.CLIENT_CREDENTIALS

    with patch.object(refresher, "_refresh_loop", new=AsyncMock()):
        refresher.start()
        assert refresher._refresh_task is not None
        await refresher.stop()

    assert refresher._refresh_task is None


@pytest.mark.asyncio
async def test_wait_for_cancel_times_out(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    # cancel event never set -> times out and returns False
    assert await refresher._wait_for_cancel(0.01) is False


@pytest.mark.asyncio
async def test_wait_for_cancel_returns_true_when_set(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    refresher._cancel_event.set()
    assert await refresher._wait_for_cancel(1.0) is True


@pytest.mark.asyncio
async def test_refresh_loop_success_then_cancel(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)

    async def fake_try() -> bool:
        refresher._cancel_event.set()
        return True

    with (
        patch.object(refresher, "_seconds_until_refresh", return_value=0),
        patch.object(refresher, "_try_refresh", side_effect=fake_try) as tr,
    ):
        await refresher._refresh_loop()

    tr.assert_awaited_once()
    assert refresher._cancel_event.is_set()


@pytest.mark.asyncio
async def test_refresh_loop_waits_then_cancel(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    with (
        patch.object(refresher, "_seconds_until_refresh", return_value=5),
        patch.object(
            refresher, "_wait_for_cancel", new=AsyncMock(return_value=True)
        ) as wc,
        patch.object(refresher, "_try_refresh", new=AsyncMock()) as tr,
    ):
        await refresher._refresh_loop()

    wc.assert_awaited_once_with(5)
    tr.assert_not_awaited()  # broke during the pre-refresh wait, never refreshed


@pytest.mark.asyncio
async def test_refresh_loop_all_attempts_fail_then_break(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    with (
        patch.object(refresher, "_seconds_until_refresh", return_value=0),
        patch.object(
            refresher, "_try_refresh", new=AsyncMock(return_value=False)
        ) as tr,
        patch.object(
            refresher, "_wait_for_cancel", new=AsyncMock(return_value=True)
        ) as wc,
    ):
        await refresher._refresh_loop()

    tr.assert_awaited_once()
    # after all attempts fail it waits the fallback interval, then breaks
    wc.assert_awaited_once_with(60)


@pytest.mark.asyncio
async def test_refresh_loop_propagates_cancelled(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    with (
        patch.object(refresher, "_seconds_until_refresh", return_value=5),
        patch.object(
            refresher,
            "_wait_for_cancel",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await refresher._refresh_loop()


@pytest.mark.asyncio
async def test_try_refresh_oauth_success(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    refresher._strategy = AuthStrategy.OAUTH
    token = TokenData(access_token="new")
    with (
        patch.object(refresher, "_refresh_oauth", new=AsyncMock(return_value=token)),
        patch.object(refresher, "_propagate_token") as prop,
    ):
        assert await refresher._try_refresh() is True
    prop.assert_called_once_with(token)


@pytest.mark.asyncio
async def test_try_refresh_retries_then_cancel(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    with (
        patch.object(
            refresher,
            "_refresh_client_credentials",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "x", request=MagicMock(), response=MagicMock(status_code=401)
                )
            ),
        ),
        patch.object(refresher, "_wait_for_cancel", new=AsyncMock(return_value=True)),
    ):
        assert await refresher._try_refresh() is False


@pytest.mark.asyncio
async def test_refresh_oauth_flow(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    auth = MagicMock()
    auth.refresh_token = "rt"
    token = TokenData(access_token="oauth-token")
    identity = MagicMock()
    identity.refresh_access_token_async = AsyncMock(return_value=token)
    with (
        patch(f"{MODULE}.get_auth_data", return_value=auth),
        patch(
            f"{MODULE}.OidcUtils.get_auth_config",
            new=AsyncMock(return_value={"client_id": "abc"}),
        ),
        patch(f"{MODULE}.IdentityService", return_value=identity),
        patch(f"{MODULE}.update_auth_file", side_effect=RuntimeError("write fail")),
    ):
        result = await refresher._refresh_oauth()
    assert result is token


@pytest.mark.asyncio
async def test_refresh_oauth_without_refresh_token_raises(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    auth = MagicMock()
    auth.refresh_token = None
    with patch(f"{MODULE}.get_auth_data", return_value=auth):
        with pytest.raises(ValueError, match="refresh_token"):
            await refresher._refresh_oauth()


@pytest.mark.asyncio
async def test_refresh_client_credentials_flow(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"access_token": "cc-token"})
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{MODULE}.httpx.AsyncClient", return_value=cm),
        patch(f"{MODULE}.get_httpx_client_kwargs", return_value={}),
    ):
        result = await refresher._refresh_client_credentials()

    assert result.access_token == "cc-token"
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_client_credentials_without_url_raises(monkeypatch):
    refresher = _client_creds_refresher(monkeypatch)
    refresher._token_url = None
    with pytest.raises(RuntimeError, match="token_url"):
        await refresher._refresh_client_credentials()
