"""Tests for the binary diagnostics helper."""

import subprocess
from unittest.mock import patch

from uipath_mcp._cli._utils._diagnose import diagnose_binary

MODULE = "uipath_mcp._cli._utils._diagnose"


def test_missing_file_returns_error():
    with patch(f"{MODULE}.os.path.exists", return_value=False):
        result = diagnose_binary("/no/such/file")
    assert result == "Error: /no/such/file does not exist"


def test_non_linux_file_command_success():
    """Windows/mac path: file type resolved, Linux ELF block skipped."""
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="AMD64"),
        patch(f"{MODULE}.platform.system", return_value="Windows"),
        patch(
            f"{MODULE}.subprocess.check_output",
            return_value="PE32+ executable (console) x86-64\n",
        ),
    ):
        result = diagnose_binary("/bin/app.exe")
    assert "incompatible" in result


def test_file_command_not_found():
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Windows"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=FileNotFoundError(),
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "incompatible" in result


def test_file_command_process_error():
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Darwin"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "file"),
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "incompatible" in result


def test_linux_elf_x86_64_arch_mismatch():
    """ELF x86-64 binary on a non-x86_64 host reports the arch mismatch."""
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="aarch64"),
        patch(f"{MODULE}.platform.system", return_value="Linux"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=[
                "ELF 64-bit LSB executable, x86-64\n",
                "  Machine: Advanced Micro Devices X86-64\n",
            ],
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "x86_64 architecture" in result
    assert "aarch64" in result


def test_linux_readelf_no_machine_line():
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Linux"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=[
                "ELF 64-bit LSB executable, x86-64\n",
                "no arch details here\n",
            ],
        ),
    ):
        result = diagnose_binary("/bin/app")
    # x86_64 host + x86-64 binary => no mismatch, falls through to generic msg
    assert "incompatible" in result


def test_linux_readelf_process_error():
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Linux"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=[
                "ELF 64-bit LSB executable, x86-64\n",
                subprocess.CalledProcessError(1, "readelf"),
            ],
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "incompatible" in result


def test_linux_readelf_not_found():
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Linux"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=[
                "ELF 64-bit LSB executable, x86-64\n",
                FileNotFoundError(),
            ],
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "incompatible" in result


def test_linux_elf_arm_mismatch():
    """ARM binary on an x86_64 host reports the ARM mismatch."""
    with (
        patch(f"{MODULE}.os.path.exists", return_value=True),
        patch(f"{MODULE}.platform.machine", return_value="x86_64"),
        patch(f"{MODULE}.platform.system", return_value="Linux"),
        patch(
            f"{MODULE}.subprocess.check_output",
            side_effect=[
                "ELF 32-bit LSB executable, ARM\n",
                "  Machine: ARM\n",
            ],
        ),
    ):
        result = diagnose_binary("/bin/app")
    assert "ARM architecture" in result
    assert "x86_64" in result
