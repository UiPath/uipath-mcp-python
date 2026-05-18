"""Tests for the middleware registration entry point."""

from unittest.mock import patch

from uipath._cli.middlewares import Middlewares

from uipath_mcp import middlewares


def test_register_middleware_registers_new():
    with patch.object(Middlewares, "register") as reg:
        middlewares.register_middleware()
    reg.assert_called_once()
    args, _ = reg.call_args
    assert args[0] == "new"
