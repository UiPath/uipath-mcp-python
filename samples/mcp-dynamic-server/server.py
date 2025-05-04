from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool as MCPTool

# Initialize the MCP server
mcp = FastMCP("Self-Extending MCP Server")

built_in_tools: List[MCPTool] = [
    MCPTool(
        name="add_tool",
        description="Add a new tool to the MCP server by providing its Python code.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the tool"},
                "code": {
                    "type": "string",
                    "description": "Python code implementing the tool's function. Must define a function with the specified 'name'. Type hints in the function signature for the input schema.",
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the tool does",
                },
                "inputSchema": {
                    "type": "object",
                    "description": "JSON schema object describing the parameters the new tool expects (optional). This schema will be returned by get_tools and used for documentation.",
                },
            },
            "required": ["name", "code", "description"],
        },
    ),
    MCPTool(
        name="call_tool",
        description="Call a registered dynamic tool with the given arguments.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the dynamic tool to call",
                },
                "args": {
                    "type": "object",
                    "description": "Dictionary of arguments to pass to the tool. Must conform to the dynamic tool's inferred JSON input schema.",
                },
            },
            "required": ["name", "args"],
        },
    ),
]


# Tool registry to track dynamically added tools
class ToolRegistry:
    def __init__(self):
        self.tools = {}  # name -> function
        self.metadata = {}  # name -> metadata

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        inputSchema: Dict[str, Any] = None,
    ):
        """Register a new tool in the registry."""
        self.tools[name] = func
        self.metadata[name] = {
            "name": name,
            "description": description,
            "inputSchema": inputSchema or {},
        }

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tool metadata by name."""
        return self.metadata.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        return [self.metadata[name] for name in sorted(self.tools.keys())]

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self.tools


registry = ToolRegistry()


@mcp._mcp_server.list_tools()
async def get_tools() -> List[MCPTool]:
    """Get a list of all available tools in the MCP server.

    Returns:
        List of available tools and their metadata
    """
    all_tools = list(built_in_tools)

    tools = registry.list_tools()

    for tool in tools:
        all_tools.append(
            MCPTool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
            )
        )

    return all_tools


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
        if registry.has_tool(name) or hasattr(mcp, name):
            return {"status": "error", "message": f"Tool '{name}' already exists"}

        # Validate the code
        try:
            # Add the tool function to the global namespace
            namespace = {}
            exec(code, namespace)

            # Get the function
            if name not in namespace:
                return {
                    "status": "error",
                    "message": f"Function '{name}' not found in the provided code",
                }

            func = namespace[name]

            # Check if it's a function
            if not callable(func):
                return {
                    "status": "error",
                    "message": f"'{name}' is not a callable function",
                }

            # Register the tool with our registry
            registry.register(name, func, description, inputSchema)

            # Get the parameter information to return
            params = registry.get_metadata(name)["inputSchema"]

            return {
                "status": "success",
                "message": f"Tool '{name}' added successfully",
                "inputSchema": params,
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


@mcp.tool()
def call_tool(name: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
    """Call a registered dynamic tool with the given arguments.

    Args:
        name: Name of the dynamic tool to call (required)
        args: Dictionary of arguments to pass to the tool. You should consult the tool's schema from get_tools to know the expected structure. (required)

    Returns:
        Dictionary with the tool's response
    """

    args = args or {}

    try:
        # Check if it's a built-in tool
        matching_tool = next((tool for tool in built_in_tools if tool.name == name), None)
        if matching_tool:
            return {
                "status": "error",
                "message": f"Cannot call built-in tool '{name}' using call_tool",
                "note": f"Use the {name} function directly instead of call_tool",
                "inputSchema": matching_tool.inputSchema,
            }

        # Get the tool
        tool = registry.get_tool(name)

        if not tool:
            return {
                "status": "error",
                "message": f"Tool '{name}' not found",
                "available_tools": [t["name"] for t in registry.list_tools()],
            }

        # Call the tool with the provided arguments
        try:
            result = tool(**args)
            return result
        except TypeError as e:
            # Likely an argument mismatch
            params = registry.get_metadata(name)["inputSchema"]

            # Build a usage example with actual parameter names
            param_examples = {}

            # Handle different possible inputSchema structures
            if isinstance(params, dict):
                if "properties" in params:
                    # Standard JSON Schema format
                    for param_name in params["properties"]:
                        param_examples[param_name] = f"<{param_name}_value>"
                else:
                    # Simple dict of param_name -> description
                    for param_name in params:
                        param_examples[param_name] = f"<{param_name}_value>"

            # If no parameters found or empty schema, provide generic example
            if not param_examples:
                param_examples = {"param1": "<value1>", "param2": "<value2>"}

            # Format the dictionary for better readability
            usage_str = str(param_examples).replace("'<", "<").replace(">'", ">")

            return {
                "status": "error",
                "message": f"Argument error calling tool '{name}': {str(e)}. Please fix your mistakes, add proper 'args' values!",
                "inputSchema": params,
                "example": f"call_tool(name='{name}', args={usage_str})",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error calling tool '{name}': {str(e)}",
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
