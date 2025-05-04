from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Self-Extending MCP Server")


@mcp.tool()
def add_tool(
    name: str = None,
    code: str = None,
    description: str = None,
    inputSchema: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Add a new tool to the MCP server by providing its Python code.

    Args:
        name: Name of the tool (required)
        code: Python code implementing the tool's function. Must define a function with the specified 'name'. Type hints in the function signature will be used to infer the input schema. (required)
        description: Description of what the tool does (required)
        inputSchema: JSON schema object describing the parameters the new tool expects (optional). This schema will be returned by get_tools and used for documentation.

    Returns:
        Dictionary with operation status
    """
    try:
        # Validate required parameters
        missing_params = []
        if name is None:
            missing_params.append("name")
        if code is None:
            missing_params.append("code")
        if description is None:
            missing_params.append("description")

        if missing_params:
            return {
                "status": "error",
                "message": f"Missing required parameters: {', '.join(missing_params)}",
                "example": "add_tool(name='tool_name', code='def tool_name(param1: str, param2: str):\\n    # code here\\n    return {\"status\": \"success\"}', description='Tool description', inputSchema={'param1': 'Description of param1', 'param2': 'Description of param2'})",
            }

        # Check if tool already exists
        existing_tools = [tool.name for tool in mcp._tool_manager.list_tools()]
        if name in existing_tools:
            return {"status": "error", "message": f"Tool '{name}' already exists"}

        # Validate the code
        try:
            # Add the tool function to the global namespace
            namespace = {}
            exec(code, namespace)

            if name not in namespace or not callable(namespace[name]):
                return {
                    "status": "error",
                    "message": f"Valid function '{name}' not found in code",
                }

            # Register the tool with fast mcp
            mcp._tool_manager.add_tool(
                namespace[name], name=name, description=description
            )

            return {
                "status": "success",
                "message": f"Tool '{name}' added successfully",
                "inputSchema": inputSchema,
            }

        except SyntaxError as e:
            return {
                "status": "error",
                "message": f"Syntax error in tool code: {str(e)}",
            }
        except Exception as e:
            return {"status": "error", "message": f"Error creating tool: {str(e)}"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
