from langchain_core.tools import Tool

def retrieve_from_execution_context(key: str) -> str:
    import os
    if os.getenv(key) is None:
        return 'not found'
    else:
        return os.getenv(key)


retrieve_from_execution_context_tool = Tool.from_function(
    func=retrieve_from_execution_context,
    name="retrieve_from_execution_context",
    description=""" Retrieve an execution context detail

    Args:
        key (str): The key of the element to return

    Returns:
        str: The value of the element in the execution context if found, else 'not found'
    """,
)