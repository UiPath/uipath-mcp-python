import asyncio
import random
import time
from typing import Any, Dict

from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP("Long Running Operations MCP Server")


async def run_blocking_operation(
    total_seconds: int,
    progress_interval_seconds: int,
    enable_logs: bool,
    operation_name: str,
    ctx: Context,
) -> Dict[str, Any]:
    """Run a blocking operation with progress notifications."""
    start_time = time.time()

    try:
        # Send initial progress
        await ctx.report_progress(progress=0, total=total_seconds)
        if enable_logs:
            await ctx.info(f"Starting {operation_name}")

        elapsed = 0
        while elapsed < total_seconds:
            await asyncio.sleep(min(progress_interval_seconds, total_seconds - elapsed))
            elapsed = time.time() - start_time

            current_progress = min(elapsed, total_seconds)
            remaining_time = max(0, total_seconds - elapsed)

            message = f"Running {operation_name} - {remaining_time:.1f}s remaining"
            await ctx.report_progress(progress=current_progress, total=total_seconds)

            if enable_logs:
                await ctx.info(
                    f"{operation_name}: {current_progress / total_seconds * 100:.1f}% - {message}"
                )

        # Final completion notification
        await ctx.report_progress(progress=total_seconds, total=total_seconds)
        if enable_logs:
            await ctx.info(f"Completed {operation_name}")

        return {
            "status": "completed",
            "operation_name": operation_name,
            "duration_seconds": total_seconds,
            "actual_elapsed_seconds": elapsed,
            "message": f"{operation_name} completed successfully",
        }

    except Exception as e:
        error_message = f"Error in {operation_name}: {str(e)}"
        await ctx.error(error_message)
        return {
            "status": "error",
            "operation_name": operation_name,
            "error": str(e),
            "message": error_message,
        }


@mcp.tool()
async def run_one_second_task(
    ctx: Context, progress_interval_seconds: int = 1, enable_logs: bool = False
) -> Dict[str, Any]:
    """Run a task that takes approximately 1 second to complete and blocks until finished.

    Args:
        ctx: FastMCP context for client communication
        progress_interval_seconds: Interval in seconds for progress notifications (default: 1)
        enable_logs: Whether to enable detailed logging during the operation (default: False)

    Returns:
        Dictionary containing operation completion details
    """
    operation_name = "One Second Task"

    result = await run_blocking_operation(
        1, progress_interval_seconds, enable_logs, operation_name, ctx
    )

    return result


@mcp.tool()
async def run_one_minute_task(
    ctx: Context, progress_interval_seconds: int = 10, enable_logs: bool = False
) -> Dict[str, Any]:
    """Run a task that takes approximately 1 minute to complete and blocks until finished.

    Args:
        ctx: FastMCP context for client communication
        progress_interval_seconds: Interval in seconds for progress notifications (default: 10)
        enable_logs: Whether to enable detailed logging during the operation (default: False)

    Returns:
        Dictionary containing operation completion details
    """
    operation_name = "One Minute Task"

    result = await run_blocking_operation(
        60, progress_interval_seconds, enable_logs, operation_name, ctx
    )

    return result


@mcp.tool()
async def run_one_hour_task(
    ctx: Context, progress_interval_seconds: int = 300, enable_logs: bool = False
) -> Dict[str, Any]:
    """Run a task that takes approximately 1 hour to complete and blocks until finished.

    Args:
        ctx: FastMCP context for client communication
        progress_interval_seconds: Interval in seconds for progress notifications (default: 300 = 5 minutes)
        enable_logs: Whether to enable detailed logging during the operation (default: False)

    Returns:
        Dictionary containing operation completion details
    """
    operation_name = "One Hour Task"

    result = await run_blocking_operation(
        3600, progress_interval_seconds, enable_logs, operation_name, ctx
    )

    return result


@mcp.tool()
async def run_custom_delay_task(
    ctx: Context,
    seconds: int = 0,
    minutes: int = 0,
    hours: int = 0,
    progress_interval_seconds: int = 30,
    enable_logs: bool = False,
) -> Dict[str, Any]:
    """Run a task with custom delay duration that blocks until finished.

    Args:
        ctx: FastMCP context for client communication
        seconds: Number of seconds to delay (default: 0)
        minutes: Number of minutes to delay (default: 0)
        hours: Number of hours to delay (default: 0)
        progress_interval_seconds: Interval in seconds for progress notifications (default: 30)
        enable_logs: Whether to enable detailed logging during the operation (default: False)

    Returns:
        Dictionary containing operation completion details
    """
    total_seconds = seconds + (minutes * 60) + (hours * 3600)

    if total_seconds <= 0:
        return {
            "status": "error",
            "message": "Total delay must be greater than 0. Please specify seconds, minutes, or hours.",
        }

    operation_name = f"Custom Delay Task ({hours}h {minutes}m {seconds}s)"

    result = await run_blocking_operation(
        total_seconds, progress_interval_seconds, enable_logs, operation_name, ctx
    )

    # Add duration breakdown to result
    result["duration_breakdown"] = {
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
    }

    return result


@mcp.tool()
async def run_random_duration_task(
    ctx: Context,
    max_duration_seconds: int = 100,
    progress_interval_seconds: int = 10,
    enable_logs: bool = False,
) -> Dict[str, Any]:
    """Run a task that takes a random amount of time between 0 and max_duration_seconds.

    Args:
        ctx: FastMCP context for client communication
        max_duration_seconds: Maximum duration in seconds (default: 100)
        progress_interval_seconds: Interval in seconds for progress notifications (default: 10)
        enable_logs: Whether to enable detailed logging during the operation (default: False)

    Returns:
        Dictionary containing operation completion details
    """
    if max_duration_seconds <= 0:
        return {
            "status": "error",
            "message": "max_duration_seconds must be greater than 0.",
        }

    # Generate random duration between 0 and max_duration_seconds
    random_duration = random.uniform(0, max_duration_seconds)
    operation_name = f"Random Duration Task ({random_duration:.1f}s)"

    result = await run_blocking_operation(
        int(random_duration),
        progress_interval_seconds,
        enable_logs,
        operation_name,
        ctx,
    )

    # Add random duration info to result
    result["random_duration_seconds"] = random_duration
    result["max_duration_seconds"] = max_duration_seconds

    return result


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
