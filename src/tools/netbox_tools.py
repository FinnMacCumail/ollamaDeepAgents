"""NetBox MCP tools wrapper with filter validation and error handling."""

import difflib
import gzip
import json
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool, Tool
from langchain_core.tools.base import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Lookup suffixes that NetBox's REST filtersets actually honour.
# Base list: netbox-mcp-server/src/netbox_mcp_server/server.py:135-153 (the
# MCP server's own VALID_SUFFIXES). `__gt/gte/lt/lte` were wrongly blacklisted
# once (trace 019e63c0) and are valid.
#
# `regex` / `iregex` are DELIBERATELY ABSENT: the MCP server lists them, but
# NetBox 4.3.3's FILTER_CHAR_BASED_LOOKUP_MAP has no regex lookup (it arrives
# in 4.3.5, netbox-community/netbox#19903), so `name__regex=^dmi01` is silently
# ignored and returns the whole table (verified live 2026-10-20: 141 of 141 vs
# `name__isw` -> 3). Re-add when the instance is >= 4.3.5.
#
# `in` is DELIBERATELY ABSENT although the upstream MCP whitelist lists it.
# NetBox 4.3 silently ignores `<field>__in` (no 400 — it drops the filter and
# returns the UNFILTERED set), verified live on 2026-10-06 against every
# field class: device_id__in=[149,150] -> 200 outlets (all tenants) vs
# device_id=[149,150] -> 16; id__in, site_id__in, name__in, vid__in likewise.
# Multi-value is the bare key with a list value (NetBox repeats the query
# param: ?device_id=149&device_id=150). Rejecting `__in` here turns a silent
# wrong answer into a structured TOOL_VALIDATION_ERROR the model can recover
# from. See docs/development/2026-10-06_in-lookup-silently-ignored.md.
VALID_SUFFIXES: frozenset[str] = frozenset({
    "n",
    "ic", "nic", "isw", "nisw", "iew", "niew", "ie", "nie",
    "empty",
    "lt", "lte", "gt", "gte",
})

# Relation (foreign-key) filter names NetBox exposes as `<name>` (slug) and
# `<name>_id` (pk). Used to catch "no <relation> assigned" filters that NetBox
# does not honour. Verified live on 2026-10-18 (dcim.device, 141 total, 15 with
# no tenant): `tenant_id=null` -> 15 (correct); `tenant__empty=true` and
# `tenant__isnull=true` -> 141 (SILENTLY IGNORED, same class as `__in`);
# `tenant__n=null` -> 126 (the COMPLEMENT: devices that HAVE a tenant). The
# only form NetBox honours for "unassigned" is `<relation>_id=null`. See
# docs/development/2026-10-18_filter-naming-after-in.md.
RELATION_FIELDS: frozenset[str] = frozenset({
    "tenant", "tenant_group", "site", "site_group", "region", "location", "rack",
    "rack_role", "device", "device_type", "device_role", "role", "platform",
    "manufacturer", "cluster", "cluster_type", "cluster_group", "virtual_machine",
    "vrf", "vlan", "vlan_group", "prefix", "aggregate", "rir", "provider",
    "provider_account", "provider_network", "circuit", "circuit_type", "type",
    "group", "parent", "interface", "vminterface", "cable", "module", "module_type",
    "power_panel", "power_feed", "power_port", "power_outlet", "primary_ip4",
    "primary_ip6", "primary_ip", "oob_ip", "nat_inside", "nat_outside",
    "contact", "contact_group", "contact_role", "config_template", "virtual_chassis",
    "fhrpgroup", "l2vpn", "tunnel", "wireless_lan", "wireless_lan_group",
})

# `ipam.ipaddress` has no containment filters of its own: `within`,
# `within_include` and `contains` belong to ipam.prefix. On ip-addresses
# `within=<cidr>` is SILENTLY IGNORED (returns every address; verified live
# 2026-10-18: 616 of 616) and `without` is a 400. The address-in-prefix filter
# is `parent=<cidr>`. `prefix=<cidr>` is likewise ignored on ip-addresses
# (verified 2026-10-19: 616 of 616). `vrf=` on ipam objects takes the route
# distinguisher, not the VRF name (400 otherwise); the usable key is `vrf_id`.
_IPADDRESS_PREFIX_ONLY_KEYS: frozenset[str] = frozenset({"within", "within_include", "without", "contains", "prefix"})

