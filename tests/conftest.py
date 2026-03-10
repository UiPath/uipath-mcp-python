import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean environment variables before each test."""
    monkeypatch.delenv("UIPATH_URL", raising=False)
    monkeypatch.delenv("UIPATH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("UIPATH_CLIENT_ID", raising=False)
    monkeypatch.delenv("UIPATH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("UIPATH_CLIENT_SCOPE", raising=False)
