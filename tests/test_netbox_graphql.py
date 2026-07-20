"""Unit tests for the read-only NetBox GraphQL tool.

HTTP is mocked via httpx.MockTransport; parsing, read-only validation, and the
safety limits are exercised for real (never mocked). Introspection responses are
generated from a small real schema with graphql-core so schema discovery is
tested end-to-end.
"""

import json

import httpx
import pytest
from graphql import build_schema, get_introspection_query, graphql_sync

from src.tools import netbox_graphql as gql
from src.tools.netbox_graphql import (
    build_graphql_tools,
    discover_schema,
    execute_graphql,
)
from src.utils.config import NetBoxConfig


@pytest.fixture
def cfg():
    return NetBoxConfig(
        url="http://localhost:8000", token="test-token-12345", mcp_server_path="/x"
    )


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    """The introspection cache is module-level; isolate tests."""
    gql._schema_cache.clear()
    yield
    gql._schema_cache.clear()


def _json_transport(body: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _forbidden_transport():
    """Fails loudly if any HTTP request is attempted."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be called for a rejected document")

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------- execution ---

async def test_direct_call_nested_query_returns_data(cfg):
    """Direct call, no model/skill involved — proves the tool works standalone."""
    body = {"data": {"device_list": [{"name": "rtr01", "site": {"name": "DM-Nashua"}}]}}
    result = await execute_graphql(
        cfg,
        "query { device_list(filters: {name: {exact: \"rtr01\"}}) { name site { name } } }",
        transport=_json_transport(body),
    )
    assert isinstance(result, dict)
    assert result["data"]["device_list"][0]["site"]["name"] == "DM-Nashua"
    assert result["errors"] is None


async def test_query_with_variables_forwarded(cfg):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"data": {"device_list": []}})

    result = await execute_graphql(
        cfg,
        "query($n: String!) { device_list(filters: {name: {exact: $n}}) { name } }",
        variables={"n": "rtr01"},
        transport=httpx.MockTransport(handler),
    )
    assert isinstance(result, dict)
    assert captured["variables"] == {"n": "rtr01"}


async def test_auth_header_and_endpoint(cfg):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": {}})

    await execute_graphql(cfg, "query { __typename }", transport=httpx.MockTransport(handler))
    assert captured["url"] == "http://localhost:8000/graphql/"
    assert captured["auth"] == "Token test-token-12345"


async def test_endpoint_normalized_when_url_has_trailing_slash():
    cfg = NetBoxConfig(
        url="http://localhost:8000/", token="test-token-12345", mcp_server_path="/x"
    )
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"data": {}})

    await execute_graphql(cfg, "query { __typename }", transport=httpx.MockTransport(handler))
    assert captured["url"] == "http://localhost:8000/graphql/"


async def test_graphql_errors_passed_through(cfg):
    body = {"data": None, "errors": [{"message": "Cannot query field 'nope'"}]}
    result = await execute_graphql(cfg, "query { nope }", transport=_json_transport(body))
    assert isinstance(result, dict)
    assert result["errors"][0]["message"].startswith("Cannot query field")


# --------------------------------------------------- read-only enforcement ---

async def test_mutation_rejected_before_any_http(cfg):
    result = await execute_graphql(
        cfg,
        "mutation { device_add(input: {name: \"x\"}) { id } }",
        transport=_forbidden_transport(),
    )
    assert isinstance(result, str)
    assert result.startswith("TOOL_VALIDATION_ERROR")
    assert "query" in result.lower()


async def test_subscription_rejected_before_any_http(cfg):
    result = await execute_graphql(
        cfg, "subscription { deviceChanged { id } }", transport=_forbidden_transport()
    )
    assert result.startswith("TOOL_VALIDATION_ERROR")


async def test_mixed_query_and_mutation_rejected(cfg):
    doc = "query { device_list { name } } mutation { device_add(input: {}) { id } }"
    result = await execute_graphql(cfg, doc, transport=_forbidden_transport())
    assert result.startswith("TOOL_VALIDATION_ERROR")


async def test_malformed_document_rejected(cfg):
    result = await execute_graphql(cfg, "query { device_list {{{", transport=_forbidden_transport())
    assert result.startswith("TOOL_VALIDATION_ERROR")
    assert "malformed" in result.lower()


async def test_query_document_too_large(cfg, monkeypatch):
    monkeypatch.setattr(gql, "GQL_MAX_QUERY_CHARS", 20)
    result = await execute_graphql(
        cfg, "query { device_list { name description comments } }", transport=_forbidden_transport()
    )
    assert result.startswith("TOOL_VALIDATION_ERROR")
    assert "exceeds limit" in result


async def test_depth_limit_enforced(cfg, monkeypatch):
    monkeypatch.setattr(gql, "GQL_MAX_DEPTH", 2)
    # depth 3: device_list -> site -> region -> name
    deep = "query { device_list { site { region { name } } } }"
    result = await execute_graphql(cfg, deep, transport=_forbidden_transport())
    assert result.startswith("TOOL_VALIDATION_ERROR")
    assert "depth" in result.lower()


# ------------------------------------------------------------- error paths ---

async def test_timeout_becomes_structured_error(cfg):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    result = await execute_graphql(
        cfg, "query { __typename }", transport=httpx.MockTransport(handler)
    )
    assert result.startswith("TOOL_API_ERROR")
    assert "timed out" in result.lower()


async def test_http_401_safe_error_no_token(cfg):
    result = await execute_graphql(
        cfg, "query { __typename }", transport=_json_transport({"detail": "bad"}, status=401)
    )
    assert result.startswith("TOOL_API_ERROR")
    assert "401" in result
    assert "test-token-12345" not in result


async def test_http_400_handled(cfg):
    result = await execute_graphql(
        cfg, "query { __typename }", transport=_json_transport({"detail": "bad"}, status=400)
    )
    assert result.startswith("TOOL_API_ERROR")


async def test_invalid_json_response(cfg):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    result = await execute_graphql(
        cfg, "query { __typename }", transport=httpx.MockTransport(handler)
    )
    assert result.startswith("TOOL_API_ERROR")


async def test_response_size_limit(cfg, monkeypatch):
    monkeypatch.setattr(gql, "GQL_MAX_RESPONSE_CHARS", 10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 500)

    result = await execute_graphql(
        cfg, "query { __typename }", transport=httpx.MockTransport(handler)
    )
    assert result.startswith("TOOL_API_ERROR")
    assert "exceeds limit" in result


async def test_token_never_leaks_in_error(cfg):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom involving Token test-token-12345 here")

    result = await execute_graphql(
        cfg, "query { __typename }", transport=httpx.MockTransport(handler)
    )
    assert "test-token-12345" not in result
    assert "***REDACTED***" in result


# ------------------------------------------------------- schema discovery ---

def _introspection_transport():
    """Return a MockTransport that serves a real introspection result built from
    a small SDL schema."""
    sdl = """
    type Region { name: String }
    type Site { name: String region: Region }
    type Device { name: String site: Site }
    type Query { device_list: [Device] site_list: [Site] }
    """
    schema = build_schema(sdl)
    result = graphql_sync(schema, get_introspection_query(descriptions=False))
    assert result.errors is None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": result.data})

    return httpx.MockTransport(handler)


async def test_schema_discovery_lists_root_fields(cfg):
    result = await discover_schema(cfg, transport=_introspection_transport())
    assert isinstance(result, dict)
    assert result["root_query_fields"] == ["device_list", "site_list"]


async def test_schema_discovery_describes_type(cfg):
    result = await discover_schema(cfg, type_name="Device", transport=_introspection_transport())
    assert isinstance(result, dict)
    assert set(result["fields"]) == {"name", "site"}


async def test_schema_discovery_unknown_type(cfg):
    result = await discover_schema(cfg, type_name="Nonexistent", transport=_introspection_transport())
    assert isinstance(result, str)
    assert result.startswith("TOOL_VALIDATION_ERROR")


async def test_schema_discovery_disabled(cfg):
    body = {"data": None, "errors": [{"message": "introspection is disabled"}]}
    result = await discover_schema(cfg, transport=_json_transport(body))
    assert isinstance(result, str)
    assert result.startswith("TOOL_API_ERROR")


# ------------------------------------------------------------- factory ---

async def test_build_graphql_tools_registers_both(cfg):
    tools = build_graphql_tools(cfg, transport=_json_transport({"data": {"device_list": []}}))
    names = {t.name for t in tools}
    assert names == {"netbox_graphql", "netbox_graphql_schema"}


async def test_tool_invocation_via_ainvoke(cfg):
    tools = {
        t.name: t
        for t in build_graphql_tools(
            cfg, transport=_json_transport({"data": {"device_list": [{"name": "rtr01"}]}})
        )
    }
    out = await tools["netbox_graphql"].ainvoke({"query": "query { device_list { name } }"})
    assert isinstance(out, dict)
    assert out["data"]["device_list"][0]["name"] == "rtr01"
