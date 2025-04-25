import json
import os
import re
from contextlib import asynccontextmanager
from typing import List, Optional

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel, Field

dotenv.load_dotenv()

AI_GENERATED_LABEL = "_/ai generated"


class PullRequestInfo(BaseModel):
    """Input parameters with Pull Request details"""

    owner: str
    repo: str
    pullNumber: int
    commentNumber: Optional[int]
    command: str = Field(default="review")


class PullRequestComment(BaseModel):
    """Human or AI message extracted from Pull Request reviews/comments/issues"""

    id: int
    body: str
    role: str
    in_reply_to: Optional[str]
    created_at: Optional[str]


class GraphState(AgentState):
    """Graph state"""

    owner: str
    repo: str
    pull_number: int
    in_reply_to: Optional[int]
    command: str


def process_comment(comment) -> PullRequestComment:
    """Process a Pull Request GitHub comment and return a PullRequestMessage."""

    in_reply_to = None
    created_at = comment.get("created_at") or comment.get("submitted_at")
    if comment["body"].startswith(AI_GENERATED_LABEL):
        # Parse in_reply_to from the AI label
        match = re.search(r"\[(\d+)\]", comment["body"])
        if match:
            in_reply_to = match.group(1)
        return PullRequestComment(
            body=comment["body"].strip(),
            role="assistant",
            created_at=created_at,
            id=comment["id"],
            in_reply_to=in_reply_to,
        )
    else:
        # /help confuses the LLM
        message = comment["body"].replace("/help", "").strip()
        path = comment.get("path")
        line = comment.get("line")
        if path and line:
            message = f"Comment on {path} line {line}: {message}"
        return PullRequestComment(
            body=message,
            role="user",
            created_at=created_at,
            id=comment["id"],
            in_reply_to=None,
        )


