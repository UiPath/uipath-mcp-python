import asyncio
import logging
import os
import time
from enum import Enum

import httpx
from uipath._cli._auth._oidc_utils import OidcUtils
from uipath._cli._auth._url_utils import build_service_url, resolve_domain
from uipath._cli._auth._utils import get_auth_data, update_auth_file
from uipath._utils._auth import parse_access_token
from uipath._utils._ssl_context import get_httpx_client_kwargs
from uipath._utils.constants import ENV_UIPATH_ACCESS_TOKEN
from uipath.platform import UiPath
from uipath.platform.common import TokenData
from uipath.platform.common._config import UiPathApiConfig
from uipath.platform.identity import IdentityService

logger = logging.getLogger(__name__)

REFRESH_MARGIN_SECONDS = 300  # Refresh 5 minutes before expiry
FALLBACK_REFRESH_INTERVAL = 45 * 60  # 45 minutes when exp claim is unavailable
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 5  # seconds
RETRY_FALLBACK_INTERVAL = 60  # seconds to wait after all retries fail


class AuthStrategy(Enum):
    OAUTH = "oauth"
    CLIENT_CREDENTIALS = "client_credentials"
    NONE = "none"


class TokenRefresher:
    """Manages token refresh for long-lived MCP runtime connections."""

    def __init__(self, uipath: UiPath):
        self._uipath = uipath
        self._refresh_task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()

        self._client_id: str | None = os.environ.get("UIPATH_CLIENT_ID")
        self._client_secret: str | None = os.environ.get("UIPATH_CLIENT_SECRET")

        self._base_url: str = uipath._config.base_url
        self._domain: str = resolve_domain(self._base_url, environment=None)

        self._strategy = self._detect_strategy()
        self._token_url: str | None = self._resolve_token_url()

        if (
            self._strategy == AuthStrategy.CLIENT_CREDENTIALS
            and self._token_url is None
        ):
            logger.error("Token refresh disabled: could not resolve token URL")
            self._strategy = AuthStrategy.NONE

    def _detect_strategy(self) -> AuthStrategy:
        """Detect which auth flow is available for token refresh."""
        if self._client_id and self._client_secret:
            return AuthStrategy.CLIENT_CREDENTIALS

        try:
            auth_data = get_auth_data()
            if auth_data.refresh_token:
                return AuthStrategy.OAUTH
        except Exception as e:
            logger.debug(f"Could not read auth file for strategy detection: {e}")

        return AuthStrategy.NONE

    def _resolve_token_url(self) -> str | None:
        """Derive the identity token endpoint for client_credentials flow."""
        if self._strategy != AuthStrategy.CLIENT_CREDENTIALS:
            return None

        try:
            return build_service_url(self._domain, "/identity_/connect/token")
        except Exception as e:
            logger.error(
                f"Could not resolve token URL from base_url '{self._base_url}': {e}"
            )
            return None

    @property
    def strategy(self) -> AuthStrategy:
        return self._strategy

    def start(self) -> None:
        """Start the background refresh task."""
        if self._strategy == AuthStrategy.NONE:
            logger.info("No token refresh strategy available; refresh disabled")
            return

        self._cancel_event.clear()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("Token refresh background task started")

    async def stop(self) -> None:
        """Stop the background refresh task."""
        self._cancel_event.set()
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await asyncio.wait_for(self._refresh_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._refresh_task = None
        logger.info("Token refresh stopped")

    async def _wait_for_cancel(self, seconds: float) -> bool:
        """Sleep for `seconds`, returning True if cancellation was requested."""
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _refresh_loop(self) -> None:
        """Background loop that refreshes the token before expiry."""
        try:
            while not self._cancel_event.is_set():
                wait_seconds = self._seconds_until_refresh()
                if wait_seconds > 0 and await self._wait_for_cancel(wait_seconds):
                    break

                if not await self._try_refresh() and not self._cancel_event.is_set():
                    logger.error(
                        "All token refresh attempts failed. "
                        "The token may expire causing failures."
                    )
                    # Avoid retry loop when the token is already expired
                    if await self._wait_for_cancel(RETRY_FALLBACK_INTERVAL):
                        break
        except asyncio.CancelledError:
            logger.info("Token refresh loop cancelled")
            raise

    async def _try_refresh(self) -> bool:
        """Attempt to refresh the token with retries. Returns True on success."""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                if self._strategy == AuthStrategy.OAUTH:
                    token_data = await self._refresh_oauth()
                else:
                    token_data = await self._refresh_client_credentials()

                self._propagate_token(token_data)
                logger.info("Token refreshed successfully.")
                return True

            except Exception as e:
                safe_msg = (
                    f"HTTP {e.response.status_code}"
                    if isinstance(e, httpx.HTTPStatusError)
                    else type(e).__name__
                )
                logger.error(
                    f"Token refresh attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} "
                    f"failed: {safe_msg}"
                )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.info(f"Retrying in {RETRY_BASE_DELAY}s...")
                    if await self._wait_for_cancel(RETRY_BASE_DELAY):
                        return False

        return False

    async def _refresh_oauth(self) -> TokenData:
        """Refresh using OAuth refresh_token grant."""
        auth_data = get_auth_data()
        refresh_token = auth_data.refresh_token
        if not refresh_token:
            raise ValueError("No refresh_token found in .uipath/.auth.json")

        auth_config = await OidcUtils.get_auth_config(self._domain)
        client_id = auth_config["client_id"]

        identity_service = IdentityService(self._domain)
        token_data = await identity_service.refresh_access_token_async(
            refresh_token=refresh_token,
            client_id=client_id,
        )

        try:
            update_auth_file(token_data)
        except Exception as e:
            logger.warning(f"Failed to update .auth.json: {type(e).__name__}")

        return token_data

    async def _refresh_client_credentials(self) -> TokenData:
        """Refresh using client_credentials grant."""
        if self._token_url is None:
            raise RuntimeError("token_url must be set for client_credentials strategy")

        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": os.environ.get("UIPATH_CLIENT_SCOPE", "OR.Execution"),
        }

        async with httpx.AsyncClient(**get_httpx_client_kwargs()) as client:
            response = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return TokenData.model_validate(response.json())

    def _propagate_token(self, token_data: TokenData) -> None:
        """Update all token consumers after a successful refresh."""
        new_token = token_data.access_token

        self._uipath._config = UiPathApiConfig(
            base_url=self._uipath._config.base_url,
            secret=new_token,
        )

        os.environ[ENV_UIPATH_ACCESS_TOKEN] = new_token

    def _seconds_until_refresh(self) -> float:
        """Calculate seconds to wait before next refresh attempt."""
        try:
            claims = parse_access_token(self._uipath._config.secret)
            exp = claims.get("exp")
            if exp is not None:
                remaining = float(exp) - time.time()
                if remaining <= REFRESH_MARGIN_SECONDS:
                    return 0
                return remaining - REFRESH_MARGIN_SECONDS
        except Exception as e:
            logger.warning(f"Failed to parse token expiry: {e}")

        return FALLBACK_REFRESH_INTERVAL
