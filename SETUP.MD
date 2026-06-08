# SETUP.MD

This file documents how to provision a clean development environment for `uipath-mcp`, run the build, execute the tests, and validate a sample code change end-to-end. It is intended both as a quick reference for human contributors and as a structured guide for automated environment-setup tooling.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 0.5+

### Supported platforms

`uv` is shell- and OS-agnostic, so the commands below run unchanged on every supported platform:

- [x] Linux
- [x] Windows
- [x] macOS

## Environment Variables

### Standard

None required for environment setup, build, or unit tests.

### Project-specific

None. The unit-test suite under the `Test` section below runs fully offline and requires no external authentication.

> **All commands below must be run from the repository root.** The `uv` invocations resolve `pyproject.toml`, `src/`, and `tests/` relative to the current working directory. The first line of `## Setup` enforces this by `cd`-ing to the git root.

## Setup

```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m pip install --upgrade uv
uv sync --all-extras
```

## Verify Setup

```bash
uv --version
uv run python --version
uv run python -c "import uipath_mcp; print('uipath_mcp ok')"
```

## Build

N/A

## Test

```bash
uv run pytest
```

## Sample Code Change

### The change

Add a new `server_count` property to `McpConfig` in `src/uipath_mcp/_cli/_utils/_config.py`, immediately after the existing `get_server_names` method:

```python
@property
def server_count(self) -> int:
    """Number of MCP servers currently loaded from configuration."""
    return len(self._servers)
```

Then create `tests/test_config_server_count.py` with two pytest tests:

```python
"""Tests for McpConfig.server_count."""

import json
from pathlib import Path

from uipath_mcp._cli._utils._config import McpConfig


def test_server_count_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({"servers": {}}))
    cfg = McpConfig(str(config_path))
    assert cfg.server_count == 0


def test_server_count_multiple(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": {
                    "alpha": {"command": "node", "args": ["alpha.js"]},
                    "beta": {"command": "node", "args": ["beta.js"]},
                }
            }
        )
    )
    cfg = McpConfig(str(config_path))
    assert cfg.server_count == 2
```

### Verification

```bash
uv run pytest tests/test_config_server_count.py -v
```

## Test with a real UiPath Coded MCP

The unit tests above are necessary but not sufficient — they don't exercise the package end-to-end. The flow below validates changes against a live runtime:

1. Apply the code changes locally.
2. Run the unit tests (see the `Sample Code Change` section above).
3. Scaffold a coded UiPath MCP that exercises the changed code path.
4. In the downstream project's `pyproject.toml`, add this local library as an editable dependency:

   ```toml
   [tool.uv.sources]
   uipath-mcp = { path = "../path/to/uipath-mcp-python", editable = true }
   ```

5. Exercise the new behavior end-to-end:

   ```bash
   uv run uipath run <mcp-name> --input '{...}'
   ```

6. (Optional) Open a PR and apply the `build:dev` label — this publishes the development version to Test PyPI.
7. The PR description is updated automatically with instructions for pointing the downstream MCP at the Test PyPI dev version.
8. Push the dev version to UiPath with [`uipath push`](https://uipath.github.io/uipath-python/cli/#push), then deploy it to Orchestrator or Studio Web with [`uipath deploy`](https://uipath.github.io/uipath-python/cli/#deploy), and run it in cloud to confirm the changes behave correctly against the real platform.
