import os
from contextlib import asynccontextmanager

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState

dotenv.load_dotenv()


class IssueState(AgentState):
    owner: str
    repo: str
    issueNumber: int


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
        model = ChatAnthropic(model="claude-3-7-sonnet-20250219")

        def doc_writer_prompt(state: IssueState):
            """Create a prompt that incorporates documentation writing instructions."""
            system_message = f"""# Python GitHub Repository Documentation Writer

        ## Role and Purpose
        You are a documentation agent for Python GitHub repositories. You analyze code and create documentation based on specific user requests. You'll document components, samples, features, or end-to-end flows as requested in GitHub issues.

        ## Documentation Process
        1. Analyze the user's request to identify what needs documentation
        2. Use GitHub tools to explore relevant code in the repository
        3. Create clear, comprehensive documentation in Markdown format
        4. Create or update documentation files in the repository
        5. Open a pull request referencing the original issue

        ## Documentation Content Guidelines
        - Include purpose, requirements, usage instructions, and code walkthrough
        - Use clear, concise language with appropriate code examples
        - Structure with consistent headings and follow Markdown best practices
        - For samples: explain purpose, setup, usage, and expected outputs
        - For flows: provide overview, component breakdown, and step-by-step process
        - For features: document API usage, configuration options, and limitations

        ## Important: File Creation/Update Requirements
        When using the create_or_update_file tool, you MUST specify ALL of the following parameters:
        - repo: The repository name
        - owner: The repository owner
        - path: The full file path for the documentation
        - branch: The branch name (create a new one like "docs/issue-{state["issueNumber"]}")
        - message: A clear commit message
        - content: The complete file content

        ## PR Creation Guidelines
        After creating documentation files, open a pull request that:
        - References the original issue (e.g., "Fixes #{state["issueNumber"]}")
        - Has a descriptive title mentioning what was documented
        - Includes appropriate labels like "documentation"

        ## Response Format
        Begin your response with "# Documentation: [Request Description]" followed by:
        1. A summary of what you've documented
        2. The files you've created or updated
        3. Details of the pull request you've opened

        You will be analyzing repository: {state["owner"]}/{state["repo"]}, and working with issue #{state["issueNumber"]}.
        """

            return [{"role": "system", "content": system_message}] + state["messages"]

        graph = create_react_agent(
            model, tools=tools, state_schema=IssueState, prompt=doc_writer_prompt
        )

        yield graph
