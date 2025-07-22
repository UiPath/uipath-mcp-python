# GitHub-Slack Integration Agent

An advanced integration agent that connects GitHub and Slack, providing automated code review notifications and insights. This agent demonstrates cross-platform automation using multiple MCP servers.

## Features
- Automated PR reviews posted to Slack
- Detailed code analysis and feedback
- Threaded discussions in Slack
- Integration with both GitHub and Slack MCP servers
- Professional formatting for Slack messages

## Requirements
- Python >=3.11
- `langchain-mcp-adapters`
- `langgraph`
- `uipath-langchain`
- Access to GitHub and Slack MCP servers

## Configuration
Set the following environment variables in `.env`:
```bash
GITHUB_MCP_SERVER_URL=your_github_mcp_url
SLACK_MCP_SERVER_URL=your_slack_mcp_url
SLACK_CHANNEL_ID=your_channel_id
UIPATH_ACCESS_TOKEN=your_access_token
```

## Usage
The agent automatically:
1. Monitors GitHub pull requests
2. Performs code review analysis
3. Posts formatted messages to Slack
4. Creates threaded discussions for detailed feedback

## Message Format
Messages in Slack follow this structure:
```
🧠 Summary:
Brief explanation of the PR

✅ Pros:
• Code strengths
• Architecture improvements

❌ Issues:
• Specific file and line references
• Detailed problem descriptions

💡 Suggestions:
• Improvement recommendations
• Code examples
```
