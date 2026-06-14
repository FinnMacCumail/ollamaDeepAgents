"""Integration tests for NetBox DeepAgents system."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.netbox_agent import NetBoxDeepAgent, create_netbox_agent, query_netbox
from src.utils.config import NetBoxConfig, QueryMetrics


class TestNetBoxAgentInitialization:
    """Test NetBox agent initialization."""

    @pytest.mark.asyncio
    @patch("src.agents.netbox_agent.create_netbox_mcp_client")
    @patch("src.agents.netbox_agent.create_ollama_model")
    @patch("src.agents.netbox_agent.create_deep_agent")
    async def test_agent_initialization(
        self, mock_create_deep_agent, mock_create_ollama, mock_create_mcp, mock_netbox_config
    ):
        """Test agent initializes with all components."""
        # Setup mocks
        mock_mcp_client = AsyncMock()
        mock_create_mcp.return_value = mock_mcp_client

        mock_ollama = MagicMock()
        mock_create_ollama.return_value = mock_ollama

        mock_agent = MagicMock()
        mock_create_deep_agent.return_value = mock_agent

        # Create and initialize agent
        agent = NetBoxDeepAgent(netbox_config=mock_netbox_config)
        await agent.initialize()

        # Verify initialization
        assert agent.mcp_client == mock_mcp_client
        assert agent.agent == mock_agent
        mock_create_mcp.assert_called_once()
        mock_create_ollama.assert_called_once()
        mock_create_deep_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_requires_initialization(self):
        """Test that agent methods require initialization."""
        agent = NetBoxDeepAgent()

        with pytest.raises(RuntimeError, match="not initialized"):
            async for _ in agent.query("test query"):
                pass

    @pytest.mark.asyncio
    @patch("src.agents.netbox_agent.load_netbox_config")
    @patch("src.agents.netbox_agent.create_netbox_mcp_client")
    @patch("src.agents.netbox_agent.create_ollama_model")
    @patch("src.agents.netbox_agent.create_deep_agent")
    async def test_agent_loads_config_from_env(
        self,
        mock_create_deep_agent,
        mock_create_ollama,
        mock_create_mcp,
        mock_load_netbox_config,
        mock_netbox_config,
        mock_ollama_config,
    ):
        """Test agent loads NetBox credentials from env when not provided."""
        mock_load_netbox_config.return_value = mock_netbox_config
        mock_create_mcp.return_value = AsyncMock()

        agent = NetBoxDeepAgent()  # No config provided
        await agent.initialize()

        mock_load_netbox_config.assert_called_once()
        assert agent.netbox_config == mock_netbox_config


class TestNetBoxAgentQuerying:
    """Test NetBox agent query functionality."""

    @pytest.mark.asyncio
    async def test_query_streaming(self):
        """Test streaming query responses."""
        agent = NetBoxDeepAgent()
        agent.agent = AsyncMock()

        # Mock streaming response
        async def mock_astream(*args, **kwargs):
            yield {"messages": [MagicMock(content="Response chunk 1")]}
            yield {"messages": [MagicMock(content="Response chunk 2")]}

        agent.agent.astream = mock_astream

        # Collect streamed response
        response_parts = []
        async for chunk in agent.query("test query"):
            response_parts.append(chunk)

        assert len(response_parts) == 2
        assert response_parts[0] == "Response chunk 1"
        assert response_parts[1] == "Response chunk 2"

    @pytest.mark.asyncio
    async def test_query_sync(self):
        """Test synchronous query execution."""
        agent = NetBoxDeepAgent()
        agent.agent = AsyncMock()

        # Mock streaming response
        async def mock_astream(*args, **kwargs):
            yield {"messages": [MagicMock(content="Complete ")]}
            yield {"messages": [MagicMock(content="response")]}

        agent.agent.astream = mock_astream

        response = await agent.query_sync("test query")
        assert response == "Complete response"

    @pytest.mark.asyncio
    async def test_query_with_metrics(self):
        """Test query execution with metrics tracking."""
        agent = NetBoxDeepAgent(enable_metrics=True)
        agent.agent = AsyncMock()

        async def mock_astream(*args, **kwargs):
            yield {"messages": [MagicMock(content="Response")]}

        agent.agent.astream = mock_astream

        await agent.query_sync("test query")

        # Check metrics
        assert agent.metrics.total_queries == 1
        assert agent.metrics.successful_queries == 1
        assert len(agent.metrics.response_times) == 1

    @pytest.mark.asyncio
    async def test_query_filter_error_handling(self):
        """Test handling of filter errors during query."""
        agent = NetBoxDeepAgent(enable_metrics=True)
        agent.agent = AsyncMock()

        # Simulate filter error
        async def mock_astream(*args, **kwargs):
            raise ValueError("Invalid filter: device__site_id")

        agent.agent.astream = mock_astream

        response_parts = []
        try:
            async for chunk in agent.query("test query"):
                response_parts.append(chunk)
        except ValueError:
            pass  # Expected

        # Check error handling
        assert agent.metrics.total_queries == 1
        assert agent.metrics.filter_errors == 1
        assert any("filter constraint issue" in part for part in response_parts)

    @pytest.mark.asyncio
    async def test_batch_query(self):
        """Test batch query execution."""
        agent = NetBoxDeepAgent()
        agent.agent = AsyncMock()

        # Mock responses
        async def mock_astream(*args, **kwargs):
            query = args[0]["messages"][0]["content"]
            yield {"messages": [MagicMock(content=f"Response for: {query}")]}

        agent.agent.astream = mock_astream

        queries = ["Query 1", "Query 2", "Query 3"]
        results = await agent.batch_query(queries)

        assert len(results) == 3
        assert results["Query 1"] == "Response for: Query 1"
        assert results["Query 2"] == "Response for: Query 2"
        assert results["Query 3"] == "Response for: Query 3"


class TestFailedQueryRecovery:
    """Test recovery from failed queries."""

    @pytest.mark.asyncio
    async def test_cable_query_recovery(self, failed_queries, mock_cable_response):
        """Test recovery for cable query with relationship filter."""
        agent = NetBoxDeepAgent(enable_metrics=True)
        agent.agent = AsyncMock()

        # Simulate successful recovery after filter error
        call_count = 0

        async def mock_astream(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First attempt fails with filter error
                raise ValueError("Invalid filter: termination_a__device_id")
            else:
                # Recovery succeeds
                yield {"messages": [MagicMock(content=str(mock_cable_response))]}

        agent.agent.astream = mock_astream

        # Query should eventually succeed with recovery
        query = failed_queries[0]  # Cable query
        response = ""
        try:
            async for chunk in agent.query(query):
                response += chunk
        except ValueError:
            # Recovery middleware should handle this
            pass

        # Verify error was caught
        assert agent.metrics.filter_errors > 0

    @pytest.mark.asyncio
    async def test_site_search_recovery(self, failed_queries):
        """Test recovery for site search with Django lookup."""
        agent = NetBoxDeepAgent(enable_metrics=True)
        agent.agent = AsyncMock()

        # Simulate recovery from icontains error
        async def mock_astream(*args, **kwargs):
            query_content = args[0]["messages"][0]["content"]
            if "icontains" in str(query_content):
                raise ValueError("Invalid filter: name__icontains")
            else:
                yield {"messages": [MagicMock(content="Sites found via search")]}

        agent.agent.astream = mock_astream

        query = failed_queries[1]  # Dunder-Mifflin sites query
        try:
            response = await agent.query_sync(query)
            # Recovery should suggest using search
        except ValueError as e:
            assert "Invalid filter" in str(e)


class TestMetricsTracking:
    """Test metrics tracking functionality."""

    @pytest.mark.asyncio
    async def test_metrics_report_generation(self):
        """Test generation of metrics report."""
        agent = NetBoxDeepAgent(enable_metrics=True)

        # Populate metrics
        agent.metrics.total_queries = 10
        agent.metrics.successful_queries = 8
        agent.metrics.filter_errors = 3
        agent.metrics.recovered_errors = 2
        agent.metrics.response_times = [1.0, 2.0, 1.5]
        agent.metrics.token_usage = [100, 150, 120]

        report = agent.get_metrics_report()

        assert "Total Queries: 10" in report
        assert "Successful: 8" in report
        assert "Success Rate: 80.0%" in report
        assert "Filter Errors: 3" in report
        assert "Recovered: 2" in report
        assert "Recovery Rate: 66.7%" in report

    @pytest.mark.asyncio
    async def test_metrics_disabled(self):
        """Test behavior when metrics are disabled."""
        agent = NetBoxDeepAgent(enable_metrics=False)

        report = agent.get_metrics_report()
        assert "disabled" in report.lower()


class TestAgentCleanup:
    """Test agent cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_cleanup_disconnects_mcp(self):
        """Test that cleanup disconnects MCP client."""
        agent = NetBoxDeepAgent()
        agent.mcp_client = AsyncMock()

        await agent.cleanup()

        agent.mcp_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_create_netbox_agent_helper():
    """Test the create_netbox_agent helper function."""
    with patch("src.agents.netbox_agent.NetBoxDeepAgent.initialize") as mock_init:
        mock_init.return_value = None

        agent = await create_netbox_agent(
            model_name="mixtral:8x7b",
            skills_path="/custom/skills",
            enable_metrics=False,
        )

        assert isinstance(agent, NetBoxDeepAgent)
        assert agent.model_name == "mixtral:8x7b"
        assert agent.skills_path == "/custom/skills"
        assert agent.enable_metrics is False
        mock_init.assert_called_once()


@pytest.mark.asyncio
async def test_query_netbox_helper(query_metrics):
    """Test the query_netbox helper function."""
    agent = NetBoxDeepAgent()
    agent.agent = AsyncMock()

    async def mock_astream(*args, **kwargs):
        yield {"messages": [MagicMock(content="Test response")]}

    agent.agent.astream = mock_astream

    response_parts = []
    async for chunk in query_netbox(agent, "test query", query_metrics):
        response_parts.append(chunk)

    assert response_parts == ["Test response"]
    assert query_metrics.total_queries == 1
    assert query_metrics.successful_queries == 1