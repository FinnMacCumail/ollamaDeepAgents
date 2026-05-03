"""NetBox DeepAgent implementation with Ollama and MCP integration."""

import asyncio
import time
from collections.abc import AsyncGenerator

from deepagents import create_deep_agent

from ..middleware.filter_recovery import FilterErrorRecoveryMiddleware, MetricsMiddleware
from ..middleware.metrics import QueryMetricsMiddleware, TokenOptimizationMiddleware
from ..tools.netbox_tools import NetBoxToolWrapper, create_netbox_mcp_client
from ..utils.config import NetBoxConfig, QueryMetrics, load_config
from ..utils.logging import get_logger
from .ollama_config import create_ollama_model

logger = get_logger(__name__)

# System prompt for the NetBox agent
NETBOX_SYSTEM_PROMPT = """You are a NetBox infrastructure query assistant powered by DeepAgents.

Your role is to help users query and understand their NetBox infrastructure data efficiently.

CRITICAL CONSTRAINTS for NetBox MCP filters:
- NEVER use multi-hop filters with double underscores for relationships (e.g., device__site_id)
- NEVER use Django ORM lookups (e.g., __icontains, __in, __startswith)
- ALWAYS use two-step queries when filtering by related objects
- ALWAYS check the netbox-mcp-filters skill for filter guidance

When encountering filter errors:
1. Identify the problematic filter pattern
2. Break the query into multiple steps:
   - First: Get the parent/related object by name or ID
   - Second: Use the object's ID in a simple filter
3. Use netbox_search_objects for pattern matching instead of complex filters

Query Patterns:
- Direct ID filters always work: {"device_id": 123}
- Exact name matches work: {"name": "exact-name"}
- For partial matches, use search: netbox_search_objects(query="pattern")
- For relationships, use two-step queries

Remember to:
- Provide clear, concise responses
- Show relevant data fields
- Explain any workarounds used
- Suggest optimizations when applicable
"""


