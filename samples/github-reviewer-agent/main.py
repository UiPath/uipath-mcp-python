import os
from contextlib import asynccontextmanager

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState

dotenv.load_dotenv()


class PullRequestState(AgentState):
    owner: str
    repo: str
    pullNumber: int


@asynccontextmanager
async def make_graph():
    async with MultiServerMCPClient() as client:
        await client.connect_to_server_via_sse(
            server_name="github-mcp-server",
            url=os.getenv("UIPATH_MCP_SERVER_URL"),
            headers={"Authorization": f"Bearer {os.getenv('UIPATH_ACCESS_TOKEN')}"},
            timeout=60,
        )

        tools = client.get_tools()
        print(tools)
        model = ChatAnthropic(model="claude-3-5-sonnet-latest")

        def pr_prompt(state: PullRequestState):
            """Create a prompt that incorporates PR data."""
            system_message = f"""You are a professional Python developer with experience in code reviews.
            You are reviewing a PR for repo: {state["owner"]}/{state["repo"]}, PR #{state["pullNumber"]}.
            Your task is to analyze the code changes in the PR and provide feedback.
            Use the available tools to fetch PR details and provide a thorough code review.
            Please post the review in the PR comments."""

            return [{"role": "system", "content": system_message}] + state["messages"]

        graph = create_react_agent(
            model, tools=tools, state_schema=PullRequestState, prompt=pr_prompt
        )

        yield graph
