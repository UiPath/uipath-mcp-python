import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from retry import retry


def get_required_env_var(name: str) -> str:
    """Get required environment variable or raise an error if not set."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value

@retry(tries=3, delay=2, backoff=2)
async def call_datetime_tools():
    # Load configuration from environment variables
    base_url = get_required_env_var("BASE_URL")
    folder_key = get_required_env_var("UIPATH_FOLDER_KEY")
    token = get_required_env_var("UIPATH_ACCESS_TOKEN")
    mcp_server_name = get_required_env_var("MCP_SERVER_NAME")

    # Construct the MCP server URL
    mcp_url = f"{base_url}/agenthub_/mcp/{folder_key}/{mcp_server_name}"

    try:
        # Use streamable HTTP client to connect to the MCP server
        async with streamablehttp_client(mcp_url, headers={ 'Authorization': f'Bearer {token}' }) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize the session
                await session.initialize()

                # List available tools
                tools_result = await session.list_tools()
                available_tools = [tool.name for tool in tools_result.tools]
                expected_available_tools = [
                    "current_utc_time", "days_between", "add_days", "day_of_week",
                    "is_leap_year", "days_in_month", "time_difference", "is_weekend"
                ]

                print (f"Available tools: {available_tools}")

                if set(available_tools) != set(expected_available_tools):
                    raise AssertionError(f"Tool sets don't match. Expected: {set(expected_available_tools)}, Got: {set(available_tools)}")

                # Call the days_between tool
                call_tool_result = await session.call_tool(name="days_between", arguments={"date1": "2024-01-01", "date2": "2024-01-31"})

                expected_result = "30"
                actual_result = call_tool_result.content[0].text if call_tool_result.content else None

                if actual_result != expected_result:
                    raise AssertionError(f"Expected {expected_result}, got {actual_result}")

                # Call the is_leap_year tool
                call_tool_result = await session.call_tool(name="is_leap_year", arguments={"year": 2024})

                expected_result = "true"
                actual_result = call_tool_result.content[0].text.lower() if call_tool_result.content else None

                if actual_result != expected_result:
                    raise AssertionError(f"Expected {expected_result}, got {actual_result}")

                print("Test completed successfully")
    except Exception as e:
        print(f"Unexpected error connecting to MCP server: {e}")
        raise AssertionError(f"Connection error, {e}") from e

async def main():
    """Main async function to run the test."""
    try:
        load_dotenv()

        await call_datetime_tools()
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
