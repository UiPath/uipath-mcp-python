import importlib
import inspect
import re
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

# FastMCP for UIPath Python SDK
mcp = FastMCP("UIPath SDK Assistant")

# Map of entity types to service classes with correct import paths
SERVICE_MAP = {
    "buckets": "uipath._services.buckets_service.BucketsService",
    "assets": "uipath._services.assets_service.AssetsService",
    "jobs": "uipath._services.jobs_service.JobsService",
    "processes": "uipath._services.processes_service.ProcessesService",
    "queues": "uipath._services.queues_service.QueuesService",
    "actions": "uipath._services.actions_service.ActionsService",
    "context-grounding": "uipath._services.context_grounding_service.ContextGroundingService",
}


@mcp.tool()
def get_entity_types() -> Dict[str, str]:
    """Returns all available entity types supported by the SDK.

    This tool helps the agent understand what entity types are available
    for querying method information.

    Returns:
        Dictionary mapping entity type names to their descriptions
    """
    result = {}
    for entity_type, service_path in SERVICE_MAP.items():
        # Try to extract descriptions from the class docstring
        try:
            module_path, class_name = service_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            service_class = getattr(module, class_name)
            docstring = inspect.getdoc(service_class) or ""

            # Clean up the docstring (remove extra whitespace and empty lines)
            cleaned_docstring = "\n".join(
                line
                for line in [line.strip() for line in docstring.split("\n")]
                if line
            )

            # Use the entire docstring instead of just the first paragraph
            result[entity_type] = (
                cleaned_docstring or f"{entity_type.capitalize()} related operations"
            )
        except Exception:
            result[entity_type] = f"{entity_type.capitalize()} related operations"

    return result


