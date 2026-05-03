"""Pytest fixtures for NetBox DeepAgents testing."""

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_ollama import ChatOllama

from src.utils.config import NetBoxConfig, OllamaConfig, QueryMetrics


@pytest.fixture
def mock_netbox_config():
    """Mock NetBox configuration."""
    return NetBoxConfig(
        url="http://localhost:8000",
        token="test-token-12345",
        mcp_server_path="/test/path/mcp",
    )


@pytest.fixture
def mock_ollama_config():
    """Mock Ollama configuration."""
    return OllamaConfig(
        model="mixtral:8x7b",
        temperature=0.0,
        base_url="http://localhost:11434",
    )


@pytest.fixture
def mock_netbox_response():
    """Mock successful NetBox API response."""
    return {
        "count": 2,
        "results": [
            {
                "id": 1,
                "name": "test-device-01",
                "site": {"id": 5, "name": "NYC-DC1"},
                "status": "active",
            },
            {
                "id": 2,
                "name": "test-device-02",
                "site": {"id": 5, "name": "NYC-DC1"},
                "status": "active",
            },
        ],
    }


@pytest.fixture
def mock_cable_response():
    """Mock cable query response."""
    return {
        "count": 1,
        "results": [
            {
                "id": 42,
                "termination_a": {
                    "id": 1,
                    "device": {"id": 19, "name": "dmi01-nashua-pdu01"},
                },
                "termination_b": {
                    "id": 2,
                    "device": {"id": 20, "name": "switch01"},
                },
                "status": "connected",
            }
        ],
    }


@pytest.fixture
def failed_queries():
    """Queries that fail in baseline implementation."""
    return [
        "Show cables connected to device dmi01-nashua-pdu01",
        "Show all Dunder-Mifflin sites with device counts",
        "List interfaces on device with site_id 5",
        "Find all power outlets in rack R01",
        "Get VLANs in site with name containing 'prod'",
    ]


@pytest.fixture
def successful_queries():
    """Queries that should succeed with simple filters."""
    return [
        "Show device with ID 42",
        "Get site named NYC-DC1",
        "List all active devices",
        "Search for production servers",
    ]


@pytest.fixture
def invalid_filters():
    """Invalid filter patterns that should be caught."""
    return [
        {"device__site_id": 5},
        {"termination_a__device_id": 19},
        {"name__icontains": "dunder"},
        {"interface__device__name": "router01"},
        {"created__gte": "2024-01-01"},
        {"id__in": [1, 2, 3]},
    ]


@pytest.fixture
def valid_filters():
    """Valid filter patterns that should work."""
    return [
        {"device_id": 123},
        {"site_id": 5},
        {"name": "exact-name"},
        {"status": "active"},
        {"role": "server"},
        {"device_id": 42, "status": "active"},
    ]


@pytest.fixture
def mock_ollama_model():
    """Mock Ollama model for testing."""
    mock = MagicMock(spec=ChatOllama)
    mock.model = "mixtral:8x7b"
    mock.temperature = 0.0
    mock.options = {"num_ctx": 8192}

    # Mock invoke method
    mock.invoke = MagicMock(
        return_value=AIMessage(content="Mocked response from Ollama model")
    )

    # Mock async stream
    async def mock_astream(*args, **kwargs):
        yield {"messages": [AIMessage(content="Streaming response chunk 1")]}
        yield {"messages": [AIMessage(content="Streaming response chunk 2")]}

    mock.astream = mock_astream

    return mock


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for testing."""
    mock = AsyncMock()

    # Mock connection methods
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()

    # Mock get_tools method
    async def get_tools():
        from langchain_core.tools import Tool

        return [
            Tool(
                name="netbox_get_objects",
                description="Get NetBox objects",
                func=AsyncMock(return_value={"count": 1, "results": []}),
            ),
            Tool(
                name="netbox_get_object_by_id",
                description="Get NetBox object by ID",
                func=AsyncMock(return_value={"id": 1, "name": "test"}),
            ),
            Tool(
                name="netbox_search_objects",
                description="Search NetBox objects",
                func=AsyncMock(return_value={"results": []}),
            ),
        ]

    mock.get_tools = get_tools

    return mock


@pytest.fixture
def mock_deep_agent():
    """Mock DeepAgent for testing."""
    mock = AsyncMock()

    # Mock astream method for streaming responses
    async def mock_astream(messages, **kwargs):
        yield {
            "messages": [
                AIMessage(content="I'll help you query NetBox for that information.")
            ]
        }
        yield {"messages": [AIMessage(content="Here are the results...")]}

    mock.astream = mock_astream

    return mock


@pytest.fixture
def query_metrics():
    """Fresh QueryMetrics instance for testing."""
    return QueryMetrics()


@pytest.fixture
def test_skill_content():
    """Sample skill content for testing."""
    return """---
title: Test NetBox Skill
description: Test skill for NetBox queries
version: 1.0.0
tags: [test, netbox]
priority: high
trigger: test queries
---

# Test Skill Content

This is a test skill for unit testing.

## Key Points
- Always use two-step queries
- Avoid Django lookups
- Use search for patterns
"""


@pytest.fixture
def mock_filter_error():
    """Mock filter error for testing recovery."""
    return ValueError(
        "MCP Filter Error: Invalid filter: device__site_id\n"
        "Suggestion: Perform two-step query: 1) Get device by name, 2) Use device_id filter\n"
        "Consult the netbox-mcp-filters skill for guidance."
    )


@pytest.fixture
async def mock_agent_state():
    """Mock agent state for middleware testing."""
    return {
        "messages": [
            HumanMessage(content="Show cables for device router01"),
            AIMessage(content="I'll query NetBox for cables connected to router01."),
        ],
        "error": None,
        "model_name": "mixtral:8x7b",
        "token_count": 150,
    }


# Pytest configuration for async tests
pytest_plugins = ["pytest_asyncio"]