"""Tests for TokenRefresher."""

import base64
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uipath.platform.common import TokenData
from uipath.platform.common._config import UiPathApiConfig

from uipath_mcp._cli._runtime._token_refresh import (
    FALLBACK_REFRESH_INTERVAL,
    REFRESH_MARGIN_SECONDS,
    AuthStrategy,
    TokenRefresher,
)


def _make_jwt(exp: float | None = None) -> str:
    """Create a minimal fake JWT with an optional exp claim."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload: dict[str, object] = {"sub": "test"}
    if exp is not None:
        payload["exp"] = exp
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


def _make_uipath_mock(
    base_url: str = "https://cloud.uipath.com/org/tenant",
    secret: str = "mock_token",
) -> MagicMock:
    """Create a mock UiPath instance with the expected _config attribute."""
    mock = MagicMock()
    mock._config = UiPathApiConfig(base_url=base_url, secret=secret)
    return mock


class TestDetectStrategy:
    """Tests for _detect_strategy auth strategy detection."""

    def test_client_credentials_when_both_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Detects client_credentials when CLIENT_ID and CLIENT_SECRET are set."""
        monkeypatch.setenv("UIPATH_CLIENT_ID", "my-id")
        monkeypatch.setenv("UIPATH_CLIENT_SECRET", "my-secret")

        refresher = TokenRefresher(_make_uipath_mock())

        assert refresher.strategy == AuthStrategy.CLIENT_CREDENTIALS

    def test_oauth_when_auth_file_has_refresh_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Detects oauth when .auth.json contains a refresh_token."""
        mock_auth = MagicMock()
        mock_auth.refresh_token = "rt_abc123"

        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            return_value=mock_auth,
        ):
            refresher = TokenRefresher(_make_uipath_mock())

        assert refresher.strategy == AuthStrategy.OAUTH

    def test_none_when_no_credentials_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to NONE when neither client_credentials nor oauth is available."""
        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError("no auth file"),
        ):
            refresher = TokenRefresher(_make_uipath_mock())

        assert refresher.strategy == AuthStrategy.NONE


class TestSecondsUntilRefresh:
    """Tests for _seconds_until_refresh timing calculations."""

    def test_returns_time_minus_margin_for_valid_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns (remaining - margin) when exp claim is present."""
        exp = time.time() + 3600  # expires in 1 hour
        token = _make_jwt(exp=exp)

        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock(secret=token))

        result = refresher._seconds_until_refresh()

        expected = 3600 - REFRESH_MARGIN_SECONDS
        assert abs(result - expected) < 5  # allow small drift

    def test_returns_zero_when_token_nearly_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns 0 when token expires within the refresh margin."""
        exp = time.time() + 60  # expires in 60s, within 5-min margin
        token = _make_jwt(exp=exp)

        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock(secret=token))

        assert refresher._seconds_until_refresh() == 0

    def test_returns_fallback_when_token_has_no_exp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns fallback interval when exp claim is missing."""
        token = _make_jwt(exp=None)

        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock(secret=token))

        assert refresher._seconds_until_refresh() == FALLBACK_REFRESH_INTERVAL

    def test_returns_fallback_when_token_unparseable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns fallback interval when token cannot be parsed."""
        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock(secret="not-a-jwt"))

        assert refresher._seconds_until_refresh() == FALLBACK_REFRESH_INTERVAL


class TestPropagateToken:
    """Tests for _propagate_token updating config and env."""

    def test_updates_config_and_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token propagation updates both the UiPath config and env var."""
        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            mock_uipath = _make_uipath_mock()
            refresher = TokenRefresher(mock_uipath)

        token_data = TokenData(access_token="new_access_token_123")
        refresher._propagate_token(token_data)

        assert mock_uipath._config.secret == "new_access_token_123"
        assert os.environ.get("UIPATH_ACCESS_TOKEN") == "new_access_token_123"

    def test_preserves_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token propagation keeps the original base_url."""
        base_url = "https://my-instance.uipath.com/org/tenant"

        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            mock_uipath = _make_uipath_mock(base_url=base_url)
            refresher = TokenRefresher(mock_uipath)

        refresher._propagate_token(TokenData(access_token="refreshed"))

        assert mock_uipath._config.base_url == base_url


class TestStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_does_nothing_when_strategy_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """start() is a no-op when no auth strategy is available."""
        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock())

        assert refresher.strategy == AuthStrategy.NONE

        refresher.start()

        assert refresher._refresh_task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stop() completes cleanly when no task is running."""
        with patch(
            "uipath_mcp._cli._runtime._token_refresh.get_auth_data",
            side_effect=FileNotFoundError,
        ):
            refresher = TokenRefresher(_make_uipath_mock())

        await refresher.stop()

        assert refresher._refresh_task is None


class TestTryRefresh:
    """Tests for _try_refresh retry logic."""

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_refresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_try_refresh returns True when refresh succeeds on first attempt."""
        monkeypatch.setenv("UIPATH_CLIENT_ID", "my-id")
        monkeypatch.setenv("UIPATH_CLIENT_SECRET", "my-secret")

        refresher = TokenRefresher(_make_uipath_mock())
        token_data = TokenData(access_token="fresh_token")

        with patch.object(
            refresher,
            "_refresh_client_credentials",
            new_callable=AsyncMock,
            return_value=token_data,
        ):
            result = await refresher._try_refresh()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_after_all_retries_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_try_refresh returns False when all retry attempts fail."""
        monkeypatch.setenv("UIPATH_CLIENT_ID", "my-id")
        monkeypatch.setenv("UIPATH_CLIENT_SECRET", "my-secret")

        refresher = TokenRefresher(_make_uipath_mock())

        monkeypatch.setattr(
            "uipath_mcp._cli._runtime._token_refresh.RETRY_BASE_DELAY", 0
        )

        with patch.object(
            refresher,
            "_refresh_client_credentials",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection failed"),
        ):
            result = await refresher._try_refresh()

        assert result is False
