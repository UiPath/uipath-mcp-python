from uipath._cli.middlewares import Middlewares

from ._cli.cli_init import mcp_init_middleware
from ._cli.cli_new import mcp_new_middleware
from ._cli.cli_run import mcp_run_middleware


def register_middleware():
    """This function will be called by the entry point system when uipath-mcp is installed"""
    Middlewares.register("init", mcp_init_middleware)
    Middlewares.register("run", mcp_run_middleware)
    Middlewares.register("new", mcp_new_middleware)