# The change-log `action` filter is an enum of bare verbs. The upstream MCP
# server's tool description says "(created, updated, deleted)"; NetBox 4.3
# answers 400 to those (verified live 2026-10-19: action=create -> 3,158,
# action=created -> "Select a valid choice"). Same shape as the `id__in`
# example behind ADR-0041: the tool description is the source of the bad value.
CHANGELOG_ACTION_FIX: dict[str, str] = {"created": "create", "updated": "update", "deleted": "delete"}

# ---------------------------------------------------------------------------
# Schema layers (2026-10-20). NetBox silently drops any query parameter its
# filterset does not define and returns the UNFILTERED set with HTTP 200, so the
# only reliable authority for "does this filter exist on this endpoint" is the
# instance's own OpenAPI document. scripts/build_netbox_filter_index.py vendors
# it as a per-endpoint {name -> {type, multi, enum}} index stamped with the
# NetBox version. Replaying 1,237 recorded benchmark calls against it rejected
# 54 key uses (27 distinct wrong names such as device_role_id, circuit_type_id,
# vlan_group_id, parent_prefix) - every one verified silently ignored live - and
# 0 honoured keys; the enum layer caught all 6 `action=created` 400s. Precedent:
# pynetbox `strict_filters` (7.6.0). The hand rules above stay for value
# semantics the schema cannot express (`__n: null`, `<rel>_id: "null"`, `vrf`
# wanting a route distinguisher, slugs). Fail-open: no index, unknown object
# type or unknown endpoint -> only the hand rules run.
# See docs/development/2026-10-20_openapi-schema-driven-filter-validation.md.
_FILTER_INDEX_PATH = Path(__file__).with_name("netbox_filter_index.json.gz")
_filter_index: dict | None = None
_filter_index_loaded = False

# Keys NetBox honours that are not filterset parameters (view-level or
# instance-time): never rejected by the schema layer.
_SCHEMA_EXEMPT_KEYS: frozenset[str] = frozenset({"fields", "brief", "export", "format", "limit", "offset", "ordering", "q"})


def load_filter_index() -> dict | None:
    """Vendored OpenAPI filter index, or None when absent/unreadable (fail-open)."""
    global _filter_index, _filter_index_loaded
    if not _filter_index_loaded:
        _filter_index_loaded = True
        try:
            _filter_index = json.loads(gzip.decompress(_FILTER_INDEX_PATH.read_bytes()))
        except (OSError, ValueError) as e:  # missing file or corrupt gzip/json
            logger.warning("NetBox filter index unavailable; schema layer disabled", error=str(e))
            _filter_index = None
    return _filter_index


def index_version_warning(live_version: str | None) -> str | None:
    """Return a warning when the vendored index was built from a different
    NetBox version than the one running (lookup sets change between releases:
    regex lookups arrive in 4.3.5). None when they match or either is unknown."""
    idx = load_filter_index()
    if not idx or not live_version:
        return None
    stamped = str(idx.get("netbox_version", "")).split(" ")[0].split("-")[0]
    live = str(live_version).split(" ")[0].split("-")[0]
    if stamped and live and stamped != live:
        return (
            f"NetBox filter index was built from {stamped} but the instance runs {live}; "
            f"re-run scripts/build_netbox_filter_index.py (schema layer stays on, fail-open)"
        )
    return None


def endpoint_params(object_type: str | None) -> dict[str, dict] | None:
    """{param name -> entry} for the object type's list endpoint, or None."""
    idx = load_filter_index()
    if not idx or not object_type:
        return None
    path = idx.get("object_types", {}).get(object_type)
    return idx.get("endpoints", {}).get(path) if path else None


