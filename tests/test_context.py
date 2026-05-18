"""Tests for UiPathServerType enum."""

import pytest

from uipath_mcp._cli._runtime._context import UiPathServerType


def test_enum_values():
    assert UiPathServerType.UiPath.value == 0
    assert UiPathServerType.Command.value == 1
    assert UiPathServerType.Coded.value == 2
    assert UiPathServerType.SelfHosted.value == 3


@pytest.mark.parametrize(
    "name",
    ["UiPath", "Command", "Coded", "SelfHosted"],
)
def test_from_string_valid(name: str):
    assert UiPathServerType.from_string(name) == UiPathServerType[name]


def test_from_string_invalid():
    with pytest.raises(ValueError, match="Unknown server type"):
        UiPathServerType.from_string("Nope")


@pytest.mark.parametrize(
    "server_type",
    list(UiPathServerType),
)
def test_get_description_known(server_type: UiPathServerType):
    desc = UiPathServerType.get_description(server_type)
    assert isinstance(desc, str)
    assert desc != "Unknown server type"


def test_get_description_unknown():
    assert UiPathServerType.get_description("not-an-enum") == "Unknown server type"  # type: ignore[arg-type]
