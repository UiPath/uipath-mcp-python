from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Code Functions MCP Server")


# Functions registry to track dynamically added code functions
class FunctionRegistry:
    def __init__(self):
        self.functions = {}  # name -> function
        self.metadata = {}  # name -> metadata

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        inputSchema: Dict[str, Any] = None,
    ):
        """Register a new function in the registry."""
        self.functions[name] = func
        self.metadata[name] = {
            "name": name,
            "description": description,
            "inputSchema": inputSchema or {},
        }

    def get_function(self, name: str) -> Optional[Callable]:
        """Get a function by name."""
        return self.functions.get(name)

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get function metadata by name."""
        return self.metadata.get(name)

    def list_functions(self) -> List[Dict[str, Any]]:
        """List all registered functions."""
        return [self.metadata[name] for name in sorted(self.functions.keys())]

    def has_function(self, name: str) -> bool:
        """Check if a function exists."""
        return name in self.functions


registry = FunctionRegistry()


@mcp.tool()
async def get_functions() -> List[Dict[str, Any]]:
    """Get a list of all available registered functions in the MCP server.

    Returns:
        List of available functions and their metadata
    """
    return registry.list_functions()


@mcp.tool()
def add_function(
    name: str = None,
    code: str = None,
    description: str = None,
    inputSchema: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Add a new function to the MCP server by providing its Python code.

    Args:
        name: Name of the function (required)
        code: Python code implementing the function's function. Must define a function with the specified 'name'. Type hints in the function signature will be used to infer the input schema. (required)
        description: Description of what the function does (required)
        inputSchema: JSON schema object describing the parameters the new function expects (optional). This schema will be returned by get_functions and used for documentation.

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
                "example": "add_function(name='function_name', code='def function_name(param1: str, param2: str):\\n    # code here\\n    return {\"status\": \"success\"}', description='Function description', inputSchema={'param1': 'Description of param1', 'param2': 'Description of param2'})",
            }

        # Track if we're replacing an existing function
        function_exists = registry.has_function(name) or hasattr(mcp, name)

        # Validate the code
        try:
            # Add the function to the global namespace
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

            # Register the function, overwriting if it already exists
            registry.register(name, func, description, inputSchema)

            # Get the parameter information to return
            params = registry.get_metadata(name)["inputSchema"]

            # Determine the appropriate status message
            status_msg = "added" if not function_exists else "updated"

            return {
                "status": "success",
                "message": f"Function '{name}' {status_msg} successfully",
                "inputSchema": params,
            }

        except SyntaxError as e:
            return {
                "status": "error",
                "message": f"Syntax error in function code: {str(e)}",
            }
        except Exception as e:
            return {"status": "error", "message": f"Error creating function: {str(e)}"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def call_function(name: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
    """Call a registered dynamic function with the given arguments.

    Args:
        name: Name of the dynamic function to call (required)
        args: Dictionary of arguments to pass to the function. You should consult the function's schema from get_functions to know the expected structure. (required)

    Returns:
        Dictionary with the function's response
    """

    args = args or {}

    try:
        # Get the function
        function = registry.get_function(name)

        if not function:
            return {
                "status": "error",
                "message": f"Function '{name}' not found",
                "available_functions": [t["name"] for t in registry.list_functions()],
            }

        # Call the function with the provided arguments
        try:
            result = function(**args)
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
                "message": f"Argument error calling function '{name}': {str(e)}. Please fix your mistakes, add proper 'args' values!",
                "inputSchema": params,
                "example": f"call_function(name='{name}', args={usage_str})",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error calling function '{name}': {str(e)}",
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