# Wrong names the replay recorded whose fix is not a plain prefix strip.
_FILTER_ALIASES: dict[str, str] = {
    "parent_prefix": "parent",
    "assigned_object_id": "object_id",
    "assigned_object_type": "object_type",
    "assigned_object_type_id": "object_type_id",
    "devicetype_id": "device_type_id",
    "ip_address_id": "address",
}


def _schema_suggestion(key: str, params: dict[str, dict], value: Any = None) -> str:
    """Name the filter the model probably meant. Order: structural rewrites
    (verified on the replay: 20 of 27 wrong names), then difflib with a guard
    against suggesting the `__n` negation for an `__in`/`__empty` family input
    (difflib's top hit for `site_id__in` is `site_id__n`, a harmful hint), then
    the endpoint's relation filters."""
    base, _, suffix = key.partition("__")
    fam = suffix in ("in", "empty", "null", "isnull", "none")
    if suffix == "in" and base in params:
        return (
            f"'__in' is silently ignored by NetBox. Pass a list as the value of the bare key: "
            f"filters={{'{base}': [<v1>, <v2>, ...]}}"
        )
    if fam and (base.endswith("_id") or f"{base}_id" in params):
        rel = base[:-3] if base.endswith("_id") else base
        return f"For objects with no {rel} assigned use filters={{'{rel}_id': 'null'}}"
    alias = _FILTER_ALIASES.get(base)
    if alias and alias in params:
        return f"'{key}' is not a filter here; the filter is '{alias}' (same value)."
    # a leading model prefix on a real filter: device_role_id / devicerole_id ->
    # role_id, circuit_type_id -> type_id, vlan_group_id -> group_id. Longest
    # real parameter that the key ends with, with an alphabetic remainder.
    best = ""
    for p in params:
        if "__" in p or p == "id" or len(p) < 3 or not base.endswith(p) or len(p) <= len(best):
            continue
        rest = base[: -len(p)].rstrip("_")
        if rest and rest.replace("_", "").isalpha():
            best = p
    if best:
        return f"'{key}' is not a filter here; the filter is '{best}' (same value)."
    if base.endswith("_id") and base[:-3] in params:
        return f"'{key}' is not a filter here; use '{base[:-3]}' (it takes the id or slug)."
    names = [n for n in params if not (fam and n.endswith("__n"))]
    close = difflib.get_close_matches(key, names, n=3, cutoff=0.6)
    if close:
        return f"'{key}' is not a filter here. Did you mean: {', '.join(close)}?"
    rels = sorted(n for n in params if n.endswith("_id") and "__" not in n)
    return (
        f"'{key}' is not a filter on this endpoint. Its relation filters are: "
        f"{', '.join(rels[:25])}{' ...' if len(rels) > 25 else ''}. "
        f"If the relation lives on another object, filter that object instead."
    )


def validate_against_schema(filter_dict: dict[str, Any], object_type: str | None) -> tuple[bool, str | None]:
    """Layer 1 (key exists on the endpoint) and layer 2 (enum membership).
    Returns (True, None) when the index cannot answer (fail-open)."""
    params = endpoint_params(object_type)
    if params is None:
        return True, None
    for key, value in filter_dict.items():
        if key in _SCHEMA_EXEMPT_KEYS or key.startswith("cf_"):
            continue
        entry = params.get(key)
        if entry is None:
            # the wrapper appends suggest_alternative(key, object_type) as the fix
            return (
                False,
                f"Invalid filter pattern: {key} (not a filter on {object_type}; NetBox "
                f"silently ignores unknown filters and returns the UNFILTERED set)",
            )
        enum = entry.get("e")
        if enum:
            values = value if isinstance(value, list) else [value]
            bad = [v for v in values if v is not None and str(v) not in enum]
            if bad:
                return (
                    False,
                    f"Invalid filter pattern: {key} ('{bad[0]}' is not one of the values "
                    f"NetBox accepts for {key}; use one of: {', '.join(enum)})",
                )
    return True, None


