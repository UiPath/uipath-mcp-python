# MCP DateTime Server

A sample MCP server that exposes date and time utility tools over Streamable HTTP transport, built with the UiPath MCP SDK (`FastMCP`).

## Tools

| Tool | Description |
|------|-------------|
| `current_utc_time` | Returns the current UTC date/time in ISO 8601 format |
| `days_between` | Calculates absolute days between two dates |
| `add_days` | Adds or subtracts days from a date |
| `day_of_week` | Returns the day name for a given date |
| `is_leap_year` | Checks if a year is a leap year |
| `days_in_month` | Returns the number of days in a given month/year |
| `time_difference` | Calculates difference between two datetimes (days, hours, minutes, seconds) |
| `is_weekend` | Checks if a date falls on Saturday or Sunday |

## Running

```bash
uipath run mcp-datetime-server
```
