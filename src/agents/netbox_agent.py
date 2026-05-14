"""NetBox DeepAgent implementation with Ollama and MCP integration."""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import InMemorySaver

# Project root, computed from this file's location so skills resolve
# regardless of the process's cwd at runtime.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

from ..middleware.filter_recovery import FilterErrorRecoveryMiddleware, MetricsMiddleware
from ..middleware.metrics import QueryMetricsMiddleware, TokenOptimizationMiddleware
from ..tools.netbox_tools import NetBoxToolWrapper, create_netbox_mcp_client
from ..utils.config import NetBoxConfig, QueryMetrics, load_config
from ..utils.logging import get_logger
from .ollama_config import create_ollama_model
from .llamacpp_config import create_llamacpp_model

logger = get_logger(__name__)

# System prompt for the NetBox agent
NETBOX_SYSTEM_PROMPT = """You are a NetBox infrastructure assistant with semantic understanding of network relationships.

## CRITICAL OPTIMIZATION RULES:
1. ALWAYS use the 'fields' parameter to minimize token usage (90% reduction possible)
2. NEVER request all fields unless explicitly asked for complete objects
3. Start with 'brief=true' for overview queries, then drill down with specific fields
4. Use 'netbox_search_objects' for global queries when object type is unknown
5. Use 'netbox_get_objects' when you know the specific object type

## COMMON FIELD PATTERNS:
- Devices: fields=['id', 'name', 'status', 'device_type', 'site', 'primary_ip4']
- IP Addresses: fields=['id', 'address', 'status', 'dns_name', 'description', 'vrf']
- Sites: fields=['id', 'name', 'status', 'region', 'description', 'facility']
- Interfaces: fields=['id', 'name', 'type', 'enabled', 'device']
- VLANs: fields=['id', 'vid', 'name', 'status', 'site', 'description']
- Racks: fields=['id', 'name', 'site', 'status', 'u_height', 'facility_id']
- Circuits: fields=['id', 'cid', 'provider', 'type', 'status', 'description']
- Virtual Machines: fields=['id', 'name', 'status', 'cluster', 'vcpus', 'memory']

## QUERY OPTIMIZATION WORKFLOW:
1. Analyze user question to determine required data
2. Select minimal field set that answers the question
3. Use pagination (limit/offset) for large datasets
4. Leverage ordering to get most relevant results first
5. For counting: use fields=['id'] only

## SEMANTIC INFRASTRUCTURE UNDERSTANDING:
- Understand NetBox object relationships: Device → Site → Region
- Interface → Device, IP Address → Interface → Device
- VLAN → Site, Circuit → Provider
- Use two-step queries for cross-relationship filtering
- Remember: Multi-hop filters like 'device__site_id' are NOT supported

## RELATIONAL FILTER VALUES (CRITICAL — READ TWICE):
When filtering by a related object (site, device, rack, tenant, region, provider, cluster, etc.),
the value MUST be either a numeric ID or a lowercase slug — NEVER a display name.

YOU MUST NEVER INVENT, GUESS, OR ASSUME A NUMERIC ID.
- IDs you have not seen returned by a previous tool call DO NOT EXIST to you.
- Guessing an ID like `site_id: 5` without looking it up is a CRITICAL ERROR — it may
  syntactically succeed but return data for a completely different object (silent wrong answer).
- The only IDs you may use in a filter are IDs that appeared in a prior tool result in this
  conversation, or that the user gave you explicitly.

MANDATORY two-step pattern (whenever the user gives you a display name, not an ID):
  Step 1 — REQUIRED FIRST TOOL CALL: resolve the name to an ID
    netbox_get_objects('dcim.site', filters={'name': 'DM-Akron'}, fields=['id', 'slug'])
    → read the returned id (e.g. 7)
  Step 2 — only after Step 1 returns: use that id
    netbox_get_objects('dcim.rack', filters={'site_id': 7, 'name': 'Comms closet'}, fields=[...])

If a name lookup in Step 1 returns zero results, STOP and tell the user the name was not found.
Do NOT proceed to Step 2 with a guessed id.

WRONG: filters={'site': 'DM-Akron'}              # display name → 400 error
WRONG: filters={'site_id': 5}  # without first looking up DM-Akron's id
RIGHT: filters={'site_id': <id returned by Step 1>}
RIGHT: filters={'site': 'dm-akron'}              # lowercase slug — only if you already know the slug

## FILTER CONSTRAINTS:
- NEVER use multi-hop filters with double underscores (e.g., device__site_id)
- NEVER use Django ORM lookups (e.g., __icontains, __in, __startswith)
- ALWAYS check the netbox-mcp-filters skill for filter guidance
- Direct ID filters always work: {"device_id": 123}
- Exact name matches work: {"name": "exact-name"}
- For partial matches, use netbox_search_objects(query="pattern")

When encountering filter errors:
1. Identify the problematic filter pattern
2. Break the query into multiple steps:
   - First: Get the parent/related object by name or ID
   - Second: Use the object's ID in a simple filter
3. Use netbox_search_objects for pattern matching instead of complex filters

## OUTPUT FORMATTING:
- Present results as concise markdown tables
- Highlight key information relevant to user's question
- Include summary statistics when appropriate
- For large result sets, show sample + summary (e.g., 'Showing 10 of 247 total')
- Always mention if results are paginated and how to get more

Your goal: Provide accurate, efficient answers using minimal tokens while maintaining clarity.
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
        backend: str | None = None,
    ):
        """
        Initialize the NetBox DeepAgent.

        Args:
            netbox_config: NetBox configuration (loads from env if not provided)
            model_name: Model name to use (Ollama or GGUF filename)
            skills_path: Path to skills directory
            enable_metrics: Whether to enable metrics tracking
            backend: LLM backend to use ("ollama" or "llamacpp", defaults to env var or "ollama")
        """
        import os

        self.netbox_config = netbox_config
        self.model_name = model_name
        self.skills_path = skills_path
        self.enable_metrics = enable_metrics
        self.backend = backend or os.getenv("LLM_BACKEND", "ollama")
        self.metrics = QueryMetrics() if enable_metrics else None
        self.agent = None
        self.mcp_client = None
        self.tool_wrapper = None
        # Conversation memory: one checkpointer for the agent, one rolling thread_id.
        # Each query in this thread sees prior turns; new_conversation() rotates the id.
        self.checkpointer = InMemorySaver()
        self.thread_id = uuid.uuid4().hex

    @staticmethod
    def _capture_skill_warnings():
        """Attach a list-handler to the deepagents skills logger to catch
        otherwise-silent warnings (e.g. SKILL.md missing 'name')."""
        import logging

        sk_logger = logging.getLogger("deepagents.middleware.skills")

        class _ListHandler(logging.Handler):
            def __init__(self):
                super().__init__(level=logging.WARNING)
                self.records: list[logging.LogRecord] = []

            def emit(self, record: logging.LogRecord) -> None:
                self.records.append(record)

            def detach(self) -> None:
                sk_logger.removeHandler(self)

        h = _ListHandler()
        sk_logger.addHandler(h)
        # Ensure WARNING propagates even if the root level is higher.
        if sk_logger.level == 0 or sk_logger.level > logging.WARNING:
            sk_logger.setLevel(logging.WARNING)
        return h

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

        # Create LLM model based on backend
        print(f"DEBUG: Creating {self.backend} model...", flush=True)
        if self.backend == "llamacpp":
            model = create_llamacpp_model(self.model_name)
            print(f"DEBUG: llama.cpp model created: {self.model_name}", flush=True)
        else:
            model = create_ollama_model(self.model_name)
            print(f"DEBUG: Ollama model created: {self.model_name}", flush=True)

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
        # Capture skill-loader warnings so misconfigured SKILL.md files (missing
        # required 'name'/'description', bad YAML, etc.) don't get silently skipped.
        skill_warnings = self._capture_skill_warnings()
        # SkillsMiddleware needs a backend that can read skill files from disk.
        # create_deep_agent defaults to StateBackend (in-memory, expects skills via
        # invoke(files={...})), which silently loads zero skills for our use case.
        # FilesystemBackend rooted at the project gives us disk-loaded skills with
        # virtual_mode=True providing path-based guardrails.
        skills_backend = FilesystemBackend(
            root_dir=str(PROJECT_ROOT), virtual_mode=True
        )

        self.agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=NETBOX_SYSTEM_PROMPT,
            middleware=middleware,
            # DeepAgents expects skills as list[str]; a bare string iterates char-by-char
            # and silently loads zero skills.
            skills=[self.skills_path],
            backend=skills_backend,
            checkpointer=self.checkpointer,
        )
        for w in skill_warnings.records:
            logger.warning("Skill loader warning", message=w.getMessage())
            print(f"WARNING: skill loader: {w.getMessage()}", flush=True)
        skill_warnings.detach()
        print("DEBUG: DeepAgent created successfully!", flush=True)

        logger.info(
            "NetBox DeepAgent initialized",
            backend=self.backend,
            model=self.model_name,
            netbox_url=self.netbox_config.url,
            skills_path=self.skills_path,
        )
        print("DEBUG: Agent fully initialized!", flush=True)

    async def query(
        self, user_query: str, thread_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Execute a query and stream the response.

        Args:
            user_query: Natural language query from user
            thread_id: Override the conversation thread (defaults to self.thread_id,
                which preserves history across calls until new_conversation() is called)

        Yields:
            Response chunks as they're generated
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        logger.info("Processing query", query=user_query[:100])
        start_time = time.time()

        config = {"configurable": {"thread_id": thread_id or self.thread_id}}

        try:
            # Stream the agent response
            async for chunk in self.agent.astream(
                {"messages": [{"role": "user", "content": user_query}]},
                config=config,
                stream_mode="values",
            ):
                if "messages" in chunk and chunk["messages"]:
                    last_msg = chunk["messages"][-1]

                    # Only yield final AI responses, filter out:
                    # - HumanMessage (user query echoes)
                    # - ToolMessage (raw JSON from NetBox MCP)
                    # - AIMessage with tool_calls but no content
                    # - Empty messages
                    if (hasattr(last_msg, "type") and
                        last_msg.type == "ai" and
                        hasattr(last_msg, "content") and
                        last_msg.content and
                        not getattr(last_msg, "tool_calls", None)):
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

    async def query_sync(self, user_query: str, thread_id: str | None = None) -> str:
        """
        Execute a query synchronously (waits for full response).

        Args:
            user_query: Natural language query from user
            thread_id: Optional override for the conversation thread

        Returns:
            Complete response as a single string
        """
        response_parts = []
        async for chunk in self.query(user_query, thread_id=thread_id):
            response_parts.append(chunk)
        return "".join(response_parts)

    def new_conversation(self) -> str:
        """Start a fresh conversation thread, discarding prior history.

        Returns the new thread_id.
        """
        self.thread_id = uuid.uuid4().hex
        logger.info("Started new conversation", thread_id=self.thread_id)
        return self.thread_id

    async def batch_query(self, queries: list[str]) -> dict[str, str]:
        """
        Execute multiple queries in sequence, each in its own thread so
        unrelated queries do not share conversation context.

        Args:
            queries: List of queries to execute

        Returns:
            Dictionary mapping queries to responses
        """
        results = {}
        for query in queries:
            try:
                # Independent thread per batch query
                response = await self.query_sync(query, thread_id=uuid.uuid4().hex)
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
    backend: str | None = None,
) -> NetBoxDeepAgent:
    """
    Create and initialize a NetBox DeepAgent.

    Args:
        netbox_config: NetBox configuration
        model_name: Model name to use (Ollama or GGUF filename)
        skills_path: Path to skills directory
        enable_metrics: Whether to enable metrics
        backend: LLM backend to use ("ollama" or "llamacpp")

    Returns:
        Initialized NetBoxDeepAgent
    """
    agent = NetBoxDeepAgent(
        netbox_config=netbox_config,
        model_name=model_name,
        skills_path=skills_path,
        enable_metrics=enable_metrics,
        backend=backend,
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
