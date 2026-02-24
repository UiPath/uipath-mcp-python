"""Date and time operations MCP server running over streamable HTTP."""

from datetime import datetime, timedelta, timezone
from typing import Dict

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DateTime Operations Server", host="127.0.0.1", port=8080)


@mcp.tool()
def current_utc_time() -> str:
    """Get the current UTC date and time in ISO 8601 format.

    Returns:
        Current UTC datetime as an ISO 8601 string
    """
    return datetime.now(timezone.utc).isoformat()


@mcp.tool()
def days_between(date1: str, date2: str) -> int:
    """Calculate the number of days between two dates.

    Args:
        date1: First date in ISO 8601 format
        date2: Second date in ISO 8601 format

    Returns:
        Absolute number of days between the two dates
    """
    dt1 = datetime.fromisoformat(date1)
    dt2 = datetime.fromisoformat(date2)
    return abs((dt2 - dt1).days)


@mcp.tool()
def add_days(date_string: str, days: int) -> str:
    """Add or subtract days from a date.

    Args:
        date_string: Starting date in ISO 8601 format
        days: Number of days to add (negative to subtract)

    Returns:
        The resulting date in ISO 8601 format
    """
    dt = datetime.fromisoformat(date_string)
    result = dt + timedelta(days=days)
    return result.isoformat()


@mcp.tool()
def day_of_week(date_string: str) -> str:
    """Get the day of the week for a given date.

    Args:
        date_string: Date in ISO 8601 format

    Returns:
        Name of the day of the week (e.g. "Monday")
    """
    dt = datetime.fromisoformat(date_string)
    return dt.strftime("%A")


@mcp.tool()
def is_leap_year(year: int) -> bool:
    """Check if a given year is a leap year.

    Args:
        year: The year to check

    Returns:
        True if the year is a leap year
    """
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


@mcp.tool()
def days_in_month(year: int, month: int) -> int:
    """Get the number of days in a given month.

    Args:
        year: The year
        month: The month (1-12)

    Returns:
        Number of days in the month

    Raises:
        ValueError: If month is not between 1 and 12
    """
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and is_leap_year(year):
        return 29
    return days[month - 1]


@mcp.tool()
def time_difference(datetime1: str, datetime2: str) -> Dict[str, int]:
    """Calculate the difference between two datetimes.

    Args:
        datetime1: First datetime in ISO 8601 format
        datetime2: Second datetime in ISO 8601 format

    Returns:
        Dictionary with days, hours, minutes, and seconds of difference
    """
    dt1 = datetime.fromisoformat(datetime1)
    dt2 = datetime.fromisoformat(datetime2)
    diff = abs(dt2 - dt1)
    total_seconds = int(diff.total_seconds())
    days = diff.days
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return {"days": days, "hours": hours, "minutes": minutes, "seconds": seconds}


@mcp.tool()
def is_weekend(date_string: str) -> bool:
    """Check if a given date falls on a weekend.

    Args:
        date_string: Date in ISO 8601 format

    Returns:
        True if the date is Saturday or Sunday
    """
    dt = datetime.fromisoformat(date_string)
    return dt.weekday() >= 5


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
