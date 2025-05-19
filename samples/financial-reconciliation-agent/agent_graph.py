import enum
from contextlib import asynccontextmanager
from typing import Literal, TypedDict, Any, Optional

from langchain_anthropic import ChatAnthropic
from langgraph.graph import START, StateGraph, END
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from pydantic import BaseModel
from uipath_langchain.chat.models import UiPathAzureChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient

from prompts import email_triage_prompt, refund_payment_agent_prompt, email_topic_extractor_prompt
from local_tools import retrieve_from_execution_context_tool
import os


class EmailTopic(enum.Enum):
    """Email regarding a new payment"""
    PAYMENT = "PAYMENT"
    """Email regarding a payment refund"""
    REFUND = "REFUND"
    """Used for any email topic, other than payment or refund"""
    OTHER = "OTHER"

class EmailTopicExtractorStructure(TypedDict):
    """The structure for email topic extraction response"""
    email_topic: str

if os.getenv("USE_UIPATH_AI_UNITS") and os.getenv("USE_UIPATH_AI_UNITS") == "true":
    # other available UiPath chat models
    # "anthropic.claude-3-5-sonnet-20240620-v1:0",
    # "anthropic.claude-3-5-sonnet-20241022-v2:0",
    # "anthropic.claude-3-7-sonnet-20250219-v1:0",
    # "anthropic.claude-3-haiku-20240307-v1:0",
    # "gemini-1.5-pro-001",
    # "gemini-2.0-flash-001",
    # "gpt-4o-2024-05-13",
    # "gpt-4o-2024-08-06",
    # "gpt-4o-2024-11-20",
    # "gpt-4o-mini-2024-07-18",
    # "o3-mini-2025-01-31",
    llm = UiPathAzureChatOpenAI()
else:
    llm = ChatAnthropic(model="claude-3-5-sonnet-latest")

class OutputStructure(TypedDict):
    """LLM message after finishing execution"""
    message: str
    """Whether agent execution should continue"""
    should_continue: bool

class GraphInput(BaseModel):
    email_address: str
    email_content: str

class GraphOutput(BaseModel):
    answer: str

class State(BaseModel):
    email_address: str
    email_content: str
    agent_message: str
    email_topic: Optional[EmailTopic]
    should_continue: bool

def prepare_input(state: GraphInput):
    return State(
        email_address=state.email_address,
        email_content=state.email_content,
        should_continue=True,
        agent_message="",
        email_topic=None,
    )

@asynccontextmanager
async def agent_mcp(
        server_slug: str,
        structured_output: Any = None,
        extra_tools: Any = None):
    async with MultiServerMCPClient() as client:
        await client.connect_to_server_via_sse(
            server_name="local-stripe-server",
            url=server_slug,
            headers={
                "Authorization": f"Bearer {os.getenv('UIPATH_ACCESS_TOKEN')}"
                },
            timeout=60,
        )

        mcp_tools = client.get_tools()
        if extra_tools:
            available_tools = [*mcp_tools, *extra_tools]
        else:
            available_tools = [*mcp_tools]
        if structured_output is not None:
            agent = create_react_agent(llm, tools=available_tools, response_format=structured_output)
        else:
            agent = create_react_agent(llm, tools=available_tools)

        try:
            yield agent
        finally:
            pass

async def understand_email(state: State) -> Command:
    result = await llm.with_structured_output(EmailTopicExtractorStructure).ainvoke(
            [("system", email_topic_extractor_prompt),
             ("user", "email content: " + state.email_content)]
        )
    print(result)
    return Command(
        update={
            "email_topic":result["email_topic"]
        }
    )

async def check_email(state: State) -> Command:
    async with (agent_mcp(
            os.getenv("UIPATH_MCP_INTERNAL_SERVER_URL"),
            structured_output = OutputStructure,
            extra_tools = [retrieve_from_execution_context_tool])
    as agent):
        response = await agent.ainvoke(
            {
                "messages":[("system", email_triage_prompt),
                            ("user", "email topic: " + str(state.email_topic.value)),
                            ("user", "email address: " + state.email_address)]
            }
        )
        # Extract the message from the agent's response
        output = response["structured_response"]
        print(output)
        return Command(
            update={
                "agent_message": output["message"],
                "should_continue": output["should_continue"],
            }
        )

async def analyze_email_and_take_action(state: State) -> Command:
    async with agent_mcp(os.getenv("UIPATH_MCP_EXTERNAL_SERVER_URL")) as agent:
        response = await agent.ainvoke(
            {
                "messages":[("system", refund_payment_agent_prompt),
                            ("user", "email content:" + state.email_content),
                            ("user", "email address:" + state.email_address),]
            }
        )
    return Command(
        update={
            "agent_message": str(response["messages"][-1].content),
        }
    )
def collect_output(state: State) -> GraphOutput:
    return GraphOutput(answer=str(state.agent_message))

def decide_next_node_after_email_validation(state: State) -> Literal["analyze_email_and_take_action", "collect_output"]:
    if state.should_continue:
        return "analyze_email_and_take_action"
    return "collect_output"

def decide_next_node_given_email_topic(state: State) -> Literal["collect_output", "check_email"]:
    if state.email_topic == EmailTopic.OTHER:
        return "collect_output"
    return "check_email"

builder = StateGraph(State, input=GraphInput, output=GraphOutput)
builder.add_node("prepare_input", prepare_input)
builder.add_node("check_email", check_email)
builder.add_node("collect_output", collect_output)
builder.add_node("analyze_email_and_take_action", analyze_email_and_take_action)
builder.add_node("understand_email", understand_email)

builder.add_edge(START, "prepare_input")
builder.add_edge("prepare_input", "understand_email")
builder.add_conditional_edges("understand_email", decide_next_node_given_email_topic)
builder.add_conditional_edges("check_email", decide_next_node_after_email_validation)
builder.add_edge("analyze_email_and_take_action", "collect_output")
builder.add_edge("collect_output", END)


graph = builder.compile()
