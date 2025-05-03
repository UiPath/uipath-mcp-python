from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Self-Extending MCP Server")


# Tool registry to track dynamically added tools
class ToolRegistry:
    def __init__(self):
        self.tools = {}  # name -> function
        self.metadata = {}  # name -> metadata

    def register(self, name: str, func: Callable, description: str):
        """Register a new tool in the registry."""
        self.tools[name] = func
        self.metadata[name] = {"name": name, "description": description}

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

        # Add the built-in tools
        built_in_tools = ["get_tools", "add_tool", "call_tool"]

        # Combine built-in tools with dynamic tools
        all_tools = [{"name": tool, "built_in": True} for tool in built_in_tools]
        for tool in tools:
            all_tools.append(
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "built_in": False,
                }
            )

        return {"status": "success", "tools": all_tools}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Core functionality: Add a new tool
@mcp.tool()
def add_tool(name: str, code: str, description: str) -> Dict[str, Any]:
    """Add a new tool to the MCP server.

    Args:
        name: Name of the tool
        code: Python code implementing the tool function
        description: Description of what the tool does

    Returns:
        Dictionary with operation status
    """
    try:
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
            registry.register(name, func, description)

            return {"status": "success", "message": f"Tool '{name}' added successfully"}

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
def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Call a registered tool with the given arguments.

    Args:
        name: Name of the tool to call
        args: Dictionary of arguments to pass to the tool

    Returns:
        Dictionary with the tool's response
    """
    try:
        # Check if it's a built-in tool
        if name in ["get_tools", "add_tool", "call_tool"]:
            return {
                "status": "error",
                "message": f"Cannot call built-in tool '{name}' using call_tool",
            }

        # Get the tool
        tool = registry.get_tool(name)

        if not tool:
            return {"status": "error", "message": f"Tool '{name}' not found"}

        # Call the tool with the provided arguments
        try:
            result = tool(**args)
            return result
        except TypeError as e:
            # Likely an argument mismatch
            return {
                "status": "error",
                "message": f"Argument error calling tool '{name}': {str(e)}",
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
