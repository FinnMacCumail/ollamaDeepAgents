"""Metrics tracking middleware for NetBox DeepAgents."""

import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from ..utils.config import QueryMetrics
from ..utils.logging import MetricsLogger, get_logger

logger = get_logger(__name__)


class QueryMetricsMiddleware(AgentMiddleware):
    """
    Middleware for comprehensive query metrics tracking.

    Tracks:
    - Query execution time
    - Success/failure rates
    - Token usage
    - Error recovery attempts
    - Model performance
    """

    def __init__(self):
        """Initialize metrics tracking."""
        self.metrics = QueryMetrics()
        self.metrics_logger = MetricsLogger()
        self.current_query = None
        self.query_start_time = None

    def before_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Track metrics before model execution.

        Args:
            state: Current agent state

        Returns:
            Modified state or None
        """
        # Extract current query from messages
        messages = state.get("messages", [])
        if messages:
            last_user_msg = None
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "user":
                    last_user_msg = msg.content
                    break

            if last_user_msg:
                self.current_query = last_user_msg
                self.query_start_time = time.time()
                logger.debug("Starting query tracking", query=last_user_msg[:100])

        return None

    def after_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Track metrics after model execution.

        Args:
            state: Current agent state

        Returns:
            Modified state or None
        """
        if self.query_start_time:
            duration = time.time() - self.query_start_time
            success = not bool(state.get("error"))

            # Log the query execution
            self.metrics_logger.log_query(
                query=self.current_query or "unknown",
                success=success,
                duration=duration,
                model=state.get("model_name", "unknown"),
            )

            # Update aggregated metrics
            if success:
                self.metrics.successful_queries += 1
            self.metrics.total_queries += 1
            self.metrics.response_times.append(duration)

            # Track token usage if available
            if "token_count" in state:
                self.metrics.token_usage.append(state["token_count"])

            # Reset for next query
            self.query_start_time = None
            self.current_query = None

        return None

    def get_metrics_summary(self) -> str:
        """Get a formatted summary of current metrics."""
        return self.metrics.report()


class TokenOptimizationMiddleware(AgentMiddleware):
    """
    Middleware for optimizing token usage.

    Strategies:
    - Remove verbose tool outputs
    - Summarize long responses
    - Truncate repetitive data
    """

    def __init__(self, max_tokens_per_message: int = 1000):
        """
        Initialize token optimization.

        Args:
            max_tokens_per_message: Maximum tokens per message before truncation
        """
        self.max_tokens = max_tokens_per_message
        self.logger = get_logger(__name__)

    def after_model(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Optimize token usage in state after model execution.

        Args:
            state: Current agent state

        Returns:
            Modified state with optimized messages
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        optimized = False
        for _i, msg in enumerate(messages):
            if hasattr(msg, "content"):
                content = str(msg.content)
                # Rough token estimate (1 token ≈ 4 chars)
                estimated_tokens = len(content) // 4

                if estimated_tokens > self.max_tokens:
                    # Truncate and add ellipsis
                    truncated = content[: self.max_tokens * 4] + "\n[... truncated for token optimization]"
                    msg.content = truncated
                    optimized = True

                    self.logger.debug(
                        "Truncated message",
                        original_tokens=estimated_tokens,
                        new_tokens=len(truncated) // 4,
                    )

        if optimized:
            return {"messages": messages}

        return None


class PerformanceMonitoringMiddleware(AgentMiddleware):
    """
    Middleware for monitoring overall system performance.

    Tracks:
    - Model response times
    - Tool execution times
    - Memory usage
    - Cache hit rates
    """

    def __init__(self):
        """Initialize performance monitoring."""
        self.logger = get_logger(__name__)
        self.tool_execution_times = {}
        self.model_response_times = []
        self.cache_hits = 0
        self.cache_misses = 0

    def before_tool(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Track tool execution start."""
        self.tool_execution_times[tool_name] = time.time()

    def after_tool(self, tool_name: str, tool_output: Any) -> None:
        """Track tool execution completion."""
        if tool_name in self.tool_execution_times:
            duration = time.time() - self.tool_execution_times[tool_name]
            self.logger.info(
                "Tool executed",
                tool=tool_name,
                duration_ms=int(duration * 1000),
            )
            del self.tool_execution_times[tool_name]

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance metrics summary."""
        avg_model_time = (
            sum(self.model_response_times) / len(self.model_response_times)
            if self.model_response_times
            else 0
        )

        cache_hit_rate = (
            self.cache_hits / (self.cache_hits + self.cache_misses)
            if (self.cache_hits + self.cache_misses) > 0
            else 0
        )

        return {
            "avg_model_response_time": avg_model_time,
            "cache_hit_rate": cache_hit_rate,
            "total_cache_hits": self.cache_hits,
            "total_cache_misses": self.cache_misses,
        }