def normalise_filter_values(filters: dict[str, Any]) -> dict[str, Any]:
    """Make filter values survive the wire. `requests` DROPS parameters whose
    value is None (netbox-mcp-server/netbox_client.py builds `params=` straight
    from this dict), so `{"tenant_id": None}` reached NetBox as no filter at all
    and returned every device (141) - verified live 2026-10-20; the string
    "null" returns the 15 devices without a tenant. Booleans likewise must be
    the strings NetBox's filtersets parse ("true"/"false"; Python's "True" is
    silently ignored on boolean filters). Lists are normalised element-wise."""
    def one(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        return v
    out: dict[str, Any] = {}
    for k, v in (filters or {}).items():
        out[k] = [one(x) for x in v] if isinstance(v, list) else one(v)
    return out


class FilterValidator:
    """Validates NetBox filters before sending to MCP server.

    Mirrors the MCP server's own validate_filters() at server.py:117 — rejects
    multi-hop relationship traversals (any chain of `__field__field`) and
    double-underscore suffixes not on the VALID_SUFFIXES whitelist — and is
    stricter in one place: `__in` is rejected because NetBox ignores it (see
    the VALID_SUFFIXES comment above).
    """

    @staticmethod
    def validate_filter(
        filter_dict: dict[str, Any], object_type: str | None = None
    ) -> tuple[bool, str | None]:
        """
        Validate a filter dictionary for MCP compatibility.

        Args:
            filter_dict: Filter parameters to validate
            object_type: The NetBox object type being queried (e.g. "ipam.ipaddress"),
                when known. Enables the per-type rules; omit for the
                type-independent rules only.

        Returns:
            Tuple of (is_valid, error_message)
        """
        for key, value in filter_dict.items():
            if "__" not in key:
                # bare key (e.g. site_id, name, status) is allowed, except the
                # ip-address containment keys NetBox ignores or rejects
                if object_type == "ipam.ipaddress" and key in _IPADDRESS_PREFIX_ONLY_KEYS:
                    return (
                        False,
                        f"Invalid filter pattern: {key} (on ipam.ipaddress '{key}' is "
                        f"ignored or rejected - it is a prefix filter; addresses inside "
                        f"a CIDR are filtered with 'parent': {{'parent': '<cidr>'}})",
                    )
                if key == "action" and str(value).lower() in CHANGELOG_ACTION_FIX:
                    fix = CHANGELOG_ACTION_FIX[str(value).lower()]
                    return (
                        False,
                        f"Invalid filter pattern: action ('{value}' is not a change-log "
                        f"action; NetBox uses the bare verbs create / update / delete - "
                        f"use {{'action': '{fix}'}})",
                    )
                if key == "vrf" and (object_type or "").startswith("ipam."):
                    return (
                        False,
                        "Invalid filter pattern: vrf (the 'vrf' filter takes the route "
                        "distinguisher and returns HTTP 400 for a VRF name; use "
                        "'vrf_id' with the VRF's numeric id, or 'vrf_id': null for "
                        "addresses in the global table)",
                    )
                continue

            parts = key.split("__")
            if len(parts) != 2:
                return (
                    False,
                    f"Invalid filter pattern: {key} (multi-hop relationship "
                    f"traversal not supported — use a two-step query instead)",
                )

            field, suffix = parts[0], parts[1]
            if suffix not in VALID_SUFFIXES:
                return (
                    False,
                    f"Invalid filter pattern: {key} (suffix '__{suffix}' is not "
                    f"on the MCP server's whitelist; allowed: "
                    f"{', '.join(sorted(VALID_SUFFIXES))})",
                )

            # "no <relation> assigned": only `<relation>_id: null` works.
            base = field[:-3] if field.endswith("_id") else field
            is_relation = base in RELATION_FIELDS or field.endswith("_id")
            if suffix == "empty" and is_relation:
                return (
                    False,
                    f"Invalid filter pattern: {key} ('__empty' is silently ignored on "
                    f"relation fields - NetBox returns the UNFILTERED set; for objects "
                    f"with no {base} use {{'{base}_id': null}})",
                )
            if suffix == "n" and is_relation and (value is None or str(value).lower() in ("null", "none")):
                return (
                    False,
                    f"Invalid filter pattern: {key} with value null ('{key}': null "
                    f"returns the objects that HAVE a {base} - the opposite of what "
                    f"was asked; for objects with no {base} use {{'{base}_id': null}})",
                )

        # Schema layers: does each remaining key exist on this endpoint, and are
        # enum values valid. Fail-open when the index or object type is unknown.
        return validate_against_schema(filter_dict, object_type)

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
    def suggest_alternative(invalid_filter: str, object_type: str | None = None) -> str:
        """Suggest an alternative for a filter rejected by validate_filter.

        With the allow-list-based validator, only two rejection paths reach
        here: multi-hop traversals (>2 `__`-separated parts) and unknown
        suffixes (not on VALID_SUFFIXES). Most unknown suffixes that the
        model is likely to try are Django ORM lookup names with short MCP
        equivalents — translate those directly.
        """
        params = endpoint_params(object_type)
        if params is not None and invalid_filter not in params and invalid_filter not in _IPADDRESS_PREFIX_ONLY_KEYS and invalid_filter not in ("vrf", "action"):
            return _schema_suggestion(invalid_filter, params)
        if "__" not in invalid_filter:
            if invalid_filter in _IPADDRESS_PREFIX_ONLY_KEYS:
                return (
                    "On ipam.ipaddress use filters={'parent': '<cidr>'} for addresses "
                    "inside a prefix ('within'/'within_include'/'contains' are "
                    "ipam.prefix filters and are ignored or rejected here)."
                )
            if invalid_filter == "action":
                return (
                    "Change-log actions are the bare verbs: filters={'action': 'create'} / "
                    "'update' / 'delete' (not 'created' / 'updated' / 'deleted')."
                )
            if invalid_filter == "vrf":
                return (
                    "Use filters={'vrf_id': <id>} (resolve the VRF by name on ipam.vrf "
                    "first), or filters={'vrf_id': null} for the global table."
                )
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
        base = field[:-3] if field.endswith("_id") else field
        is_relation = base in RELATION_FIELDS or field.endswith("_id")
        if suffix in ("regex", "iregex"):
            return (
                f"'__{suffix}' is silently ignored on NetBox 4.3.3 (returns the UNFILTERED "
                f"set; regex lookups arrive in 4.3.5). Use the anchored lookups instead: "
                f"filters={{'{field}__isw': '<prefix>'}} / '__iew' / '__ic'."
            )
        if suffix in ("null", "isnull", "none", "empty") and is_relation:
            return (
                f"To select objects with NO {base} assigned, filter the bare id key "
                f"with null: filters={{'{base}_id': null}}. '__empty' and '__isnull' are "
                f"silently ignored on relation fields (NetBox returns the unfiltered set)."
            )
        if suffix == "n" and is_relation:
            return (
                f"'{field}__n': null returns the objects that HAVE a {base}. For objects "
                f"with no {base} use filters={{'{base}_id': null}}; to exclude one "
                f"specific {base} use filters={{'{base}_id__n': <id>}}."
            )

        if suffix == "in":
            return (
                f"'__in' is silently ignored by NetBox (it returns the UNFILTERED "
                f"set, not an error). To match several values, pass a list as the "
                f"value of the bare key: filters={{'{field}': [<v1>, <v2>, ...]}} "
                f"— NetBox repeats the query parameter (?{field}=v1&{field}=v2)."
            )

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
        await self._check_index_version()
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

    async def _check_index_version(self) -> None:
        """Compare the vendored filter index's NetBox version with /api/status/
        once per agent start. Logs a warning on mismatch; never raises."""
        import os
        url = os.environ.get("NETBOX_URL")
        token = os.environ.get("NETBOX_TOKEN")
        if not url or load_filter_index() is None:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    url.rstrip("/") + "/api/status/",
                    headers={"Authorization": f"Token {token}"} if token else {},
                )
            live = resp.json().get("netbox-version") if resp.status_code == 200 else None
        except Exception as e:  # noqa: BLE001 - diagnostics only
            logger.debug("NetBox /api/status/ not reachable for index version check", error=str(e))
            return
        warning = index_version_warning(live)
        if warning:
            logger.warning(warning)
        else:
            logger.info("NetBox filter index matches the running instance", version=live)

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

            # netbox_get_changelogs: `action` may arrive as a direct argument
            if "action" in kwargs and str(kwargs["action"]).lower() in CHANGELOG_ACTION_FIX:
                fix = CHANGELOG_ACTION_FIX[str(kwargs["action"]).lower()]
                logger.warning(
                    "Invalid change-log action - returning structured error to model",
                    tool=tool.name, action=kwargs["action"],
                )
                return (
                    f"TOOL_VALIDATION_ERROR: action '{kwargs['action']}' is not a change-log "
                    f"action; NetBox uses the bare verbs create / update / delete.\n"
                    f"Suggestion: reissue with action='{fix}'."
                )

            # Check if this tool uses filters
            if "filters" in kwargs or "filter" in kwargs:
                filter_param = kwargs.get("filters") or kwargs.get("filter") or {}
                object_type = kwargs.get("object_type")

                # Find the first invalid key (validate_filter returns on the first failure)
                is_valid, error_msg = self.validator.validate_filter(filter_param, object_type)

                if not is_valid:
                    # Identify which key failed so the suggestion is targeted at it
                    invalid_key = next(
                        (k for k in filter_param if not self.validator.validate_filter({k: filter_param[k]}, object_type)[0]),
                        next(iter(filter_param), ""),
                    )
                    suggestion = self.validator.suggest_alternative(invalid_key, object_type)

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

            # Normalise values that would otherwise be dropped or ignored on the wire
            for fkey in ("filters", "filter"):
                if isinstance(kwargs.get(fkey), dict):
                    kwargs[fkey] = normalise_filter_values(kwargs[fkey])

            # If validation passes, call the original function
            try:
                result = await original_func(*args, **kwargs)
                logger.debug(f"Tool {tool.name} executed successfully", kwargs=kwargs)
                return result
            except ToolException as e:
                # MCP-layer ToolException (typically a NetBox API 400/404/500
                # wrapped by langchain_mcp_adapters). Convert to a structured
                # error STRING so langgraph threads it back as a ToolMessage —
                # the model sees the error on its next turn and can retry with
                # a corrected call. Without this, the ToolException propagates
                # up and crashes the entire agent run (observed in traces
                # 019df9d8, 019e638c, 019e63d4).
                error_msg = str(e)
                logger.warning(
                    "Tool returned ToolException — converting to structured error",
                    tool=tool.name,
                    error=error_msg,
                    kwargs=kwargs,
                )
                return (
                    f"TOOL_API_ERROR: {error_msg}\n"
                    f"The NetBox API or MCP server rejected this call. Re-examine "
                    f"the filter parameters and reissue with a corrected shape. "
                    f"Common causes (consult the netbox-mcp-filters skill):\n"
                    f"  - GenericForeignKey ID fields (assigned_object_id, scope_id, "
                    f"object_id) are SCALAR — a list value fails on these. Use the "
                    f"typed alias filter instead (e.g. `interface_id` for IPs on "
                    f"interfaces, `site_id` for prefixes on sites).\n"
                    f"  - Display names used where slugs/IDs are required "
                    f"(e.g. `site='DM-Akron'` should be `site='dm-akron'` or "
                    f"`site_id=2`).\n"
                    f"  - Lowercase slugs required for status/role values "
                    f"(`active` not `Active`).\n"
                    f"  - Or use a parent-object aggregate field "
                    f"(e.g. `count_ipaddresses` on `dcim.interface`) to avoid "
                    f"the failing query entirely."
                )
            except Exception as e:
                logger.error(f"Tool {tool.name} failed unexpectedly", error=str(e), kwargs=kwargs)
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
