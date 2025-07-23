# Quickstart Guide: UiPath Coded MCP Servers

## Introduction

This guide provides instructions for setting up and running a UiPath coded MCP Server.

## Prerequisites

You need:

-   Python 3.11 or higher
-   `pip` or `uv` package manager
-   A UiPath Automation Cloud account with appropriate permissions
-   A [UiPath Personal Access Token](https://docs.uipath.com/automation-cloud/automation-cloud/latest/api-guide/personal-access-tokens) with _Orchestrator API Access scopes_

## Creating a New Project

Use `uv` for package management. To create a new project:

//// tab | Linux, macOS, Windows Bash

<!-- termynal -->

```shell
> mkdir example
> cd example
```

////

//// tab | Windows PowerShell

<!-- termynal -->

```powershell
> New-Item -ItemType Directory -Path example
> Set-Location example
```

////

//// tab | uv
    new: true

<!-- termynal -->

```shell
# Initialize a new uv project in the current directory
> uv init . --python 3.11

# Create a new virtual environment
# By default, uv creates a virtual environment in a directory called .venv
> uv venv
Using CPython 3.11.16 interpreter at: [PATH]
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate

# Activate the virtual environment
# For Windows PowerShell/ Windows CMD: .venv\Scripts\activate
# For Windows Bash: source .venv/Scripts/activate
> source .venv/bin/activate

# Install the uipath package
> uv add uipath-mcp
```

////

//// tab | pip

<!-- termynal -->

```shell
# Create a new virtual environment
> python -m venv .venv

# Activate the virtual environment
# For Windows PowerShell: .venv\Scripts\Activate.ps1
# For Windows Bash: source .venv/Scripts/activate
> source .venv/bin/activate

# Upgrade pip to the latest version
> python -m pip install --upgrade pip

# Install the uipath package
> pip install uipath-mcp
```

////

## Create Your First UiPath Coded MCP Server

Create your first MCP server

<!-- termynal -->

```shell
> uipath new math-server
⠋ Creating new mcp server 'math-server' in current directory ...
✓  Created 'server.py' file.
✓  Created 'mcp.json' file.
✓  Created 'pyproject.toml' file.
💡  Initialize project: uipath init
════════════════════════════════════════════════════════════
Start 'math-server' as a self-hosted MCP server
════════════════════════════════════════════════════════════
💡  1. Set UIPATH_FOLDER_PATH environment variable
💡  2. Start the server locally: uipath run math-server
```

/// warning
_uipath new_ command deletes all previous `.py` files in the current directory.
  ///

This command creates the following files:

| File Name        | Description                                                                            |
|------------------|----------------------------------------------------------------------------------------|
| `server.py`      | A sample MCP math server using FastMCP                                                 |
| `mcp.json`       | Configuration file needed for coded UiPath MCP Servers.                                |
| `pyproject.toml` | Project metadata and dependencies as per [PEP 518](https://peps.python.org/pep-0518/). |


## Initialize Project

<!-- termynal -->

```shell
> uipath init
⠋ Initializing UiPath project ...
✓   Created '.env' file.
✓   Created 'uipath.json' file.
```

This command creates the following files:

| File Name        | Description                                                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `.env`           | Environment variables and secrets (this file is not packed & published).                                                     |
| `uipath.json`    | Input/output JSON schemas and bindings.                                                                                           |

## Authenticate With UiPath

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

## Run the MCP Server

There are two ways to run your coded MCP server:

### 1. Running Locally (On-Prem)

When running the server locally, JSON-RPC requests are tunneled from UiPath servers to your local server. During startup, the local server automatically registers itself with UiPath.

Since MCP servers are folder-scoped in Orchestrator, you need to set the `UIPATH_FOLDER_PATH` environment variable. To do this:

1. Copy the folder path from your Orchestrator interface

<picture data-light="../quick_start_images/copy-folder-light.png" data-dark="../quick_start_images/copy-folder-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/copy-folder-dark.png"
  />
  <img
    src="../quick_start_images/copy-folder-light.png"
  />
</picture>

2. Add it to the `.env` file (created during [`uipath init`](#initialize-project)) as:
   ```
   UIPATH_FOLDER_PATH=<Copied folder path>
   ```

<!-- termynal -->
```shell
# Start the server
> uipath run math-server
Initializing tracer instance. This should only be done once per process.
HTTP Request: GET https://***/orchestrator_/api/FoldersNavigation/GetFoldersForCurrentUser?searchText=Agents&skip=0&take=20 "HTTP/1.1 200 OK"
Folder key: ***
Initializing client session...
Initialization successful
Registering server runtime ...
...
```

#### Verifying the Server

Once started successfully, your MCP server will appear in Orchestrator. Navigate to the **MCP Servers** tab in your configured folder:

<picture data-light="../quick_start_images/self-hosted-light.png" data-dark="../quick_start_images/self-hosted-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/self-hosted-dark.png"
  />
  <img
    src="../quick_start_images/self-hosted-light.png"
  />
</picture>

You can inspect the available tools by clicking on the server:

<picture data-light="../quick_start_images/tools-light.png" data-dark="../quick_start_images/tools-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/tools-dark.png"
  />
  <img
    src="../quick_start_images/tools-light.png"
  />
</picture>

Now we can connect to the server using any MCP client. See the [Connecting to the MCP Server](#connecting-to-the-mcp-server) section.

### 2. Running on UiPath Automation Cloud

/// Info
This quickstart guide provides instructions for deploying the MCP Server in _My Workspace_ folder. Choosing this folder simplifies the configuration process, as you won’t need to manually handle the following:

- Serverless machine allocation

- Unattended robot permissions

- Process creation (processes are automatically provisioned when a package is published to `My Workspace`)

If you prefer to deploy the MCP Server in a different folder, additional steps are required:

1. Create a process from the MCP Server package.

2. Ensure a [serverless runtime (machine)](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/executing-unattended-automations-with-serverless-robots) is assigned to the target folder in Orchestrator.

3. Confirm that a user with [unattended robot permissions](https://docs.uipath.com/robot/standalone/2024.10/admin-guide/unattended-automations) is assigned to the target folder.
///

To deploy your MCP server to UiPath Automation Cloud, follow these steps:

#### (Optional) Customize the Package

Update author details in `pyproject.toml`:

```toml
authors = [{ name = "Your Name", email = "your.name@example.com" }]
```

#### Package Your Project

<!-- termynal -->
```shell
> uipath pack
⠹ Packaging project ...
Name       : math-server
Version    : 0.0.1
Description: Description for math-server project
Authors    : John Doe
✓  Project successfully packaged.
```

#### Publish The MCP Server Package

<!-- termynal -->
```shell
> uipath publish --my-workspace
⠙ Publishing most recent package: math-server.0.0.1.nupkg ...
✓  Package published successfully!
⠦ Getting process information ...
🔗 Process configuration link: [LINK]
💡 Use the link above to configure any environment variables
```

After publishing, you can configure and manage your MCP server through the UiPath Automation Cloud interface:

#### Configure in UiPath Automation Cloud

1. In `My Workspace`, navigate to the **MCP Servers** tab and click **Add MCP Server**

<picture data-light="../quick_start_images/add-mcp-light.png" data-dark="../quick_start_images/add-mcp-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/add-mcp-dark.png"
  />
  <img
    src="../quick_start_images/add-mcp-light.png"
  />
</picture>

2. In the configuration dialog:
   - Select `Coded` as the server type
   - Choose the `math-server` process
   - Click **Add** to deploy the server

<picture data-light="../quick_start_images/configure-mcp-light.png" data-dark="../quick_start_images/configure-mcp-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/configure-mcp-dark.png"
  />
  <img
    src="../quick_start_images/configure-mcp-light.png"
  />
</picture>

Once deployed, the server automatically starts and registers its available tools. You can monitor the job status in the MCP Server side panel.

## Connecting to the MCP Server

You can connect to your MCP server using any MCP client. Here's what you need:

1. **MCP Server URL**: Copy this from the UiPath **MCP Servers** page in Orchestrator

<picture data-light="../quick_start_images/copy-link-light.png" data-dark="../quick_start_images/copy-link-dark.png">
  <source
    media="(prefers-color-scheme: dark)"
    srcset="../quick_start_images/copy-link-dark.png"
  />
  <img
    src="../quick_start_images/copy-link-light.png"
  />
</picture>

2. **Authentication**: Use your [Personal Access Token (PAT)](#prerequisites) with _Orchestrator API Access scopes_ as authorization header
3. **Transport**: Configure the client to use HTTP Streamable transport

## Next Steps

Congratulations! You have successfully set up, created, published, and run a coded UiPath MCP Server. 🚀

For more coded MCP samples, please refer to our [samples section](https://github.com/UiPath/uipath-mcp-python/tree/main/samples) in GitHub.
