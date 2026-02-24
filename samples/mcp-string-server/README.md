# MCP String Server

A sample MCP server that exposes string manipulation tools over Streamable HTTP transport, built with the UiPath MCP SDK (`FastMCP`).

## Tools

| Tool | Description |
|------|-------------|
| `reverse_string` | Reverses the input string |
| `to_uppercase` | Converts a string to uppercase |
| `to_lowercase` | Converts a string to lowercase |
| `count_words` | Counts the number of words in a string |
| `replace_text` | Replaces all occurrences of a substring |
| `trim` | Removes leading and trailing whitespace |
| `split_string` | Splits a string by a delimiter |
| `join_strings` | Joins a list of strings with a delimiter |
| `is_palindrome` | Checks if a string is a palindrome (ignoring case/spaces) |
| `char_frequency` | Returns character frequency counts |

## Running

```bash
uipath run mcp-string-server
```
