"""NetBox MCP tools wrapper with filter validation and error handling."""

import re
from typing import Any

from langchain_core.tools import StructuredTool, Tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Known problematic filter patterns that will fail with MCP
INVALID_FILTER_PATTERNS = [
    r".*__.*__.*",  # Multi-hop filters (e.g., device__site__name)
    r".*__(icontains|contains|startswith|endswith|regex|iregex|in|gt|gte|lt|lte)$",  # Django lookups
    r"^(termination_[ab]|device|site|rack)__\w+",  # Relationship traversals
]


class FilterValidator:
    """Validates NetBox filters before sending to MCP server."""

    @staticmethod
    def validate_filter(filter_dict: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate a filter dictionary for MCP compatibility.

        Args:
            filter_dict: Filter parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        for key, _value in filter_dict.items():
            # Check for multi-hop patterns
            if "__" in key:
                # Check against known invalid patterns
                for pattern in INVALID_FILTER_PATTERNS:
                    if re.match(pattern, key):
                        return False, f"Invalid filter pattern: {key} (contains unsupported lookup or relationship traversal)"

        return True, None

    @staticmethod
    def suggest_alternative(invalid_filter: str) -> str:
        """
        Suggest an alternative approach for an invalid filter.

        Args:
            invalid_filter: The invalid filter key

        Returns:
            Suggestion for how to fix the filter
        """
        if "__" in invalid_filter:
            parts = invalid_filter.split("__")
            if len(parts) == 2:
                if parts[1] in ["icontains", "contains", "startswith"]:
                    return f"Use netbox_search_objects with query parameter instead of {invalid_filter}"
                else:
                    return f"Perform two-step query: 1) Get {parts[0]} by name, 2) Use {parts[0]}_id filter"
            else:
                return "Break into multiple queries, fetching intermediate objects first"

        return "Use direct ID filters or exact name matches"


class NetBoxToolWrapper:
    """Wrapper for NetBox MCP tools with validation and error handling."""

    def __init__(self, mcp_client: MultiServerMCPClient):
        self.mcp_client = mcp_client
        self.validator = FilterValidator()

    async def get_tools(self) -> list[Tool]:
        """Get wrapped NetBox tools with validation."""
        # Get raw MCP tools
        raw_tools = await self.mcp_client.get_tools()

        # Wrap each tool with validation
        wrapped_tools = []
        for tool in raw_tools:
            if "netbox" in tool.name.lower():
                wrapped_tool = self._wrap_tool_with_validation(tool)
                wrapped_tools.append(wrapped_tool)
            else:
                wrapped_tools.append(tool)

        return wrapped_tools

    def _wrap_tool_with_validation(self, tool: Tool) -> Tool:
        """Wrap a tool with filter validation logic."""
        # Get the original function - MCP tools use coroutine attribute for async functions
        original_func = getattr(tool, "coroutine", None) or tool.func

        async def validated_func(*args, **kwargs):
            # Normalize arguments - handle both calling conventions
            # LangChain can call tools with either:
            # 1. A single positional dict: func({"object_type": "...", "filters": {...}})
            # 2. Keyword arguments: func(object_type="...", filters={...})
            if args and len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                # Called with single positional dict - convert to kwargs
                kwargs = args[0]
                args = ()

            # Check if this tool uses filters
            if "filters" in kwargs or "filter" in kwargs:
                filter_param = kwargs.get("filters") or kwargs.get("filter") or {}

                # Validate the filter
                is_valid, error_msg = self.validator.validate_filter(filter_param)

                if not is_valid:
                    # Log the error
                    logger.warning(
                        "Invalid filter detected",
                        filter=filter_param,
                        error=error_msg,
                    )

                    # Get suggestion for fixing
                    suggestion = self.validator.suggest_alternative(list(filter_param.keys())[0])

                    # Raise a descriptive error
                    raise ValueError(
                        f"MCP Filter Error: {error_msg}\n"
                        f"Suggestion: {suggestion}\n"
                        f"Consult the netbox-mcp-filters skill for guidance."
                    )

            # If validation passes, call the original function
            try:
                result = await original_func(*args, **kwargs)
                logger.debug(f"Tool {tool.name} executed successfully", kwargs=kwargs)
                return result
            except Exception as e:
                logger.error(f"Tool {tool.name} failed", error=str(e), kwargs=kwargs)
                raise

        # Create new tool with validation wrapper
        # Use StructuredTool.from_function with coroutine parameter for async functions
        return StructuredTool.from_function(
            coroutine=validated_func,  # Use coroutine parameter for async functions
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )


async def create_netbox_mcp_client(netbox_url: str, netbox_token: str, server_path: str | None = None) -> MultiServerMCPClient:
    """
    Create and connect to NetBox MCP client.

    Args:
        netbox_url: NetBox instance URL
        netbox_token: NetBox API token
        server_path: Optional path to MCP server

    Returns:
        Connected MCP client
    """
    print(f"DEBUG: create_netbox_mcp_client called with server_path={server_path}", flush=True)
    # Configure MCP client for NetBox with stdio transport
    # Try to use installed module first, fall back to running from path
    if server_path:
        # Run from the server path, adding it to PYTHONPATH so module can be imported
        import os
        import sys

        # Add the src directory to PYTHONPATH
        src_path = os.path.join(server_path, "src")

        # netbox-mcp-server requires Python 3.13+, check if we need a different interpreter
        python_cmd = sys.executable
        if sys.version_info < (3, 13):
            # Try to find Python 3.13 via pyenv
            pyenv_python = os.path.expanduser("~/.pyenv/versions/3.13.0/bin/python")
            if os.path.exists(pyenv_python):
                python_cmd = pyenv_python
                print(f"DEBUG: Using Python 3.13 for MCP server: {python_cmd}", flush=True)
            else:
                logger.warning(
                    "netbox-mcp-server requires Python 3.13+, but current version is %s.%s. "
                    "Python 3.13 not found at %s",
                    sys.version_info.major,
                    sys.version_info.minor,
                    pyenv_python,
                )

        mcp_config = {
            "netbox": {
                "transport": "stdio",
                "command": "uv",
                "args": ["--directory", server_path, "run", "netbox-mcp-server"],
                "env": {
                    "NETBOX_URL": netbox_url,
                    "NETBOX_TOKEN": netbox_token,
                    "TRANSPORT": "stdio",  # Override .env file
                }
            }
        }
        print(f"DEBUG: Using MCP server from path: {server_path}", flush=True)
    else:
        # Use installed module (assumes it's in current uv environment)
        mcp_config = {
            "netbox": {
                "transport": "stdio",
                "command": "uv",
                "args": ["run", "netbox-mcp-server"],
                "env": {
                    "NETBOX_URL": netbox_url,
                    "NETBOX_TOKEN": netbox_token,
                    "TRANSPORT": "stdio",  # Override .env file
                }
            }
        }
        print("DEBUG: Using installed netbox-mcp-server module via uv", flush=True)

    print("DEBUG: Creating MultiServerMCPClient with config...", flush=True)
    client = MultiServerMCPClient(mcp_config)
    print("DEBUG: MultiServerMCPClient created", flush=True)

    # Initialize/connect the client
    logger.info("Connecting to NetBox MCP server...", url=netbox_url)
    try:
        # Try to get tools to verify connection works (with timeout)
        import asyncio
        tools = await asyncio.wait_for(client.get_tools(), timeout=30.0)
        logger.info("Successfully connected to NetBox MCP server", url=netbox_url, num_tools=len(tools))
    except asyncio.TimeoutError:
        logger.error("Timeout connecting to NetBox MCP server after 30 seconds")
        raise RuntimeError("Failed to connect to NetBox MCP server: connection timeout")
    except Exception as e:
        logger.error("Failed to connect to NetBox MCP server", error=str(e))
        raise

    return client


class NetBoxQueryHelper:
    """Helper class for common NetBox query patterns."""

    @staticmethod
    def create_two_step_filter(entity_type: str, entity_name: str, target_filter: str) -> list[dict[str, Any]]:
        """
        Create a two-step query plan for relationship filters.

        Args:
            entity_type: Type of entity to lookup first (e.g., "device")
            entity_name: Name of the entity
            target_filter: The filter to use with the entity ID

        Returns:
            List of query steps to execute
        """
        return [
            {
                "tool": "netbox_get_objects",
                "params": {
                    "object_type": f"dcim.{entity_type}",
                    "filters": {"name": entity_name},
                },
                "description": f"Get {entity_type} by name",
            },
            {
                "tool": "netbox_get_objects",
                "params": {
                    "object_type": target_filter.split(".")[0] + "." + target_filter.split(".")[1],
                    "filters": {f"{entity_type}_id": "{{previous_result.id}}"},  # Template for ID from previous step
                },
                "description": f"Get objects filtered by {entity_type} ID",
            },
        ]

    @staticmethod
    def use_search_instead(query_text: str, object_types: list[str] | None = None) -> dict[str, Any]:
        """
        Create a search query instead of filtered query.

        Args:
            query_text: Text to search for
            object_types: Optional list of object types to search

        Returns:
            Search query parameters
        """
        params = {"query": query_text}
        if object_types:
            params["object_types"] = object_types

        return {
            "tool": "netbox_search_objects",
            "params": params,
            "description": f"Search for '{query_text}'",
        }
