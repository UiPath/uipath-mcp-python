# GitHub Docs Agent Sample

This sample demonstrates how to use the GitHub Docs Agent to automate documentation tasks within a GitHub repository. The agent is designed to analyze code and create documentation based on specific user requests.

## Folder Structure

- `.env.example`: Example environment variables file.
- `agent.mermaid`: Diagram file for visualizing the agent's workflow.
- `langgraph.json`: Configuration file for language graph settings.
- `main.py`: Main script containing the agent's logic.
- `pyproject.toml`: Python project configuration file.
- `uipath.json`: Configuration file for UiPath settings.
- `uv.lock`: Lock file for dependencies.

## Setup Instructions

1. **Clone the Repository**: Clone the `uipath-mcp-python` repository to your local machine.

   ```bash
   git clone https://github.com/UiPath/uipath-mcp-python.git
   ```

2. **Navigate to the Sample Directory**: Change your working directory to the `github-docs-agent` sample.

   ```bash
   cd uipath-mcp-python/samples/github-docs-agent
   ```

3. **Install Dependencies**: Use the following command to install the necessary Python dependencies.

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**: Copy the `.env.example` to `.env` and fill in the required environment variables.

   ```bash
   cp .env.example .env
   ```

5. **Run the Agent**: Execute the main script to start the agent.

   ```bash
   python main.py
   ```

## Usage

The GitHub Docs Agent listens for specific documentation requests in GitHub issues and automatically generates the required documentation. It uses the `main.py` script to process these requests and update the repository accordingly.

## Expected Outcomes

- Automated documentation generation based on GitHub issues.
- Updated documentation files within the repository.
- Improved documentation consistency and quality.

## Additional Information

For more details on configuring and extending the agent, refer to the `pyproject.toml` and `uipath.json` files.
