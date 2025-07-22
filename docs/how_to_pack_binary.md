# How To Pack Binary MCP Server

This guide walks you through manually packaging and publishing the official [GitHub MCP server](https://github.com/github/github-mcp-server) to UiPath Orchestrator. An [example GitHub Actions workflow](/.github/workflows/build-github-mcp-server.yml) is provided to automate these steps.

/// attention
To build binary MCP servers locally, your environment must match UiPath's serverless runtime architecture (Ubuntu 64-bit AMD64). If you're on a different operating system, we recommend using the GitHub Actions workflow described in the [Automating with GitHub Actions](#automating-with-github-actions) section below.
///

## Prerequisites

- UiPath Cloud account
- UiPath PAT (personal access token)
- `go` (version 1.21+)
- `python` (version 3.11+)
- `uv` package manager (`pip install uv`)

## Steps

### 1. Clone and Build the GitHub MCP Server

<!-- termynal -->
```shell
# Clone the repository
> git clone https://github.com/github/github-mcp-server.git
> cd github-mcp-server

# Build the server
> cd cmd/github-mcp-server
> go build
```

### 2. Create Package Directory

<!-- termynal -->
```shell
# Create package directory and copy executable
> mkdir -p mcp-package
> cp github-mcp-server mcp-package/
> cd mcp-package
```

### 3. Create Configuration Files

Create the following files in the mcp-package directory:

1. `mcp.json` - Server configuration:
```json
{
  "servers": {
    "github": {
      "command": "/bin/sh",
      "args": ["-c", "chmod +x github-mcp-server && ./github-mcp-server stdio"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "x"
      }
    }
  }
}
```

2. `pyproject.toml` - Project metadata:
```toml
[project]
name = "mcp-github-server"
version = "0.0.1"
description = "Official GitHub MCP Server"
authors = [{ name = "John Doe" }]
dependencies = [
    "uipath-mcp>=0.0.99",
]
requires-python = ">=3.11"
```

### 4. Set Up Python Environment

<!-- termynal -->
```shell
# Initialize a new uv project in the current directory
> uv venv

# Activate the virtual environment
> source .venv/bin/activate

# Install dependencies
> uv sync
```

### 5. Authenticate With UiPath

<!-- termynal -->
```shell
> uipath auth
⠋ Authenticating with UiPath ...
🔗 If a browser window did not open, please open the following URL in your browser: [LINK]
👇 Select tenant:
  0: Tenant1
  1: Tenant2
Select tenant number: 0
Selected tenant: Tenant1
✓  Authentication successful.
```

### 6. Initialize UiPath Package

<!-- termynal -->
```shell
⠋ Initializing UiPath project ...
✓   Created '.env' file.
✓   Created 'uipath.json' file.
```

Edit the generated `uipath.json` to include the executable:
```json
{
  "settings": {
    "filesIncluded": ["github-mcp-server"]
  }
}
```

### 7. Package for UiPath

<!-- termynal -->
```shell
⠋ Packaging project ...
Name       : mcp-github-server
Version    : 0.0.1
Description: Official GitHub MCP Server
Authors    : John Doe
✓  Project successfully packaged.
```

### 8. Upload to UiPath Orchestrator

<!-- termynal -->
```shell
⠙ Publishing most recent package: mcp-github-server.0.0.1.nupkg ...
✓  Package published successfully!
```

## Automating with GitHub Actions

To automate this process:

1. Copy the [example workflow](https://github.com/UiPath/uipath-mcp-python/blob/main/.github/workflows/build-github-mcp-server.yml) to `.github/workflows/` in your repository
2. Go to GitHub Actions tab and run the workflow
3. Provide the version when prompted
4. Download the artifact after completion

The workflow handles all the manual steps automatically, including the crucial modification of `uipath.json` to include the executable in the package.
