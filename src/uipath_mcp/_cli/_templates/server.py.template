import math
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Advanced Math Operations Server")

# Basic arithmetic operations
@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of a and b
    """
    return a * b



# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
