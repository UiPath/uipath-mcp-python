"""Tests for the `uipath new` MCP middleware."""

from pathlib import Path
from unittest.mock import patch

import pytest
from uipath._cli.middlewares import MiddlewareResult

from uipath_mcp._cli import cli_new


def test_clean_directory_removes_only_py_files(tmp_path: Path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    cli_new.clean_directory(str(tmp_path))
    assert not (tmp_path / "a.py").exists()
    assert (tmp_path / "b.txt").exists()
    assert (tmp_path / "sub").exists()


def test_write_template_file_plain_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "tpl").write_text("hello")
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr("uipath_mcp._cli.cli_new.os.path.dirname", lambda _: str(src))
    cli_new.write_template_file(str(target), "tpl", "result.txt", None)
    assert (target / "result.txt").read_text() == "hello"


def test_write_template_file_with_replacements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "tpl").write_text("name=$name; v=$v")
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr("uipath_mcp._cli.cli_new.os.path.dirname", lambda _: str(src))
    cli_new.write_template_file(
        str(target), "tpl", "result.txt", [("$name", "svc"), ("$v", "1")]
    )
    assert (target / "result.txt").read_text() == "name=svc; v=1"


def test_generate_files_calls_write_three_times(tmp_path: Path):
    with patch.object(cli_new, "write_template_file") as wtf:
        cli_new.generate_files(str(tmp_path), "svc")
    assert wtf.call_count == 3


def test_mcp_new_middleware_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with (
        patch.object(cli_new, "clean_directory") as cd,
        patch.object(cli_new, "generate_files") as gf,
    ):
        result = cli_new.mcp_new_middleware("svc")
    assert isinstance(result, MiddlewareResult)
    assert result.should_continue is False
    cd.assert_called_once()
    gf.assert_called_once()


def test_mcp_new_middleware_error_returns_stacktrace_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    with (
        patch.object(cli_new, "clean_directory", side_effect=OSError("boom")),
        patch.object(cli_new.console, "error"),
    ):
        result = cli_new.mcp_new_middleware("svc")
    assert result.should_continue is False
    assert result.should_include_stacktrace is True
