import os
import shutil
from typing import List, Optional, Tuple

import click
from uipath._cli._utils._console import ConsoleLogger
from uipath._cli.middlewares import MiddlewareResult

console = ConsoleLogger()


def clean_directory(directory: str) -> None:
    """Clean up Python files in the specified directory.

    Args:
        directory (str): Path to the directory to clean.

    This function removes all Python files (*.py) from the specified directory.
    It's used to prepare a directory for new MCP server template files.
    """
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)

        if os.path.isfile(file_path) and file_name.endswith(".py"):
            # Delete the file
            os.remove(file_path)


def write_template_file(
    target_directory: str,
    file_path: str,
    file_name: str,
    replace_tuple: Optional[List[Tuple[str, str]]] = None,
) -> None:
    """Write a template file to the target directory with optional placeholder replacements.

    Args:
        target_directory (str): Directory where the file will be created.
        file_path (str): Path to the template file relative to this module.
        file_name (str): Name of the file to create in the target directory.
        replace_tuple (Optional[List[Tuple[str, str]]]): List of (placeholder, value) pairs for template substitution.
            If None, the template file is copied as-is.

    This function copies a template file to the target directory and optionally replaces placeholders
    with specified values. It logs a success message after creating the file.
    """
    template_path = os.path.join(os.path.dirname(__file__), file_path)
    target_path = os.path.join(target_directory, file_name)
    if replace_tuple is not None:
        # replace the template placeholders
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        for target, new_value in replace_tuple:
            template_content = template_content.replace(target, new_value)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(template_content)
    else:
        shutil.copyfile(template_path, target_path)
    console.success(f"Created '{file_name}' file.")


def generate_files(target_directory: str, server_name: str):
    """Generate all necessary files for a new MCP server project.

    Args:
        target_directory (str): Directory where the files will be created.
        server_name (str): Name of the MCP server, used in configuration files.

    This function creates three essential files for an MCP server:
    - server.py: The main server implementation
    - mcp.json: Server configuration file
    - pyproject.toml: Project metadata and dependencies
    """
    write_template_file(
        target_directory, "_templates/server.py.template", "server.py", None
    )
    write_template_file(
        target_directory,
        "_templates/mcp.json.template",
        "mcp.json",
        [("$server_name", server_name)],
    )
    write_template_file(
        target_directory,
        "_templates/pyproject.toml.template",
        "pyproject.toml",
        [("$project_name", server_name)],
    )


def mcp_new_middleware(name: str) -> MiddlewareResult:
    """Create a new MCP server project with template files.

    Args:
        name (str): Name of the MCP server to create.

    Returns:
        MiddlewareResult: Result object indicating success/failure and whether to continue processing.

    This middleware function:
    1. Cleans the current directory of Python files
    2. Generates new template files for the MCP server
    3. Displays helpful instructions for initializing and running the server
    4. Returns a MiddlewareResult indicating whether to continue processing

    If an error occurs during creation, it returns a MiddlewareResult with should_include_stacktrace=True.
    """
    directory = os.getcwd()

    try:
        with console.spinner(
            f"Creating new mcp server '{name}' in current directory ..."
        ):
            clean_directory(directory)
            generate_files(directory, name)
            init_command = """uipath init"""
            run_command = f"""uipath run {name}"""
            console.hint(
                f""" Initialize project: {click.style(init_command, fg="cyan")}"""
            )

            line = click.style("═" * 60, bold=True)

            console.info(line)
            console.info(
                click.style(
                    f"""Start '{name}' as a self-hosted MCP server""",
                    fg="magenta",
                    bold=True,
                )
            )
            console.info(line)

            console.hint(
                f""" 1. Set {click.style("UIPATH_FOLDER_PATH", fg="cyan")} environment variable"""
            )
            console.hint(
                f""" 2. Start the server locally: {click.style(run_command, fg="cyan")}"""
            )
        return MiddlewareResult(should_continue=False)
    except Exception as e:
        console.error(f"Error creating demo agent {str(e)}")
        return MiddlewareResult(
            should_continue=False,
            should_include_stacktrace=True,
        )
