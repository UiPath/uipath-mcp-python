import os
from contextlib import asynccontextmanager

import dotenv
import httpx2
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from mcp import ClientSession
from uipath_langchain.agent.tools.mcp import load_mcp_tools
from uipath_langchain.agent.tools.mcp.streamable_http import streamable_http_client
from uipath_langchain.chat.models import UiPathAzureChatOpenAI

dotenv.load_dotenv()


@asynccontextmanager
async def mcp_session(url: str, token: str):
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(60, read=300),
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


GITHUB_MCP_SERVER_URL = os.getenv("GITHUB_MCP_SERVER_URL")
SLACK_MCP_SERVER_URL = os.getenv("SLACK_MCP_SERVER_URL")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
UIPATH_ACCESS_TOKEN = os.getenv("UIPATH_ACCESS_TOKEN")


@asynccontextmanager
async def make_graph():
    async with mcp_session(GITHUB_MCP_SERVER_URL, UIPATH_ACCESS_TOKEN) as git_session:
        all_github_tools = await load_mcp_tools(git_session)

        async with mcp_session(
            SLACK_MCP_SERVER_URL, UIPATH_ACCESS_TOKEN
        ) as slack_session:
            all_slack_tools = await load_mcp_tools(slack_session)

            # Keep only the necessary tools
            # LLMs get confused with too many choices
            allowed_git_tool_names = {
                "get_pull_request",
                "get_pull_request_files",
                "get_file_contents",
            }

            allowed_slack_tool_names = {
                "slack_post_message",
                "slack_reply_to_thread",
            }

            github_tools = [
                tool for tool in all_github_tools if tool.name in allowed_git_tool_names
            ]
            slack_tools = [
                tool
                for tool in all_slack_tools
                if tool.name in allowed_slack_tool_names
            ]

            all_tools = github_tools + slack_tools

            model = UiPathAzureChatOpenAI(
                model="gpt-4.1-2025-04-14",
                temperature=0,
                max_tokens=10000,
                timeout=120,
                max_retries=2,
            )

            def system_prompt(state: AgentState) -> AgentState:
                system_message = f"""
You are a professional senior Python developer and GitHub reviewer.

YOU MUST FOLLOW THESE RULES WITHOUT EXCEPTION:

1. ALWAYS begin your review by reading the contents of the changed files.
2. ONLY use the contents of the changed files as context — do not assume.
3. If you encounter an issue or uncertainty, explain clearly or return an error.
4. DO NOT skip steps or speculate — be factual and grounded in the code.

At the end of your review, you MUST post a message to Slack channel `{SLACK_CHANNEL_ID}` using the `slack_post_message` tool.
This first post MUST include the GitHub Pull Request Title, number, repo and URL: https://github.com/owner/repo/pull/number nicely formatted for SLACK.

Afterward, you MUST use the `slack_reply_to_thread` tool to reply to the thread with a detailed review.

FORMAT THE REVIEW MESSAGE AS FOLLOWS, USING SLACK MARKDOWN:

*🧠 Summary:*
Briefly explain what the pull request does.

*✅ Pros:*
• List strengths of the code
• Mention clarity, structure, naming, tests, etc.

*❌ Issues:*
• `filename.py` line 42: Describe the issue
• Be precise and line-specific

*💡 Suggestions:*
• Recommend cleanups, refactors, or improvements

Wrap multi-line code suggestions in triple backticks (```python ... ```).
End with:

_This review was generated automatically._
"""

                return [{"role": "system", "content": system_message}] + state[
                    "messages"
                ]

            agent = create_react_agent(
                model,
                tools=all_tools,
                prompt=system_prompt,
            )

            yield agent
