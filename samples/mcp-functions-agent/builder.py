import os
from contextlib import asynccontextmanager

import dotenv
from langchain.output_parsers import PydanticOutputParser
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel
from uipath_langchain.chat.models import UiPathAzureChatOpenAI

dotenv.load_dotenv()


class GraphInput(BaseModel):
    """Input containing a query about what function to build"""

    query: str


class GraphOutput(BaseModel):
    """Final function code"""

    function_code: str


class Spec(BaseModel):
    name: str
    description: str
    input_schema: str
    expected_behavior: str


class GraphState(AgentState):
    """Graph state"""

    name: str = ""
    description: str = ""
    input_schema: str = ""
    expected_behavior: str = ""
    validation_feedback: str = ""
    attempts: int = 0


FUNCTIONS_MCP_SERVER_URL = os.getenv("FUNCTIONS_MCP_SERVER_URL")
UIPATH_ACCESS_TOKEN = os.getenv("UIPATH_ACCESS_TOKEN")


@asynccontextmanager
async def make_graph():
    async with streamablehttp_client(
        url=FUNCTIONS_MCP_SERVER_URL,
        headers={"Authorization": f"Bearer {UIPATH_ACCESS_TOKEN}"},
        timeout=60,
    ) as (read, write, session_id_callback):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)

            model = UiPathAzureChatOpenAI(
                model="gpt-4.1-2025-04-14",
                temperature=0,
                max_tokens=10000,
                timeout=120,
                max_retries=2,
            )

            async def planner_agent(input: GraphInput) -> GraphState:
                """Determines the function details based on the user query"""

                planning_parser = PydanticOutputParser(pydantic_object=Spec)
                planning_prompt = f"""You are a planning agent that analyzes user requests for Python functions and determines the appropriate function specifications.

Based on the user's query, determine:
1. A clear, concise function name following Python naming conventions
2. A detailed description of what the function should do
3. An input JSON schema specifying all parameters the function should accept
4. The expected behavior including example inputs and outputs

The user requested: {input.query}

Format your response as a JSON object with the following keys:
- name: The function name (snake_case)
- description: Detailed description
- input_schema: JSON schema for the input parameters
- expected_behavior: Clear explanation of what the function should return and how it should handle different cases

Respond with a JSON object containing:
{planning_parser.get_format_instructions()}
"""

                result = await model.ainvoke(planning_prompt)

                specs = planning_parser.parse(result.content)

                # Return the specifications along with the original query
                return {
                    "name": specs.name,
                    "description": specs.description,
                    "input_schema": specs.input_schema,
                    "expected_behavior": specs.expected_behavior,
                }

            async def builder_agent(state: GraphState) -> GraphState:
                system_message = f"""You are a professional developer tasked with creating a Python function.

Function Name: {state.get("name")}
Function Description: {state.get("description")}
Input JSON Schema: {state.get("input_schema")}
Expected Behavior: {state.get("expected_behavior")}
"""

                if state.get("validation_feedback"):
                    print(state.get("validation_feedback"))
                    system_message += f"""
Previous validation feedback:
{state.get("validation_feedback")}

Based on this feedback, improve your implementation of the function.
"""

                system_message += """
Write Python code that implements this function. The code MUST:
1. Define a SINGLE function with the specified name that accepts input parameters according to the INPUT JSON Schema parameters list
2. Return the expected outputs as specified in the expected behavior
3. Be robust, handle edge cases, and include appropriate error handling
4. Use ONLY Python's standard library - DO NOT use ANY external libraries or subprocess calls
5. If you need to parse or analyze code, use Python's built-in modules like ast, tokenize, etc.
6. If you need to handle web requests, use only urllib from the standard library

You MUST start by registering the code using the `add_function` tool. The function's description must also contain the expected behavior with example inputs/outputs. You MUST specify the INPUT JSON SCHEMA.
Then you must respond with the complete function code.
IMPORTANT: Your response should only contain the complete function code as a clearly formatted Python code block. This is crucial as the final function code will be extracted from your response.
"""

                add_tool = [tool for tool in tools if tool.name == "add_function"]

                agent = create_react_agent(model, tools=add_tool, prompt=system_message)
                result = await agent.ainvoke(state)

                # Extract the builder's message
                builder_message = result["messages"][-1]
                updated_messages = state.get("messages", []) + [builder_message]

                # Increment the attempts counter and save the extracted code
                attempts = state.get("attempts", 0) + 1
                return {
                    **state,
                    "messages": updated_messages,
                    "attempts": attempts,
                }

            async def validator_agent(state: GraphState) -> GraphState:
                # Create mock test cases based on expected behavior
                test_case_prompt = f"""Create 3 test cases with real but MINIMAL data for this tool:

                Function Name: {state.get("name")}
                Function Description: {state.get("description")}
                Input Schema: {state.get("input_schema")}
                Expected Behavior: {state.get("expected_behavior")}

                This function may depend on specific data or files being present for testing. To generate realistic and minimal test cases:

                1. If files or input data need to exist before the function runs:
                - Define a **setup function** using the `add_function` tool.
                - This setup function can create any necessary files, folders, or data structures required for valid input.
                - You may generate sample files with small, valid content.

                2. Use `call_function` to execute the setup function and create the test environment.

                3. Based on the environment created, define test case inputs that match the input schema, and describe expected results.

                4. Return a list of 3 test cases. Each test case must include:
                - `"input"`: The actual input values for the main function, based on the seeded environment
                - `"expected_output"`: What the function should return

                **Example use case:** If the function reads files from disk, your setup function should create a temporary folder and write some files into it. Then, test the function against that folder path.
                """

                seeder = create_react_agent(model, tools=tools, prompt=test_case_prompt)

                test_result = await seeder.ainvoke(state)

                system_message = f"""You are a function validator. Test if this function works correctly:

                Function Name: {state.get("name")}
                Function Description: {state.get("description")}
                Input Schema: {state.get("input_schema")}

                Test Cases:
                {test_result["messages"][-1].content}

                Use the call_function tool with these test cases and verify the results match expected outputs.

                If the function doesn't work with the test cases:
                1. Explain EXACTLY what went wrong
                2. Provide CLEAR feedback on how to fix the issues
                3. Be specific about what changes are needed

                If all of the test cases are successful, you MUST reply with "ALL TESTS PASSED".
                """

                validator = create_react_agent(
                    model, tools=tools, prompt=system_message
                )

                validation_result = await validator.ainvoke(state)

                validation_message = validation_result["messages"][-1].content

                return {**state, "validation_feedback": validation_message}

            async def extractor_agent(state: GraphState) -> GraphOutput:
                # The function code is already extracted and stored in the state
                # Just return it as the output
                return GraphOutput(function_code=state.get("messages")[-1].content)

            def should_continue_loop(state: GraphState):
                # Continue the loop if:
                # 1. Tests haven't passed yet (feedback doesn't contain "ALL TESTS PASSED")
                # 2. We haven't exceeded the maximum number of attempts (5)
                return (
                    "ALL TESTS PASSED" not in state.get("validation_feedback").upper()
                    and state.get("attempts") < 5
                )

            # Build the workflow
            workflow = StateGraph(GraphState, input=GraphInput, output=GraphOutput)

            workflow.add_node("planner_agent", planner_agent)
            workflow.add_node("builder_agent", builder_agent)
            workflow.add_node("validator_agent", validator_agent)
            workflow.add_node("extractor_agent", extractor_agent)

            workflow.add_edge("planner_agent", "builder_agent")
            workflow.add_edge("builder_agent", "validator_agent")
            workflow.add_edge("validator_agent", "extractor_agent")
            workflow.add_edge("extractor_agent", END)

            workflow.set_entry_point("planner_agent")

            workflow.add_conditional_edges(
                "validator_agent",
                lambda s: "builder_agent"
                if should_continue_loop(s)
                else "extractor_agent",
            )

            # Compile the graph
            graph = workflow.compile()

            yield graph
