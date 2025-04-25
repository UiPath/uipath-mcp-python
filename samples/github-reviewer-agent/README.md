# LangGraph GitHub Reviewer Agent with Claude and GitHub MCP Server

This project demonstrates how to create a GitHub Reviewer Agent using LangGraph with Claude 3.5 Sonnet which connects to the GitHub MCP Server.

## Overview

The agent uses:
- Claude 3.5 Sonnet as the language model
- LangGraph for orchestration
- Connects to a Remote MCP server

## Architecture

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	agent(agent)
	tools(tools)
	__end__([<p>__end__</p>]):::last
	__start__ --> agent;
	tools --> agent;
	agent -.-> tools;
	agent -.-> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Prerequisites

- Python 3.10+
- `langchain-anthropic`
- `langchain-mcp-adapters`
- `langgraph`
- Anthropic API key set as an environment variable

## Installation

```bash
uv venv -p 3.11 .venv
.venv\Scripts\activate
uv sync
```

Set your API keys and MCP Remote Server URL as environment variables in .env

```bash
ANTHROPIC_API_KEY=your_anthropic_api_key
UIPATH_MCP_SERVER_URL=https://alpha.uipath.com/account/tenant/mcp_/mcp/server_slug/sse
```

## Debugging

For debugging issues:

1. Check logs for any connection or runtime errors:
   ```bash
   uipath run '{"messages": [{"role": "user", "content": "Review this PR and provide detailed feedback"}], "owner": "anthropic", "repo": "claude", "pullNumber": 123}'
   ```


