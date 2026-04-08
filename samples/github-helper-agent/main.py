import json
import os
import re
from contextlib import asynccontextmanager
from typing import List, Optional

import dotenv
from langchain.output_parsers import PydanticOutputParser
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, Field
from uipath_langchain.chat.models import UiPathAzureChatOpenAI

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
    in_reply_to: Optional[int]
    created_at: Optional[str]


class PullRequestFile(BaseModel):
    path: str
    content: str


class PullRequestCommit(BaseModel):
    message: str
    files: List[PullRequestFile]


class GraphState(AgentState):
    """Graph state"""

    owner: str
    repo: str
    pull_number: int
    branch: str
    in_reply_to: Optional[int]
    command: str


def process_comment(comment) -> PullRequestComment:
    """Process a GitHub comment and return a PullRequestComment."""

    in_reply_to = None
    created_at = comment.get("created_at") or comment.get("submitted_at")
    if comment["body"].startswith(AI_GENERATED_LABEL):
        # Parse in_reply_to from the AI label
        match = re.search(r"\[(\d+)\]", comment["body"])
        if match:
            in_reply_to = int(match.group(1))
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
    async with streamablehttp_client(
        url=os.getenv("UIPATH_MCP_SERVER_URL"),
        headers={"Authorization": f"Bearer {os.getenv('UIPATH_ACCESS_TOKEN')}"},
        timeout=60,
    ) as (read, write, session_id_callback):
        async with ClientSession(read, write) as session:
            all_tools = await load_mcp_tools(session)

            # Keep only data extraction tools
            # LLMs get confused with too many choices
            allowed_tool_names = {
                "get_pull_request_files",
                "get_file_contents",
            }

            tools = [tool for tool in all_tools if tool.name in allowed_tool_names]

            model = UiPathAzureChatOpenAI(
                model="gpt-4.1-2025-04-14",
                temperature=0,
                max_tokens=10000,
                timeout=120,
                max_retries=2,
            )

            commit_data_parser = PydanticOutputParser(pydantic_object=PullRequestCommit)

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
                pr_branch = pr_details.get("head").get("ref")

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
                    "branch": pr_branch,
                    "in_reply_to": input.commentNumber,
                    "messages": messages,
                }

            def reviewer_prompt(state: GraphState) -> GraphState:
                in_reply_to = state.get("in_reply_to")
                if in_reply_to:
                    label = f"{AI_GENERATED_LABEL} [{in_reply_to}]_\n"
                    command_message = f"The CURRENT command is '{state['command']}'. EXECUTE the CURRENT command in_reply_to #{in_reply_to} and provide detailed feedback."
                else:
                    label = f"{AI_GENERATED_LABEL}_\n"
                    command_message = f"The CURRENT command is '{state['command']}'. EXECUTE the CURRENT command and provide detailed feedback."

                system_message = f"""
You are a professional developer and GitHub reviewer.

You are reviewing Pull Request #{state["pull_number"]} in repo `{state["owner"]}/{state["repo"]}`.

YOU MUST FOLLOW THESE RULES WITHOUT EXCEPTION:

1. ALWAYS BEGIN WITH the contents of the changed files BEFORE doing anything else.
2. ALWAYS use the contents of the changed files as context.
3. ALWAYS start ALL responses with exactly: "{label}" (no exceptions).

COMMANDS you can receive:
- "review": Do a complete code review, pointing out issues and good practices.
- "summarize": Summarize the PR changes.
- "suggest": Suggest improvements.
- "test": Suggest tests for the changes.

IMPORTANT:
- Do not make assumptions.
- Do not skip steps.
- If you cannot complete the command for any reason, you MUST reply with an error comment.

{command_message}
                """

                return [{"role": "system", "content": system_message}] + state[
                    "messages"
                ]

            # Create the reviewer node, this one should post review comments
            # using its available GitHub tools
            reviewer_agent = create_react_agent(
                model, tools=tools, state_schema=GraphState, prompt=reviewer_prompt
            )

            async def reviewer_node(state: GraphState) -> GraphState:
                result = await reviewer_agent.ainvoke(state)

                # Add the LLM's response to the conversation history
                updated_messages = state["messages"] + result["messages"]

                # Actually post the review
                tool_result = await session.call_tool(
                    "create_pull_request_review",
                    {
                        "owner": state["owner"],
                        "repo": state["repo"],
                        "pullNumber": state["pull_number"],
                        "body": result["messages"][-1].content,
                        "event": "COMMENT",
                    },
                )
                if tool_result.isError:
                    raise ValueError(f"Failed to post review: {tool_result.content}")

                return {
                    **state,
                    "messages": updated_messages,
                }

            # Create the developer node, this one should push commits
            # using its available GitHub tools
            def developer_prompt(state: GraphState) -> GraphState:
                system_message = f"""
You are a GitHub AI assistant helping to manage Pull Requests.

You are working on Pull Request #{state["pull_number"]} in repo `{state["owner"]}/{state["repo"]}`.

Your current task: **Prepare a commit based on the latest suggestion, review, or test feedback.**

**Strict Protocol:**
1. MUST ALWAYS use the **latest suggestion, test, or review** from the conversation history to identify the changes to be made to the code.
2. MUST ALWAYS get the contents of the latest changed files BEFORE writing any response.
3. MUST ALWAYS think carefully about the file changes you want to apply.
4. MUST ALWAYS output JUST the json with this format:
{commit_data_parser.get_format_instructions()}

Begin generating the commit data now, based on the most recent suggestion, review, or test.
                """

                return [{"role": "system", "content": system_message}] + state[
                    "messages"
                ]

            developer_agent = create_react_agent(
                model, tools=tools, state_schema=GraphState, prompt=developer_prompt
            )

            async def developer_node(state: GraphState) -> GraphState:
                result = await developer_agent.ainvoke(state)
                # Add the LLM's response to the conversation history
                updated_messages = state["messages"] + result["messages"]

                # Parse the commit data from the LLM's last message
                commit_data = commit_data_parser.parse(result["messages"][-1].content)

                # Actually push the commit
                tool_result = await session.call_tool(
                    "push_files",
                    {
                        "owner": state["owner"],
                        "repo": state["repo"],
                        "pullNumber": state["pull_number"],
                        "branch": state["branch"],
                        "message": commit_data.message,
                        "files": commit_data.files,
                    },
                )
                if tool_result.isError:
                    raise ValueError(f"Failed to push files: {tool_result.content}")

                return {
                    **state,
                    "messages": updated_messages,
                }

            # Build the workflow
            workflow = StateGraph(GraphState, input=PullRequestInfo)

            workflow.add_node("hydrate_history", hydrate_history)
            workflow.add_node("reviewer_node", reviewer_node)
            workflow.add_node("developer_node", developer_node)

            workflow.add_edge("__start__", "hydrate_history")

            # If command is "commit", go to developer_node
            workflow.add_conditional_edges(
                "hydrate_history",
                lambda input: "developer_node"
                if input.command == "commit"
                else "reviewer_node",
                {
                    "developer_node": "developer_node",
                    "reviewer_node": "reviewer_node",
                    END: END,
                },
            )

            # Compile the graph
            graph = workflow.compile()

            yield graph
