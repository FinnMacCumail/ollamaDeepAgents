"""Read-only NetBox GraphQL tool for the DeepAgent.

Supplements the four MCP read tools (`netbox_get_objects`, etc.) with a
server-side GraphQL path for nested / cross-model relationship reads — one
request instead of the multi-hop REST decomposition the `netbox-mcp-filters`
skill routes around.

Design (see PRPs/netbox-graphql-read-tool.md):
- **Read-only.** Every operation in the document must be a `query`; mutations
  and subscriptions are rejected via AST inspection (graphql-core), never regex,
  *before any HTTP call*. NetBox's GraphQL endpoint is read-only server-side
  anyway, so this is defense-in-depth + clean errors; the real safety surface is
  query cost (depth / document size / response size / timeout).
- **Standalone.** These tools are NOT wrapped by `NetBoxToolWrapper`, so they
  bypass `FilterValidator` (whose Django→MCP suffix grammar is irrelevant here).
- **Structured errors as strings.** Mirrors `netbox_tools.py`: failures return a
  `TOOL_VALIDATION_ERROR:` / `TOOL_API_ERROR:` string (never raise), so langgraph
  threads them back as a ToolMessage and the model can recover.
- **Secrets hygiene.** The endpoint + `Authorization: Token <token>` header are
  built internally from `NetBoxConfig`; the token is never logged or returned.

Live-verified facts (2026-07-20, NetBox 4.3/4.4 Strawberry line):
- endpoint `{url}/graphql/`, auth `Authorization: Token <40-hex>` (not Bearer)
- introspection enabled
- ID filters are bare (`id: 6`); string filters use lookup objects
  (`name: {exact: "..."}`); the 4.5 `id: {exact: N}` form does NOT work here
- root query fields are `<model>_list` (e.g. `device_list`, `vlan_list`)
"""

import json
import os

