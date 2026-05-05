"""Middleware for recovering from NetBox MCP filter errors."""

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from ..utils.config import QueryMetrics
from ..utils.logging import get_logger

logger = get_logger(__name__)


class FilterErrorRecoveryMiddleware(AgentMiddleware):
    """
    Middleware that catches and recovers from MCP filter errors.

    This middleware intercepts filter errors from the NetBox MCP server and
    provides recovery strategies using two-step queries and search alternatives.
    """

    def __init__(self, metrics: QueryMetrics | None = None):
        """
        Initialize the middleware.

        Args:
            metrics: Optional metrics tracker for recording recovery attempts
        """
        self.logger = logger
        self.metrics = metrics or QueryMetrics()

        # Patterns that indicate filter errors
        self.error_patterns = {
            r"Invalid filter.*__": "multi_hop_filter",
            r"Invalid filter.*__icontains": "django_lookup",
            r"Invalid filter.*__contains": "django_lookup",
            r"Invalid filter.*__startswith": "django_lookup",
            r"Invalid filter.*__in": "django_lookup",
            r"termination_[ab]__device": "relationship_filter",
            r"device__site": "relationship_filter",
            r"interface__device": "relationship_filter",
            r"MCP Filter Error": "mcp_validation_error",
            # NetBox returns 400 when a relational filter receives a display name
            # instead of a slug or numeric *_id (e.g. site=DM-Akron vs site=dm-akron).
            r"400 Client Error: Bad Request": "relational_value_error",
        }

        # Track recovery attempts to avoid infinite loops
        self.recovery_attempts = {}

    def after_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Process state after model execution to detect and recover from errors.

        Args:
            state: Current agent state

        Returns:
            Modified state with recovery instructions, or None
        """
        # Check if there's an error in the state
        error_msg = str(state.get("error", ""))
        if not error_msg:
            # Also check for error in last message
            messages = state.get("messages", [])
            if messages and "error" in messages[-1].content.lower():
                error_msg = messages[-1].content

        if not error_msg:
            return None

        # Detect filter error type
        error_type = self._detect_error_type(error_msg)
        if not error_type:
            return None

        # Extract the problematic filter
        failed_filter = self._extract_filter(error_msg)
        if not failed_filter:
            return None

        # Check if we've already tried to recover this error
        error_key = f"{error_type}:{failed_filter}"
        if error_key in self.recovery_attempts:
            if self.recovery_attempts[error_key] >= 2:
                self.logger.warning(
                    "Max recovery attempts reached",
                    filter=failed_filter,
                    attempts=self.recovery_attempts[error_key],
                )
                return None
            self.recovery_attempts[error_key] += 1
        else:
            self.recovery_attempts[error_key] = 1

        # Log the error and recovery attempt
        self.logger.info(
            "Filter error detected, attempting recovery",
            error_type=error_type,
            filter=failed_filter,
            attempt=self.recovery_attempts[error_key],
        )

        # Track metrics
        if self.metrics:
            self.metrics.filter_errors += 1

        # Generate recovery strategy
        recovery_strategy = self._generate_recovery_strategy(error_type, failed_filter, error_msg)

        if recovery_strategy:
            if self.metrics:
                self.metrics.recovered_errors += 1

            # Return modified state with recovery instructions
            return {
                "recovery_strategy": recovery_strategy,
                "original_error": error_msg,
                "skill_hint": "Load the netbox-mcp-filters skill for detailed guidance",
            }

        return None

    def _detect_error_type(self, error_msg: str) -> str | None:
        """Detect the type of filter error from the error message."""
        for pattern, error_type in self.error_patterns.items():
            if re.search(pattern, error_msg, re.IGNORECASE):
                return error_type
        return None

    def _extract_filter(self, error_msg: str) -> str | None:
        """Extract the problematic filter from the error message."""
        # Try to extract filter pattern from error message
        patterns = [
            r"Invalid filter:\s*([^\s,]+)",
            r"filter['\"]:\s*['\"]([^'\"]+)",
            r"(\w+__\w+(?:__\w+)*)",
            # 400 Bad Request from NetBox: pull the offending querystring,
            # e.g. ".../api/dcim/racks/?name=Comms+closet&site=DM-Akron&..."
            r"\?([^\s'\"]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_msg)
            if match:
                return match.group(1)

        return None

    def _generate_recovery_strategy(
        self, error_type: str, failed_filter: str, error_msg: str
    ) -> dict[str, Any]:
        """
        Generate a recovery strategy based on the error type.

        Args:
            error_type: Type of filter error
            failed_filter: The filter that failed
            error_msg: Full error message

        Returns:
            Recovery strategy dictionary
        """
        strategy = {
            "type": error_type,
            "failed_filter": failed_filter,
            "steps": [],
        }

        if error_type in ["multi_hop_filter", "relationship_filter"]:
            # Generate two-step query strategy
            parts = failed_filter.split("__")
            if len(parts) >= 2:
                strategy["approach"] = "two_step_query"
                strategy["steps"] = [
                    {
                        "description": f"Get {parts[0]} by name or other simple filter",
                        "example": f'netbox_get_objects("dcim.{parts[0]}", {{"name": "<name>"}})',
                    },
                    {
                        "description": f"Use the {parts[0]}_id from step 1 in the final query",
                        "example": f'netbox_get_objects("<target_type>", {{"{parts[0]}_id": <id_from_step1>}})',
                    },
                ]
                strategy["explanation"] = (
                    f"The filter '{failed_filter}' attempts to traverse a relationship, which is not supported. "
                    f"Instead, first get the {parts[0]} object, then use its ID."
                )

        elif error_type == "django_lookup":
            # Generate search alternative
            if "__icontains" in failed_filter or "__contains" in failed_filter:
                field = failed_filter.split("__")[0]
                strategy["approach"] = "use_search"
                strategy["steps"] = [
                    {
                        "description": f"Use search instead of {failed_filter}",
                        "example": 'netbox_search_objects(query="<search_term>")',
                    }
                ]
                strategy["explanation"] = (
                    "Django lookup suffixes like '__icontains' are not supported. "
                    "Use the search tool for pattern matching instead."
                )
            else:
                strategy["approach"] = "exact_match"
                strategy["steps"] = [
                    {
                        "description": f"Use exact match instead of {failed_filter}",
                        "example": f'{{{field}: "<exact_value>"}}',
                    }
                ]
                strategy["explanation"] = (
                    f"Only exact matches are supported for field '{field}'. "
                    f"Remove the lookup suffix and use exact values."
                )

        elif error_type == "relational_value_error":
            # NetBox returned 400 — most often a relational filter received a display
            # name where it needs a slug or numeric ID. Steer toward the two-step pattern.
            strategy["approach"] = "two_step_query"
            strategy["steps"] = [
                {
                    "description": "Look up the related object by name to get its ID",
                    "example": "netbox_get_objects('dcim.site', filters={'name': '<Display Name>'}, fields=['id', 'slug'])",
                },
                {
                    "description": "Re-issue the original query using the numeric *_id",
                    "example": "netbox_get_objects('<target_type>', filters={'<related>_id': <id>, ...}, fields=[...])",
                },
            ]
            strategy["explanation"] = (
                "NetBox rejected the request (HTTP 400). Relational filters (site, device, "
                "rack, tenant, region, provider, cluster, ...) accept a numeric *_id or a "
                "lowercase slug — never a display name. Run a two-step query: resolve the "
                "name to an ID first, then filter by that ID."
            )

        elif error_type == "mcp_validation_error":
            # Generic MCP validation error
            strategy["approach"] = "simplify_filter"
            strategy["steps"] = [
                {
                    "description": "Simplify the filter to use only direct fields",
                    "example": "Use only simple filters like {'name': 'value'} or {'id': 123}",
                }
            ]
            strategy["explanation"] = (
                "The MCP server rejected the filter. Use only simple, direct field filters."
            )

        # Add general recovery tips
        strategy["tips"] = [
            "Consult the netbox-mcp-filters skill for comprehensive filter patterns",
            "Use netbox_search_objects for pattern matching",
            "Break complex queries into multiple simple steps",
            "Always validate filters before execution",
        ]

        return strategy

    def reset_recovery_attempts(self) -> None:
        """Reset the recovery attempt counter."""
        self.recovery_attempts.clear()
        self.logger.debug("Recovery attempts reset")


class MetricsMiddleware(AgentMiddleware):
    """Middleware for tracking query metrics."""

    def __init__(self, metrics: QueryMetrics):
        """Initialize with metrics tracker."""
        self.metrics = metrics
        self.logger = get_logger(__name__)
        self.query_start_time = None

    def before_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Track query start."""
        import time

        self.query_start_time = time.time()
        self.metrics.total_queries += 1
        return None

    def after_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Track query completion."""
        import time

        if self.query_start_time:
            duration = time.time() - self.query_start_time
            self.metrics.response_times.append(duration)

            # Check if query succeeded
            if not state.get("error"):
                self.metrics.successful_queries += 1

            self.logger.info(
                "Query completed",
                duration=duration,
                success=not state.get("error"),
                total_queries=self.metrics.total_queries,
            )

        return None
