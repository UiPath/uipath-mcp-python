# MCP Functions Agent

An agent that works with the MCP Functions Server to create, test, and execute Python functions dynamically.

## Features
- AI-powered function generation
- Automated test creation
- Dynamic code validation
- Integration with MCP Functions Server
- Smart error handling and debugging

## Requirements
- Python >=3.11
- `uipath-langchain`
- `langgraph`
- `langchain-mcp-adapters`
- Access to MCP Functions Server

## Configuration
Set up your environment variables in `.env`:
```bash
FUNCTIONS_MCP_SERVER_URL=your_functions_server_url
UIPATH_ACCESS_TOKEN=your_access_token
```

## Usage
The agent can:
1. Analyze natural language function requests
2. Generate appropriate Python code
3. Create comprehensive test cases
4. Validate and execute the functions
5. Provide detailed feedback on results

## Example
```bash
uipath run agent '{"query": "Create a function that calculates the factorial of a number"}'
```