import httpx
from graphql import (
    OperationType,
    build_client_schema,
    get_introspection_query,
    parse,
)
from graphql.error import GraphQLError
from graphql.language.ast import (
    FieldNode,
    ListValueNode,
    NullValueNode,
    ObjectValueNode,
    OperationDefinitionNode,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..utils.config import NetBoxConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Safety limits — env-overridable, non-secret (documented in .env.example).
GQL_TIMEOUT: float = float(os.getenv("NETBOX_GQL_TIMEOUT", "30"))
GQL_MAX_QUERY_CHARS: int = int(os.getenv("NETBOX_GQL_MAX_QUERY_CHARS", "8000"))
GQL_MAX_RESPONSE_CHARS: int = int(os.getenv("NETBOX_GQL_MAX_RESPONSE_CHARS", "200000"))
GQL_MAX_DEPTH: int = int(os.getenv("NETBOX_GQL_MAX_DEPTH", "12"))

# In-process introspection cache, keyed by endpoint. NetBox schema is stable for
# the life of the process; a new thread/process rebuilds it lazily on first use.
_schema_cache: dict[str, object] = {}


class NetBoxGraphQLInput(BaseModel):
    """Arguments for the netbox_graphql tool."""

    query: str = Field(..., description="A read-only GraphQL query document.")
    variables: dict | None = Field(
        default=None, description="Optional JSON-compatible GraphQL variables."
    )


class NetBoxGraphQLSchemaInput(BaseModel):
    """Arguments for the netbox_graphql_schema tool."""

    type_name: str | None = Field(
        default=None,
        description=(
            "A GraphQL type to describe (its fields + their types). "
            "Omit to list the available root query fields (e.g. device_list)."
        ),
    )


_EXEC_DESCRIPTION = (
    "Run ONE read-only NetBox GraphQL query for CROSS-MODEL reads anchored on a "
    "SET of objects that must be filtered/joined across models (e.g. devices at "
    "several sites with their region, circuits per provider) or 3+-hop ID joins. "
    "Deciding test = how many ANCHOR objects, NOT how many models the answer "
    "touches. DO NOT use this for a single named object's own details — its site, "
    "assigned IPs, tenant, role, status — even when the answer spans several "
    "models; that is a single-object lookup, use netbox_get_objects (resolve the "
    "object, then read its related IDs) or netbox_search_objects. Read-only: "
    "mutations are rejected. If unsure of the schema, call netbox_graphql_schema "
    "first. NetBox filter grammar here: the argument is 'filters' (plural); ID "
    "filters take ONE bare id (filters: {id: 6}) - never a list, never a lookup "
    "object; string fields use lookup objects (filters: {name: {exact: "
    '"dmi01-nashua-rtr01"}} / {name: {in_list: [...]}} / {name: {i_contains: "x"}}); '
    "paging is pagination: {limit, offset}; at most 10 aliases per document; "
    "root query fields are <model>_list (device_list, vlan_list, cable_list, ...)."
)

_SCHEMA_DESCRIPTION = (
    "Discover the NetBox GraphQL schema. Call with no arguments to list the root "
    "query fields; call with type_name to get that type's fields and their types. "
    "Use this before writing a netbox_graphql query when unsure of field names."
)


def _endpoint(cfg: NetBoxConfig) -> str:
    """GraphQL endpoint. cfg.url is already trailing-slash-normalized."""
    return f"{cfg.url}/graphql/"


def _headers(cfg: NetBoxConfig) -> dict[str, str]:
    return {
        "Authorization": f"Token {cfg.token}",
        "Content-Type": "application/json",
    }


def _sanitize(msg: str, cfg: NetBoxConfig) -> str:
    """Never let the token leak into a returned/logged message."""
    if cfg.token and cfg.token in msg:
        msg = msg.replace(cfg.token, "***REDACTED***")
    return msg


def _max_query_depth(document) -> int:
    """Approximate selection-set nesting depth (fragment spreads count as 1)."""

    def _depth(selection_set) -> int:
        if selection_set is None:
            return 0
        best = 0
        for sel in selection_set.selections:
            best = max(best, 1 + _depth(getattr(sel, "selection_set", None)))
        return best

    deepest = 0
    for defn in document.definitions:
        deepest = max(deepest, _depth(getattr(defn, "selection_set", None)))
    return deepest


def _validate_read_only(query: str) -> str | None:
    """Return an error message if the document is not a safe read-only query,
    else None. Parses the AST — no regex/substring matching."""
    try:
        document = parse(query)
    except GraphQLError as e:
        return f"malformed GraphQL document: {e}"

    saw_query = False
    for defn in document.definitions:
        if isinstance(defn, OperationDefinitionNode):
            if defn.operation != OperationType.QUERY:
                return (
                    f"only read-only 'query' operations are permitted; "
                    f"found '{defn.operation.value}'"
                )
            saw_query = True

    if not saw_query:
        return "document contains no query operation"

    depth = _max_query_depth(document)
    if depth > GQL_MAX_DEPTH:
        return f"query nesting depth {depth} exceeds the limit of {GQL_MAX_DEPTH}"

    return _validate_filter_grammar(document)


# Grammar pre-checks for mistakes the model made repeatedly in the v5 runs
# (20 of 31 GraphQL calls failed in the 2026-10-17 run; each failure costs a
# model round trip). Each rule is verified against NetBox 4.3.3's strawberry
# schema on 2026-10-18. See docs/development/2026-10-18_filter-naming-after-in.md.
GQL_MAX_ALIASES: int = 10  # NetBox: "12 aliases found. Allowed: 10"
_LIST_FIELD_ARGS = frozenset({"filters", "pagination", "ordering"})


def _iter_fields(selection_set):
    """Yield every FieldNode under a selection set, depth first."""
    if selection_set is None:
        return
    for sel in selection_set.selections:
        if isinstance(sel, FieldNode):
            yield sel
            yield from _iter_fields(sel.selection_set)
        elif getattr(sel, "selection_set", None) is not None:  # inline fragments
            yield from _iter_fields(sel.selection_set)


def _check_filter_object(obj: ObjectValueNode, where: str, path: str = "") -> str | None:
    """Reject filter shapes NetBox's ID scalars do not accept or silently ignore.
    Applies at every nesting depth: a relation filter such as `tenant: {id: ...}`
    carries the same plain-ID `id` key as the top level (verified 2026-10-19:
    `tenant: {id: {exact: 14}}` and `device: {id: {in_list: [...]}}` fail with
    'ID cannot represent a non-string and non-integer value'; `tenant: {id: 14}` works)."""
    for f in obj.fields:
        name = f.name.value
        label = f"{path}{name}"
        is_id_key = name == "id" or name.endswith("_id")
        if is_id_key and isinstance(f.value, ListValueNode):
            return (
                f"{where}: '{label}' takes ONE id, not a list (NetBox: 'ID cannot "
                f"represent a non-string and non-integer value'). For several objects "
                f"use a string lookup (name: {{in_list: [...]}}), a parent filter "
                f"(site_id, tenant_id), or up to {GQL_MAX_ALIASES} aliased queries with one id each"
            )
        if is_id_key and isinstance(f.value, ObjectValueNode):
            return (
                f"{where}: '{label}' is a plain ID scalar and takes no lookup object "
                f"(no exact/in_list) - pass the bare id: {name}: 6"
            )
        if is_id_key and isinstance(f.value, NullValueNode):
            return (
                f"{where}: '{label}: null' is silently ignored (returns every object). "
                f"For unassigned objects use the REST tool: "
                f"netbox_get_objects(<type>, filters={{'{name}': null}})"
            )
        # recurse into nested relation filters (tenant: {...}, device: {...}) and
        # the AND/OR/NOT combinators; lookup objects on string fields have no
        # id keys, so recursing into them is harmless
        if not is_id_key and isinstance(f.value, ObjectValueNode):
            err = _check_filter_object(f.value, where, f"{label}.")
            if err:
                return err
    return None


def _validate_filter_grammar(document) -> str | None:
    """Return an error message for filter-grammar mistakes NetBox would reject
    (or silently ignore), else None. Runs before any HTTP request."""
    n_aliases = 0
    for defn in document.definitions:
        if not isinstance(defn, OperationDefinitionNode):
            continue
        for field in _iter_fields(defn.selection_set):
            if field.alias is not None:
                n_aliases += 1
            fname = field.name.value
            if not fname.endswith("_list"):
                continue
            for arg in field.arguments:
                aname = arg.name.value
                if aname == "filter":
                    return f"'{fname}(filter: ...)': the argument is 'filters' (plural)"
                if aname in ("limit", "offset"):
                    return (
                        f"'{fname}({aname}: ...)': there is no '{aname}' argument; use "
                        f"pagination: {{limit: <n>, offset: <n>}}"
                    )
                if aname not in _LIST_FIELD_ARGS:
                    return (
                        f"'{fname}({aname}: ...)': unknown argument; filters go inside "
                        f"'filters: {{...}}' (e.g. filters: {{{aname}: ...}})"
                    )
                if aname == "filters" and isinstance(arg.value, ObjectValueNode):
                    err = _check_filter_object(arg.value, f"'{fname}(filters: ...)'")
                    if err:
                        return err
    if n_aliases > GQL_MAX_ALIASES:
        return (
            f"{n_aliases} aliased queries; NetBox allows {GQL_MAX_ALIASES}. Split the "
            f"document, or filter on a parent (site_id/tenant_id) and select client-side"
        )
    return None


def _validation_error(msg: str) -> str:
    return (
        f"TOOL_VALIDATION_ERROR: {msg}\n"
        f"This tool accepts read-only GraphQL 'query' operations only. "
        f"Fix the document and reissue the tool call."
    )


def _api_error(msg: str) -> str:
    return (
        f"TOOL_API_ERROR: {msg}\n"
        f"The NetBox GraphQL endpoint rejected or could not complete this call. "
        f"Re-examine the query (call netbox_graphql_schema to confirm field names) "
        f"and reissue with a corrected shape."
    )


async def execute_graphql(
    cfg: NetBoxConfig,
    query: str,
    variables: dict | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict | str:
    """Execute a read-only GraphQL query. Returns the parsed {data, errors} dict
    on success, or a structured TOOL_*_ERROR string on any failure."""
    if len(query) > GQL_MAX_QUERY_CHARS:
        return _validation_error(
            f"query document is {len(query)} chars, exceeds limit "
            f"{GQL_MAX_QUERY_CHARS}"
        )

    err = _validate_read_only(query)
    if err is not None:
        logger.warning("Rejected non-read-only/malformed GraphQL", reason=err)
        return _validation_error(err)

    payload = {"query": query, "variables": variables or {}}
    try:
        async with httpx.AsyncClient(timeout=GQL_TIMEOUT, transport=transport) as client:
            resp = await client.post(_endpoint(cfg), json=payload, headers=_headers(cfg))
    except httpx.TimeoutException:
        return _api_error(f"request timed out after {GQL_TIMEOUT}s")
    except httpx.HTTPError as e:
        return _api_error(_sanitize(f"transport error: {e}", cfg))

    body = resp.text
    if len(body) > GQL_MAX_RESPONSE_CHARS:
        return _api_error(
            f"response is {len(body)} chars, exceeds limit {GQL_MAX_RESPONSE_CHARS}; "
            f"narrow the query or add pagination (offset/limit)"
        )

    if resp.status_code in (401, 403):
        return _api_error(f"authentication/authorization failed (HTTP {resp.status_code})")
    if resp.status_code >= 400:
        return _api_error(
            _sanitize(f"HTTP {resp.status_code}: {body[:500]}", cfg)
        )

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        return _api_error(_sanitize(f"response was not valid JSON: {body[:500]}", cfg))

    # Pass GraphQL data + errors through so the model sees partial results + errors.
    return {"data": data.get("data"), "errors": data.get("errors")}


async def discover_schema(
    cfg: NetBoxConfig,
    type_name: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict | str:
    """List root query fields (type_name=None) or describe one type's fields.
    Caches the introspected schema in-process per endpoint."""
    endpoint = _endpoint(cfg)
    schema = _schema_cache.get(endpoint)

    if schema is None:
        introspection = get_introspection_query(descriptions=False)
        try:
            async with httpx.AsyncClient(timeout=GQL_TIMEOUT, transport=transport) as client:
                resp = await client.post(
                    endpoint, json={"query": introspection}, headers=_headers(cfg)
                )
        except httpx.TimeoutException:
            return _api_error(f"introspection timed out after {GQL_TIMEOUT}s")
        except httpx.HTTPError as e:
            return _api_error(_sanitize(f"introspection transport error: {e}", cfg))

        if resp.status_code >= 400:
            return _api_error(f"introspection failed (HTTP {resp.status_code})")
        try:
            result = resp.json()
        except (json.JSONDecodeError, ValueError):
            return _api_error("introspection response was not valid JSON")
        if result.get("errors") or not result.get("data"):
            return _api_error(
                "introspection is disabled or returned no schema on this instance"
            )
        try:
            schema = build_client_schema(result["data"])
        except Exception as e:  # noqa: BLE001 - surface any schema-build failure to the model
            return _api_error(_sanitize(f"could not build schema: {e}", cfg))
        _schema_cache[endpoint] = schema

    if type_name is None:
        query_type = getattr(schema, "query_type", None)
        fields = sorted(query_type.fields.keys()) if query_type else []
        return {"root_query_fields": fields}

    gql_type = getattr(schema, "type_map", {}).get(type_name)
    type_fields = getattr(gql_type, "fields", None)
    if gql_type is None or type_fields is None:
        return _validation_error(
            f"unknown GraphQL type '{type_name}'; call netbox_graphql_schema with "
            f"no arguments to list root query fields"
        )
    return {
        "type": type_name,
        "fields": {name: str(f.type) for name, f in type_fields.items()},
    }


def build_graphql_tools(
    cfg: NetBoxConfig, transport: httpx.AsyncBaseTransport | None = None
) -> list[StructuredTool]:
    """Build the standalone read-only GraphQL tools, closing over the NetBox
    config (and an optional httpx transport for testing)."""

    async def _netbox_graphql(query: str, variables: dict | None = None) -> dict | str:
        return await execute_graphql(cfg, query, variables, transport=transport)

    async def _netbox_graphql_schema(type_name: str | None = None) -> dict | str:
        return await discover_schema(cfg, type_name, transport=transport)

    exec_tool = StructuredTool.from_function(
        coroutine=_netbox_graphql,
        name="netbox_graphql",
        description=_EXEC_DESCRIPTION,
        args_schema=NetBoxGraphQLInput,
    )
    schema_tool = StructuredTool.from_function(
        coroutine=_netbox_graphql_schema,
        name="netbox_graphql_schema",
        description=_SCHEMA_DESCRIPTION,
        args_schema=NetBoxGraphQLSchemaInput,
    )
    return [exec_tool, schema_tool]