class NetBoxDeepAgent:
    """
    Main NetBox agent with DeepAgents, Ollama, and MCP integration.

    This agent handles NetBox infrastructure queries with automatic filter
    error recovery and performance optimization.
    """

    def __init__(
        self,
        netbox_config: NetBoxConfig | None = None,
        model_name: str | None = None,
        skills_path: str = "src/skills",
        enable_metrics: bool = True,
    ):
        """
        Initialize the NetBox DeepAgent.

        Args:
            netbox_config: NetBox configuration (loads from env if not provided)
            model_name: Ollama model name to use
            skills_path: Path to skills directory
            enable_metrics: Whether to enable metrics tracking
        """
        self.netbox_config = netbox_config
        self.model_name = model_name
        self.skills_path = skills_path
        self.enable_metrics = enable_metrics
        self.metrics = QueryMetrics() if enable_metrics else None
        self.agent = None
        self.mcp_client = None
        self.tool_wrapper = None

    async def initialize(self) -> None:
        """Initialize the agent and all components."""
        logger.info("Initializing NetBox DeepAgent")
        print("DEBUG: Starting agent initialization...", flush=True)

        # Load configuration if not provided
        if not self.netbox_config:
            print("DEBUG: Loading config...", flush=True)
            ollama_config, netbox_config = load_config()
            self.netbox_config = netbox_config
            if not self.model_name:
                self.model_name = ollama_config.model

        # Create MCP client
        print("DEBUG: Creating MCP client...", flush=True)
        self.mcp_client = await create_netbox_mcp_client(
            self.netbox_config.url,
            self.netbox_config.token,
            self.netbox_config.mcp_server_path,
        )
        print("DEBUG: MCP client created successfully!", flush=True)

        # Create tool wrapper for validation
        print("DEBUG: Creating tool wrapper...", flush=True)
        self.tool_wrapper = NetBoxToolWrapper(self.mcp_client)

        # Get wrapped tools with validation
        print("DEBUG: Getting wrapped tools...", flush=True)
        tools = await self.tool_wrapper.get_tools()
        print(f"DEBUG: Got {len(tools)} tools", flush=True)

        # Create Ollama model
        print("DEBUG: Creating Ollama model...", flush=True)
        model = create_ollama_model(self.model_name)
        print("DEBUG: Ollama model created", flush=True)

        # Build middleware stack
        middleware = []

        # Add filter recovery middleware (critical - goes first)
        middleware.append(FilterErrorRecoveryMiddleware(metrics=self.metrics))

        # Add metrics tracking if enabled
        if self.enable_metrics:
            middleware.append(MetricsMiddleware(self.metrics))
            middleware.append(QueryMetricsMiddleware())

        # Add token optimization
        middleware.append(TokenOptimizationMiddleware(max_tokens_per_message=1000))

        # Create the DeepAgent
        # Note: SummarizationMiddleware is added automatically by DeepAgents
        print("DEBUG: Creating DeepAgent...", flush=True)
        self.agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=NETBOX_SYSTEM_PROMPT,
            middleware=middleware,
            skills=self.skills_path,  # Load skills from directory
        )
        print("DEBUG: DeepAgent created successfully!", flush=True)

        logger.info(
            "NetBox DeepAgent initialized",
            model=self.model_name,
            netbox_url=self.netbox_config.url,
            skills_path=self.skills_path,
        )
        print("DEBUG: Agent fully initialized!", flush=True)

    async def query(self, user_query: str) -> AsyncGenerator[str, None]:
        """
        Execute a query and stream the response.

        Args:
            user_query: Natural language query from user

        Yields:
            Response chunks as they're generated
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        logger.info("Processing query", query=user_query[:100])
        start_time = time.time()

        try:
            # Stream the agent response
            async for chunk in self.agent.astream(
                {"messages": [{"role": "user", "content": user_query}]}, stream_mode="values"
            ):
                if "messages" in chunk and chunk["messages"]:
                    last_msg = chunk["messages"][-1]
                    if hasattr(last_msg, "content"):
                        yield last_msg.content

            # Track successful query
            if self.metrics:
                self.metrics.successful_queries += 1

        except Exception as e:
            logger.error("Query failed", error=str(e), query=user_query[:100])

            # Check if it's a filter error
            if "Invalid filter" in str(e) or "MCP Filter Error" in str(e):
                if self.metrics:
                    self.metrics.filter_errors += 1

                # Yield error message with recovery suggestion
                yield (
                    f"Error: {str(e)}\n\n"
                    f"This appears to be a filter constraint issue. "
                    f"I'll try to rephrase the query using supported patterns.\n"
                    f"Please consult the netbox-mcp-filters skill for guidance."
                )

            else:
                yield f"Error processing query: {str(e)}"

            raise

        finally:
            # Track metrics
            if self.metrics:
                self.metrics.total_queries += 1
                self.metrics.response_times.append(time.time() - start_time)

    async def query_sync(self, user_query: str) -> str:
        """
        Execute a query synchronously (waits for full response).

        Args:
            user_query: Natural language query from user

        Returns:
            Complete response as a single string
        """
        response_parts = []
        async for chunk in self.query(user_query):
            response_parts.append(chunk)
        return "".join(response_parts)

    async def batch_query(self, queries: list[str]) -> dict[str, str]:
        """
        Execute multiple queries in sequence.

        Args:
            queries: List of queries to execute

        Returns:
            Dictionary mapping queries to responses
        """
        results = {}
        for query in queries:
            try:
                response = await self.query_sync(query)
                results[query] = response
            except Exception as e:
                results[query] = f"Error: {str(e)}"
        return results

    def get_metrics_report(self) -> str:
        """Get a formatted metrics report."""
        if not self.metrics:
            return "Metrics tracking is disabled"
        return self.metrics.report()

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.mcp_client:
            # MCP client cleanup - check if it has cleanup methods
            if hasattr(self.mcp_client, "aclose"):
                await self.mcp_client.aclose()
            elif hasattr(self.mcp_client, "close"):
                if asyncio.iscoroutinefunction(self.mcp_client.close):
                    await self.mcp_client.close()
                else:
                    self.mcp_client.close()
            logger.info("Cleaned up MCP client resources")


async def create_netbox_agent(
    netbox_config: NetBoxConfig | None = None,
    model_name: str | None = None,
    skills_path: str = "src/skills",
    enable_metrics: bool = True,
) -> NetBoxDeepAgent:
    """
    Create and initialize a NetBox DeepAgent.

    Args:
        netbox_config: NetBox configuration
        model_name: Ollama model to use
        skills_path: Path to skills directory
        enable_metrics: Whether to enable metrics

    Returns:
        Initialized NetBoxDeepAgent
    """
    agent = NetBoxDeepAgent(
        netbox_config=netbox_config,
        model_name=model_name,
        skills_path=skills_path,
        enable_metrics=enable_metrics,
    )
    await agent.initialize()
    return agent


async def query_netbox(
    agent: NetBoxDeepAgent, query: str, metrics: QueryMetrics | None = None
) -> AsyncGenerator[str, None]:
    """
    Convenience function to query NetBox with metrics tracking.

    Args:
        agent: Initialized NetBox agent
        query: User query
        metrics: Optional metrics tracker

    Yields:
        Response chunks
    """
    if metrics:
        metrics.total_queries += 1
        start_time = time.time()

    try:
        async for chunk in agent.query(query):
            yield chunk

        if metrics:
            metrics.successful_queries += 1

    except Exception as e:
        if metrics and "Invalid filter" in str(e):
            metrics.filter_errors += 1
        raise

    finally:
        if metrics:
            metrics.response_times.append(time.time() - start_time)
