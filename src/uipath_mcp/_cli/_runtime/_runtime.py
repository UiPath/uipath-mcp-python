import asyncio
import logging
import os
import sys
import tempfile
import uuid
from typing import Any, Dict, Optional

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from opentelemetry import trace
from pysignalr.client import CompletionMessage, SignalRClient
from uipath import UiPath
from uipath._cli._runtime._contracts import (
    UiPathBaseRuntime,
    UiPathErrorCategory,
    UiPathRuntimeResult,
)
from uipath.tracing import wait_for_tracers

from .._utils._config import McpServer
from ._context import UiPathMcpRuntimeContext, UiPathServerType
from ._exception import UiPathMcpRuntimeError
from