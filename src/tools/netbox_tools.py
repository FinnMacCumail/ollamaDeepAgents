"""NetBox MCP tools wrapper with filter validation and error handling."""

import re
from typing import Any

from langchain_core.tools import StructuredTool, Tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Lookup suffixes the MCP server's validate_filters() permits.
# Source of truth: netbox-mcp-server/src/netbox_mcp_server/server.py:135-153
# (the VALID_SUFFIXES frozenset). Keep this in sync with the upstream whitelist.
# A previous version of this file maintained a blacklist that incorrectly
# rejected `__in`, `__regex`, `__gt`, `__gte`, `__lt`, `__lte`, `__iregex` —
# all of which ARE valid per the MCP server. Trace 019e63c0 surfaced the
# inconsistency: the skill content (correct) and this validator (wrong) gave
# the model contradictory guidance, costing a recovery cycle per attempt.
VALID_SUFFIXES: frozenset[str] = frozenset({
    "n",
    "ic", "nic", "isw", "nisw", "iew", "niew", "ie", "nie",
    "empty",
    "regex", "iregex",
    "lt", "lte", "gt", "gte",
    "in",
})


class FilterValidator:
    """Validates NetBox filters before sending to MCP server.

    Mirrors the MCP server's own validate_filters() at server.py:117 — rejects
    multi-hop relationship traversals (any chain of `__field__field`) and
    double-underscore suffixes not on the VALID_SUFFIXES whitelist.
    """

    @staticmethod
    def validate_filter(filter_dict: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate a filter dictionary for MCP compatibility.

        Args:
            filter_dict: Filter parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        for key in filter_dict:
            if "__" not in key:
                continue  # bare key (e.g. site_id, name, status) — always allowed

            parts = key.split("__")
            if len(parts) != 2:
                return (
                    False,
                    f"Invalid filter pattern: {key} (multi-hop relationship "
                    f"traversal not supported — use a two-step query instead)",
                )

            suffix = parts[1]
            if suffix not in VALID_SUFFIXES:
                return (
                    False,
                    f"Invalid filter pattern: {key} (suffix '__{suffix}' is not "
                    f"on the MCP server's whitelist; allowed: "
                    f"{', '.join(sorted(VALID_SUFFIXES))})",
                )

        return True, None

    # Translation from Django ORM lookup names to MCP-server-accepted suffixes.
    # The MCP server accepts case-insensitive short forms (`ic`/`isw`/`iew`/`ie`)
    # but NOT the Django spellings (`icontains`/`startswith`/etc.). Translate
    # directly so the model gets a drop-in replacement, not a "use search" detour.
    _DJANGO_TO_MCP = {
        "icontains": "ic",
        "contains": "ic",       # downgrade to case-insensitive
        "istartswith": "isw",
        "startswith": "isw",
        "iendswith": "iew",
        "endswith": "iew",
        "iexact": "ie",
        "exact": "ie",
    }

    @staticmethod
    def suggest_alternative(invalid_filter: str) -> str:
        """Suggest an alternative for a filter rejected by validate_filter.

        With the allow-list-based validator, only two rejection paths reach
        here: multi-hop traversals (>2 `__`-separated parts) and unknown
        suffixes (not on VALID_SUFFIXES). Most unknown suffixes that the
        model is likely to try are Django ORM lookup names with short MCP
        equivalents — translate those directly.
        """
        if "__" not in invalid_filter:
            return "Use a direct field filter (e.g. {'site_id': 5} or {'name': 'foo'})."

        parts = invalid_filter.split("__")
        if len(parts) > 2:
            return (
                f"'{invalid_filter}' is a multi-hop relationship traversal, which the "
                f"MCP server does not support. Use a two-step query: first fetch the "
                f"intermediate object by name, then filter the target type by its id "
                f"(e.g. '{parts[0]}_id')."
            )

        field, suffix = parts[0], parts[1]

        if suffix in FilterValidator._DJANGO_TO_MCP:
            correct = FilterValidator._DJANGO_TO_MCP[suffix]
            return (
                f"The Django-form suffix '__{suffix}' is not on the MCP server's "
                f"whitelist. Use '__{correct}' instead: "
                f"filters={{'{field}__{correct}': '<value>'}}"
            )

        return (
            f"The suffix '__{suffix}' is not supported. Valid suffixes are: "
            f"{', '.join(sorted(VALID_SUFFIXES))}. For relationship filters, "
            f"drop the suffix and use the bare key with a single value or a list."
        )


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

                # Find the first invalid key (validate_filter returns on the first failure)
                is_valid, error_msg = self.validator.validate_filter(filter_param)

                if not is_valid:
                    # Identify which key failed so the suggestion is targeted at it
                    invalid_key = next(
                        (k for k in filter_param if not self.validator.validate_filter({k: filter_param[k]})[0]),
                        next(iter(filter_param), ""),
                    )
                    suggestion = self.validator.suggest_alternative(invalid_key)

                    logger.warning(
                        "Invalid filter detected — returning structured error to model",
                        tool=tool.name,
                        filter=filter_param,
                        error=error_msg,
                    )

                    # Return a structured error STRING instead of raising. langgraph
                    # treats this as a successful tool result and threads it back into
                    # the conversation as a ToolMessage, so the model sees the error
                    # on its next turn and can retry with the suggested correction.
                    # Raising here instead would crash the entire agent run.
                    return (
                        f"TOOL_VALIDATION_ERROR: {error_msg}\n"
                        f"Suggestion: {suggestion}\n"
                        f"Consult the netbox-mcp-filters skill for guidance. "
                        f"Reissue this tool call with the corrected filter."
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
