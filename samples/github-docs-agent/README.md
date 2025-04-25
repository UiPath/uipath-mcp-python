# GitHub Docs Agent Sample

## Overview
The `github-docs-agent` sample is an automated agent designed to generate documentation for Python GitHub repositories. It analyzes code and creates comprehensive documentation based on specific user requests.

## Purpose
The purpose of this sample is to demonstrate how to automate the documentation process for GitHub repositories using Python and UiPath's MCP (Multi-Cloud Platform) services.

## Requirements
- Python 3.10 or higher
- Dependencies listed in `pyproject.toml`

## Setup Instructions
1. **Clone the Repository:**
   ```bash
   git clone https://github.com/UiPath/uipath-mcp-python.git
   cd uipath-mcp-python/samples/github-docs-agent
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows use `env\Scripts\activate`
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   - Copy `.env.example` to `.env` and fill in the required values.

## Usage
To run the agent, execute the following command:
```bash
python main.py
```

## System Integration
- **GitHub Actions:** The sample is triggered by the `trigger-docs-agent.yml` workflow, which listens for issues with the title containing `[Docs Agent]`.
- **MCP Servers:** The sample connects to MCP servers using the `MultiServerMCPClient` to fetch necessary data and perform actions.

## Debugging
To debug the agent, use the following command:
```bash
uipath run <agent> <input>
```

## Common Issues
- Ensure all environment variables are correctly set in the `.env` file.
- Verify that all dependencies are installed in the virtual environment.

## Conclusion
This documentation provides a comprehensive guide to setting up and using the `github-docs-agent` sample. It integrates with GitHub Actions and MCP servers to automate the documentation process for Python GitHub repositories.