@mcp.tool()
@mcp.tool()
def get_sdk_methods(entity_type: str) -> Dict[str, Any]:
    """Returns detailed information about all methods available for a specific entity type.

    This function only returns methods defined directly in the service class,
    excluding methods inherited from base classes.

    Args:
        entity_type: The type of entity (e.g., 'buckets', 'assets', 'queues')

    Returns:
        Dictionary containing all methods with their signatures, descriptions, and examples

    Raises:
        ValueError: If the entity type is not found or cannot be imported
    """
    if entity_type not in SERVICE_MAP:
        raise ValueError(
            f"Entity type '{entity_type}' not found. Use get_entity_types() to see available entity types."
        )

    # Import the module dynamically
    module_path, class_name = SERVICE_MAP[entity_type].rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        service_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(
            f"Could not import {class_name} from {module_path}: {str(e)}"
        ) from e

    # Get class docstring for overall description
    class_description = inspect.getdoc(service_class) or ""

    methods = {}

    # Get the methods defined directly in this class (not in parent classes)
    class_methods = {}

    # Method 1: Use __dict__ to get only methods defined in the class itself
    for name, method in service_class.__dict__.items():
        if callable(method) and not name.startswith("_"):
            # This gets methods defined directly as functions in the class
            class_methods[name] = method

    # Method 2: Check each method's __qualname__ to ensure it's defined in this class
    for name, method in inspect.getmembers(service_class, inspect.isfunction):
        if name.startswith("_"):
            continue

        # Check if method is defined in this class (not parent)
        method_class = method.__qualname__.split(".")[0]
        if method_class == class_name:
            class_methods[name] = method

    # Process each method found
    for name, method in class_methods.items():
        # Get signature information
        try:
            sig = inspect.signature(method)
        except ValueError:
            # Skip methods that can't be inspected
            continue

        docstring = inspect.getdoc(method) or ""

        # Extract parameters info
        params = {}
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Try to get type hints
            param_type = "Any"  # Default
            try:
                from typing import get_type_hints

                hints = get_type_hints(method)
                if param_name in hints:
                    param_type = str(hints[param_name])
            except Exception:
                pass

            # Extract parameter description
            param_desc = ""

            # Look for param in Args section
            args_pattern = r"Args:(.*?)(?:\n\n|\n[A-Z]|\Z)"
            args_match = re.search(args_pattern, docstring, re.DOTALL)

            if args_match:
                args_text = args_match.group(1)
                param_pattern = rf"\s+{param_name}\s*(?:\([^)]*\))?:\s*(.*?)(?:\n\s+\w+(?:\s*\(|\s*:)|\Z)"
                param_match = re.search(param_pattern, args_text, re.DOTALL)

                if param_match:
                    param_desc = param_match.group(1).strip()

            # Store parameter info
            params[param_name] = {
                "type": param_type,
                "required": param.default == param.empty,
                "description": param_desc,
                "default": None if param.default == param.empty else str(param.default),
            }

        # Extract return type and description
        return_info = {"type": "None", "description": ""}

        try:
            from typing import get_type_hints

            hints = get_type_hints(method)
            if "return" in hints:
                return_info["type"] = str(hints["return"])
        except Exception:
            pass

        # Look for Returns section
        returns_pattern = r"Returns:(.*?)(?:\n\n|\n[A-Z]|\Z)"
        returns_match = re.search(returns_pattern, docstring, re.DOTALL)

        if returns_match:
            return_info["description"] = returns_match.group(1).strip()

        # Extract examples from docstring
        examples = []
        example_pattern = r"Examples:(.*?)(?:\n\n|\Z)"
        example_match = re.search(example_pattern, docstring, re.DOTALL)

        if example_match:
            example_text = example_match.group(1)
            code_blocks = re.findall(
                r"```(?:python)?\n(.*?)```", example_text, re.DOTALL
            )

            for i, block in enumerate(code_blocks):
                examples.append({"title": f"Example {i + 1}", "code": block.strip()})

        # If no examples found in docstring, generate a simple one based on correct SDK usage
        if not examples:
            param_strings = []
            for param_name, info in params.items():
                param_type = info.get("type", "")
                is_optional = "Optional" in param_type
                if not is_optional or param_name in ["name", "folder_path"]:
                    param_strings.append(f'{param_name}="example_{param_name}"')

            # Check if method is async or not
            is_async = name.endswith("_async") or (
                "async" in inspect.getsource(method).split("def")[0]
                if hasattr(method, "__code__")
                else False
            )

            if is_async:
                example_code = f"""# Example usage of {name}
from uipath import UiPath

# Initialize the SDK client
uipath = UiPath()

# Call the async method
result = await uipath.{entity_type}.{name}({", ".join(param_strings)})
print(f"Operation completed successfully: {{result}}")"""
            else:
                example_code = f"""# Example usage of {name}
from uipath import UiPath

# Initialize the SDK client
uipath = UiPath()

# Call the method
result = uipath.{entity_type}.{name}({", ".join(param_strings)})
print(f"Operation completed successfully: {{result}}")"""

            examples.append({"title": f"Basic {name} example", "code": example_code})

        # Extract exceptions
        exceptions = []
        raises_pattern = r"Raises:(.*?)(?:\n\n|\n[A-Z]|\Z)"
        raises_match = re.search(raises_pattern, docstring, re.DOTALL)

        if raises_match:
            raises_text = raises_match.group(1)
            exception_pattern = r"\s+(\w+(?:\.\w+)*):\s*(.*?)(?:\n\s+\w+:|\Z)"
            exception_matches = re.findall(exception_pattern, raises_text, re.DOTALL)

            for exc_type, desc in exception_matches:
                exceptions.append({"type": exc_type, "description": desc.strip()})

        # Get method description (first paragraph)
        description = docstring.split("\n\n")[0].strip() if docstring else ""

        # Check if there's an async version of this method
        has_async_version = False
        if not name.endswith("_async"):
            has_async_version = hasattr(service_class, f"{name}_async")

        # Store all method info
        methods[name] = {
            "description": description,
            "parameters": params,
            "return": return_info,
            "examples": examples,
            "exceptions": exceptions,
            "is_async": is_async or name.endswith("_async"),
            "has_async_version": has_async_version,
            "async_version": f"{name}_async" if has_async_version else None,
        }

    return {
        "entity_type": entity_type,
        "description": class_description.split("\n\n")[0].strip()
        if class_description
        else "",
        "methods": methods,
        "usage_pattern": f"uipath.{entity_type}.method_name()",
    }


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
