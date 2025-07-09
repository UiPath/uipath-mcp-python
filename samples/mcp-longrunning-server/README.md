# Long Running Operations MCP Server

This sample demonstrates how to create an MCP server that handles long-running operations with real-time progress tracking and client notifications. All operations block until completion, providing synchronous execution with live progress updates.

## Overview

The Long Running Operations MCP Server provides tools for executing blocking tasks that take varying amounts of time, with real-time progress monitoring and optional detailed logging. Operations block until completion while providing continuous progress updates to clients. This is particularly useful for automation scenarios that involve time-consuming operations like data processing, file transfers, or system maintenance tasks.

## Features

### Core Tools

1. **run_one_second_task** - Execute a blocking 1-second task with progress tracking
2. **run_one_minute_task** - Execute a blocking 1-minute task with progress tracking
3. **run_one_hour_task** - Execute a blocking 1-hour task with progress tracking
4. **run_custom_delay_task** - Execute a blocking task with custom duration (seconds, minutes, hours)
5. **run_random_duration_task** - Execute a blocking task with random duration (0 to max_duration_seconds)

### Key Features

- **Blocking execution** - Operations block until completion, providing synchronous behavior
- **Real-time progress notifications** - Direct client notifications via `ctx.report_progress()`
- **Live client logging** - Messages sent directly to clients via `ctx.info()` and `ctx.error()`
- **Configurable intervals** - Customizable progress update frequencies
- **Completion results** - Detailed results returned upon task completion
- **Optional detailed logging** - Enhanced logging during operation execution

## Installation

```bash
uv venv -p 3.11 .venv
.venv\Scripts\activate
uv sync
```

## Parameters

### Common Parameters

- **progress_interval_seconds** - How often to send progress notifications (in seconds)
- **enable_logs** - Whether to capture detailed logs during the operation

### Custom Delay Parameters

- **seconds** - Number of seconds to delay
- **minutes** - Number of minutes to delay  
- **hours** - Number of hours to delay

## Response Format

### Completion Response

```json
{
  "status": "completed",
  "operation_name": "One Minute Task",
  "duration_seconds": 60,
  "actual_elapsed_seconds": 60.1,
  "message": "One Minute Task completed successfully"
}
```

### Custom Task Response

```json
{
  "status": "completed",
  "operation_name": "Custom Delay Task (2h 30m 0s)",
  "duration_seconds": 9000,
  "actual_elapsed_seconds": 9000.3,
  "duration_breakdown": {
    "hours": 2,
    "minutes": 30,
    "seconds": 0
  },
  "message": "Custom Delay Task (2h 30m 0s) completed successfully"
}
```

### Random Duration Task Response

```json
{
  "status": "completed",
  "operation_name": "Random Duration Task (47.3s)",
  "duration_seconds": 47,
  "actual_elapsed_seconds": 47.1,
  "random_duration_seconds": 47.3,
  "max_duration_seconds": 100,
  "message": "Random Duration Task (47.3s) completed successfully"
}
```

### Error Response

```json
{
  "status": "error",
  "operation_name": "One Hour Task",
  "error": "Operation interrupted",
  "message": "Error in One Hour Task: Operation interrupted"
}
```

## Progress Tracking and Notifications

The server provides real-time progress tracking during blocking operations:

1. **Real-time Progress Updates** - Continuous progress reports sent directly to clients via `ctx.report_progress()`
2. **Client Log Messages** - Optional detailed messages sent directly to clients via `ctx.info()` (when `enable_logs=True`)
3. **Error Notifications** - Immediate error messages sent directly to clients via `ctx.error()`
4. **Completion Results** - Detailed results returned upon task completion

## Use Cases

- **Data Processing** - Long-running data transformation or analysis tasks with progress tracking
- **File Operations** - Large file transfers, backups, or synchronization with completion confirmation
- **System Maintenance** - Scheduled maintenance tasks with real-time status updates
- **Integration Testing** - Simulating long-running external API calls with progress monitoring
- **Batch Processing** - Processing queues or large datasets with completion results
- **Deployment Operations** - Application deployments with step-by-step progress tracking
- **Workflow Automation** - UiPath automation tasks that require timed delays with progress feedback

## Configuration

Standard MCP configuration files:

- `mcp.json` - Server transport and command configuration
- `pyproject.toml` - Python project dependencies
- `uipath.json` - UiPath platform integration settings

## Running the Server

```bash
# Local debugging
uipath run longrunning-server

# Package and deploy
uipath pack
uipath publish
```

## Error Handling

The server includes comprehensive error handling:

- Invalid duration parameters with immediate error responses
- Exception handling with detailed error messages sent to clients
- Real-time error notifications via `ctx.error()`
- Graceful error recovery with structured error responses

All operations block until completion or error, providing immediate feedback to clients.