@asynccontextmanager
async def make_graph():
    async with sse_client(
        url=os.getenv("UIPATH_MCP_SERVER_URL"),
        headers={"Authorization": f"Bearer {os.getenv('UIPATH_ACCESS_TOKEN')}"},
        timeout=60,
    ) as (read, write):
        async with ClientSession(read, write) as session:
            tools = await load_mcp_tools(session)

            model = ChatAnthropic(model="claude-3-5-sonnet-latest")

            # Create the conversation history
            async def hydrate_history(input: PullRequestInfo) -> GraphState:
                """Fetch PR context at the start of the workflow."""

                pr_history: List[PullRequestComment] = []

                # Fetch PR details
                tool_result = await session.call_tool(
                    "get_pull_request",
                    {
                        "owner": input.owner,
                        "repo": input.repo,
                        "pullNumber": input.pullNumber,
                    },
                )

                pr_details = json.loads(tool_result.content[0].text)
                pr_body = pr_details.get("body") or ""

                # Add PR details as the first human message
                pr_history.append(
                    PullRequestComment(
                        body=f"Pull Request #{input.pullNumber} by {pr_details['user']['login']}\nTitle: {pr_details['title']}\nDescription: {pr_body}",
                        role="user",
                        created_at=pr_details["created_at"],
                        id=pr_details["id"],
                        in_reply_to=None,
                    )
                )

                # Fetch PR comments
                tool_result = await session.call_tool(
                    "get_pull_request_comments",
                    {
                        "owner": input.owner,
                        "repo": input.repo,
                        "pullNumber": input.pullNumber,
                    },
                )
                comments = json.loads(tool_result.content[0].text)
                for comment in comments:
                    pr_history.append(process_comment(comment))

                # Fetch PR review comments
                tool_result = await session.call_tool(
                    "get_pull_request_reviews",
                    {
                        "owner": input.owner,
                        "repo": input.repo,
                        "pullNumber": input.pullNumber,
                    },
                )
                review_comments = json.loads(tool_result.content[0].text)
                for comment in review_comments:
                    pr_history.append(process_comment(comment))

                # Fetch issue comments
                tool_result = await session.call_tool(
                    "get_issue_comments",
                    {
                        "owner": input.owner,
                        "repo": input.repo,
                        "issue_number": input.pullNumber,
                        "page": 1,
                        "per_page": 100,
                    },
                )
                issue_comments = json.loads(tool_result.content[0].text)
                for comment in issue_comments:
                    pr_history.append(process_comment(comment))

                # Sort chat items by created_at timestamp
                pr_history.sort(key=lambda item: item.created_at)

                messages = []
                for item in pr_history:
                    messages.append(
                        {
                            "role": item.role,
                            "content": item.body,
                            "metadata": {
                                "id": item.id,
                                "created_at": item.created_at,
                                "in_reply_to": item.in_reply_to,
                            },
                        }
                    )

                # Update the state with the hydrated conversation history
                return {
                    "owner": input.owner,
                    "repo": input.repo,
                    "pull_number": input.pullNumber,
                    "in_reply_to": input.commentNumber,
                    "messages": messages,
                }

            def pr_prompt(state: GraphState) -> GraphState:
                in_reply_to = state.get("in_reply_to")
                if in_reply_to:
                    label = f"{AI_GENERATED_LABEL} [{in_reply_to}]_\n"
                    command_message = f"The CURRENT command is '{state['command']}' from review comment id #{in_reply_to}. EXECUTE the CURRENT command and provide detailed feedback."
                else:
                    label = f"{AI_GENERATED_LABEL}_\n"
                    command_message = f"The CURRENT command is '{state['command']}. EXECUTE the CURRENT command and provide detailed feedback."

                """Create a prompt that incorporates PR data."""
                system_message = f"""You are a professional developer with experience in code reviews and GitHub pull requests.
                You are working with repo: {state["owner"]}/{state["repo"]}, PR #{state["pull_number"]}.

                IMPORTANT INSTRUCTIONS:
                1. ALWAYS get the contents of the changed files in the current PR
                2. ALWAYS use the contents of the changed files as context when replying to a user command.
                3. ALWAYS start your responses with "{label}" to properly tag your comments.
                4. When you reply to a comment, make sure to address the specific request.
                5. When reviewing code, be thorough but constructive - point out both issues and good practices.
                6. You MUST use the available tools to post your response as a PR comment or perform the PR code review.

                COMMANDS YOU SHOULD UNDERSTAND:
                - "review": Perform a full code review of the PR
                - "summarize": Summarize the changes in the PR
                - "explain <file>": Explain what changes were made to a specific file
                - "suggest": Suggest improvements to the code
                - "test": Suggest appropriate tests for the changes

                WORKFLOW:
                1. Gather the contents of the changed files for the current PR
                2. Analyze the available PR data and understand what the user is asking for
                3. Use the appropriate tools to gather any additional information needed
                4. Prepare your response based on the request
                5. [IMPORTANT] Based on the user's command:
                    - if the command has a review comment id, REPLY TO THE REVIEW COMMENT WITH THE SPECIFIED ID using tool add_pull_request_review_comment
                    - else POST PULL REQUEST REVIEW using tool create_pull_request_review

                Remember: The user wants specific, actionable feedback and help with their code.

                {command_message}
                """

                return [{"role": "system", "content": system_message}] + state[
                    "messages"
                ]

            # Create the agent node - this will handle both analysis and posting the response
            # using its available GitHub tools
            agent = create_react_agent(
                model, tools=tools, state_schema=GraphState, prompt=pr_prompt
            )

            # Create a simple two-node StateGraph
            workflow = StateGraph(GraphState, input=PullRequestInfo)

            # Add nodes
            workflow.add_node("hydrate_history", hydrate_history)
            workflow.add_node("github_agent", agent)

            # Add edges - simple linear flow from "history hydration" to "GitHub MCP tools agent" to end
            workflow.add_edge("__start__", "hydrate_history")
            workflow.add_edge("hydrate_history", "github_agent")
            workflow.add_edge("github_agent", END)

            # Compile the graph
            graph = workflow.compile()

            yield graph
