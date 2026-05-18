"""Tests for McpConfig and McpServer."""

import json
from pathlib import Path

import pytest

from uipath_mcp._cli._utils._config import McpConfig, McpServer


def test_server_defaults():
    s = McpServer("svc", {})
    assert s.name == "svc"
    assert s.type is None
    assert s.transport == "stdio"
    assert s.url is None
    assert s.command == "None"
    assert s.args == []
    assert s.env == {}
    assert s.file_path is None
    assert s.is_streamable_http is False


def test_server_streamable_http_and_args():
    s = McpServer(
        "svc",
        {
            "type": "remote",
            "transport": "streamable-http",
            "url": "https://x",
            "command": "node",
            "args": ["index.js"],
            "env": {},
        },
    )
    assert s.is_streamable_http is True
    assert s.file_path == "index.js"
    d = s.to_dict()
    assert d["transport"] == "streamable-http"
    assert d["url"] == "https://x"
    assert d["command"] == "node"
    assert "McpServer" in repr(s)


def test_server_env_overlay_from_os(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FOO", "from-env")
    s = McpServer("svc", {"env": {"FOO": "default", "BAR": "keep"}})
    assert s.env["FOO"] == "from-env"
    assert s.env["BAR"] == "keep"


def test_validate_server_name_ok():
    McpConfig.validate_server_name("good-name-1")


@pytest.mark.parametrize("bad", ["with space", "under_score", "dots.bad", ""])
def test_validate_server_name_bad(bad: str):
    with pytest.raises(ValueError):
        McpConfig.validate_server_name(bad)


def test_config_not_exists(tmp_path: Path):
    cfg = McpConfig(str(tmp_path / "missing.json"))
    assert cfg.exists is False
    assert cfg.get_servers() == []
    assert cfg.get_server_names() == []
    assert cfg.get_server("anything") is None


def test_config_load_and_lookup(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "servers": {
                    "alpha": {"command": "a", "args": ["a.py"]},
                    "beta": {"command": "b"},
                }
            }
        )
    )
    cfg = McpConfig(str(path))
    assert cfg.exists is True
    assert set(cfg.get_server_names()) == {"alpha", "beta"}
    assert len(cfg.get_servers()) == 2
    assert cfg.get_server("alpha").name == "alpha"  # type: ignore[union-attr]
    assert cfg.get_server("missing") is None
    raw = cfg.load_config()
    assert "servers" in raw


def test_config_single_server_returned_regardless_of_name(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"only": {"command": "x"}}}))
    cfg = McpConfig(str(path))
    assert cfg.get_server("does-not-matter").name == "only"  # type: ignore[union-attr]


def test_config_load_invalid_json(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        McpConfig(str(path))


def test_config_load_invalid_name(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"bad name": {}}}))
    with pytest.raises(ValueError):
        McpConfig(str(path))


def test_load_config_when_missing_raises(tmp_path: Path):
    cfg = McpConfig(str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        cfg.load_config()
