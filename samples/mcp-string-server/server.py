"""String operations MCP server running over streamable HTTP."""

from typing import Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("String Operations Server", host="127.0.0.1", port=8080)


@mcp.tool()
def reverse_string(text: str) -> str:
    """Reverse a string.

    Args:
        text: The string to reverse

    Returns:
        The reversed string
    """
    return text[::-1]


@mcp.tool()
def to_uppercase(text: str) -> str:
    """Convert a string to uppercase.

    Args:
        text: The string to convert

    Returns:
        The uppercase string
    """
    return text.upper()


@mcp.tool()
def to_lowercase(text: str) -> str:
    """Convert a string to lowercase.

    Args:
        text: The string to convert

    Returns:
        The lowercase string
    """
    return text.lower()


@mcp.tool()
def count_words(text: str) -> int:
    """Count the number of words in a string.

    Args:
        text: The string to count words in

    Returns:
        The number of words

    Raises:
        ValueError: If text is empty or whitespace only
    """
    if not text.strip():
        raise ValueError("Cannot count words in an empty string")
    return len(text.split())


@mcp.tool()
def replace_text(text: str, old: str, new: str) -> str:
    """Replace all occurrences of a substring with another.

    Args:
        text: The original string
        old: The substring to find
        new: The substring to replace with

    Returns:
        The string with replacements applied
    """
    return text.replace(old, new)


@mcp.tool()
def trim(text: str) -> str:
    """Remove leading and trailing whitespace from a string.

    Args:
        text: The string to trim

    Returns:
        The trimmed string
    """
    return text.strip()


@mcp.tool()
def split_string(text: str, delimiter: str = " ") -> List[str]:
    """Split a string by a delimiter.

    Args:
        text: The string to split
        delimiter: The delimiter to split by (default is space)

    Returns:
        List of substrings
    """
    return text.split(delimiter)


@mcp.tool()
def join_strings(strings: List[str], delimiter: str = " ") -> str:
    """Join a list of strings with a delimiter.

    Args:
        strings: List of strings to join
        delimiter: The delimiter to join with (default is space)

    Returns:
        The joined string
    """
    return delimiter.join(strings)


@mcp.tool()
def is_palindrome(text: str) -> bool:
    """Check if a string is a palindrome (ignoring case and spaces).

    Args:
        text: The string to check

    Returns:
        True if the string is a palindrome
    """
    cleaned = text.lower().replace(" ", "")
    return cleaned == cleaned[::-1]


@mcp.tool()
def char_frequency(text: str) -> Dict[str, int]:
    """Count the frequency of each character in a string.

    Args:
        text: The string to analyze

    Returns:
        Dictionary mapping each character to its frequency
    """
    freq: Dict[str, int] = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1
    return freq


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
