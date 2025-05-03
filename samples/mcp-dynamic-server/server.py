from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Self-Extending MCP Server")

built_in_tools = {
    "get_tools": {
        "description": "Get a list of all available tools in the MCP server.",
        "parameters": {}
    },
    "add_tool": {
        "description": "Add a new tool to the MCP server.",
        "parameters": {
            "name": "Name of the tool (required)",
            "code": "Python code implementing the tool function (required)",
            "description": "Description of what the tool does (required)",
            "param_descriptions": "Dictionary of parameter names to descriptions (optional)"
        }
    },
    "call_tool": {
        "description": "Call a registered tool with the given arguments.",
        "parameters": {
            "name": "Name of the tool to call (required)",
            "args": "Dictionary of arguments to pass to the tool"
        }
    }
}

# Tool registry to track dynamically added tools
class ToolRegistry:
    def __init__(self):
        self.tools = {}  # name -> function
        self.metadata = {}  # name -> metadata

    def register(self, name: str, func: Callable, description: str, param_descriptions: Dict[str, str] = None):
        """Register a new tool in the registry."""
        self.tools[name] = func
        self.metadata[name] = {
            "name": name,
            "description": description,
            "parameters": param_descriptions or {}
        }

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_metadata(self, name: str) -> Optional[Dict]:
        """Get tool metadata by name."""
        return self.metadata.get(name)

    def list_tools(self) -> List[Dict]:
        """List all registered tools."""
        return [self.metadata[name] for name in sorted(self.tools.keys())]

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self.tools


# Create the registry
registry = ToolRegistry()


# Core functionality: List available tools
@mcp.tool()
def get_tools() -> Dict[str, Any]:
    """Get a list of all available tools in the MCP server.

    Returns:
        Dictionary with list of available tools and their metadata
    """
    try:
        tools = registry.list_tools()

        # Combine built-in tools with dynamic tools
        all_tools = []
        for name, info in built_in_tools.items():
            all_tools.append({
                "name": name,
                "description": info["description"],
                "parameters": info["parameters"],
                "built_in": True
            })

        for tool in tools:
            all_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "built_in": False
            })

        return {"status": "success", "tools": all_tools}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Core functionality: Add a new tool
@mcp.tool()
def add_tool(name: str = None, code: str = None, description: str = None, param_descriptions: Dict[str, str] = None) -> Dict[str, Any]:
    """Add a new tool to the MCP server.

    Args:
        name: Name of the tool
        code: Python code implementing the tool function
        description: Description of what the tool does
        param_descriptions: Dictionary of parameter names to descriptions

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
                "usage_example": "add_tool(name='tool_name', code='def tool_name(param1, param2):\\n    # code here\\n    return {\"status\": \"success\"}', description='Tool description', param_descriptions={'param1': 'Description of param1', 'param2': 'Description of param2'})"
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
            registry.register(name, func, description, param_descriptions)

            # Get the parameter information to return
            params = registry.get_metadata(name)["parameters"]

            return {
                "status": "success",
                "message": f"Tool '{name}' added successfully",
                "parameters": params
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


# Core functionality: Call a tool
@mcp.tool()
def call_tool(name: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
    """Call a registered tool with the given arguments.

    Args:
        name: Name of the tool to call
        args: Dictionary of arguments to pass to the tool

    Returns:
        Dictionary with the tool's response
    """

    args = args or {}

    try:
        # Check if it's a built-in tool
        if name in built_in_tools:
            return {
                "status": "error",
                "message": f"Cannot call built-in tool '{name}' using call_tool",
                "note": f"Use the {name} function directly instead of call_tool",
                "parameters": built_in_tools[name]["parameters"]
            }

        # Get the tool
        tool = registry.get_tool(name)

        if not tool:
            return {
                "status": "error",
                "message": f"Tool '{name}' not found",
                "available_tools": [t["name"] for t in registry.list_tools()]
            }

        # Call the tool with the provided arguments
        try:
            result = tool(**args)
            return result
        except TypeError as e:
            # Likely an argument mismatch
            params = registry.get_metadata(name)["parameters"]
            return {
                "status": "error",
                "message": f"Argument error calling tool '{name}': {str(e)}",
                "expected_parameters": params,
                "usage_example": f"call_tool(name='{name}', args={{'param1': value1, 'param2': value2, ...}})"
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
