from uipath._cli.middlewares import Middlewares

from ._cli.cli_new import mcp_new_middleware


def register_middleware():
    """This function will be called by the entry point system when uipath-mcp is installed"""
    Middlewares.register("new", mcp_new_middleware)
