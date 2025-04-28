# How to pack and publish the GitHub MCP Server

This guide walks you through manually packaging and publishing the official [GitHub MCP server](https://github.com/github/github-mcp-server) to UiPath Orchestrator. An [example GitHub Actions workflow](/.github/workflows/build-github-mcp-server.yml) is provided to automate these steps.

## Prerequisites

- UiPath Cloud account
- UiPath PAT (personal access token)
- `go` (version 1.21+)
- `python` (version 3.10+)
- `uv` package manager (`pip install uv`)

## Steps

### 1. Clone and Build the GitHub MCP Server

```bash
# Clone the repository
git clone https://github.com/github/github-mcp-server.git
cd github-mcp-server

# Build the server
cd cmd/github-mcp-server
go build
```

### 2. Create Package Directory

```bash
# Create a temp directory for packaging
mkdir -p ~/mcp-package
cp github-mcp-server ~/mcp-package/
chmod +x ~/mcp-package/github-mcp-server
cd ~/mcp-package
```

### 3. Create Configuration Files

Create `mcp.json`:

```bash
cat > mcp.json << EOF
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
EOF
```

Create `pyproject.toml`:

```bash
cat > pyproject.toml << EOF
[project]
name = "mcp-github-server"
version = "0.0.1"
description = "Official GitHub MCP Server"
authors = [{ name = "John Doe" }]
dependencies = [
    "uipath-mcp>=0.0.74",
]
requires-python = ">=3.10"
EOF
```

Create `.env` file:

```bash
cat > .env << EOF
UIPATH_ACCESS_TOKEN=your_access_token_here
UIPATH_URL=https://cloud.uipath.com/account/tenant
EOF
```

### 4. Set Up Python Environment

```bash
# Create and activate virtual environment
uv venv -p 3.10 .venv
source .venv/bin/activate

# Install dependencies
uv sync
```

### 5. Initialize UiPath Package

```bash
# Initialize UiPath project
uipath init
```

This creates a `uipath.json` file.

### 6. Edit uipath.json to Include the Executable

Open `uipath.json` in a text editor:

```bash
nano uipath.json
```

Add a `settings` section with `filesIncluded`:

```json
{
  "settings": {
    "filesIncluded": ["github-mcp-server"]
  },
  "entrypoints": []
}
```

Save and exit.

### 7. Package for UiPath

```bash
# Create the package
uipath pack
```

This creates a `.nupkg` file in the `.uipath` directory.

### 8. Upload to UiPath Orchestrator

Upload the `.nupkg` file to your UiPath Orchestrator instance through the web interface, API or using the `uipath publish` CLI command.

## Automating with GitHub Actions

To automate this process:

1. Copy the [example workflow](/.github/workflows/build-github-mcp-server.yml) to `.github/workflows/` in your repository
2. Go to GitHub Actions tab and run the workflow
3. Provide the version when prompted
4. Download the artifact after completion

The workflow handles all the manual steps automatically, including the crucial modification of `uipath.json` to include the executable in the package.
