"""Tests for MCP filter constraint handling and recovery."""

import json

import pytest

from src.middleware.filter_recovery import FilterErrorRecoveryMiddleware
from src.tools.netbox_tools import FilterValidator, NetBoxQueryHelper
from src.utils.config import QueryMetrics


class TestFilterValidator:
    """Test filter validation logic."""

    def test_valid_filters(self, valid_filters):
        """Test that valid filters pass validation."""
        validator = FilterValidator()

        for filter_dict in valid_filters:
            is_valid, error = validator.validate_filter(filter_dict)
            assert is_valid is True, f"Filter {filter_dict} should be valid"
            assert error is None

    def test_invalid_filters(self, invalid_filters):
        """Test that invalid filters are caught."""
        validator = FilterValidator()

        for filter_dict in invalid_filters:
            is_valid, error = validator.validate_filter(filter_dict)
            assert is_valid is False, f"Filter {filter_dict} should be invalid"
            assert error is not None
            assert "Invalid filter pattern" in error or "unsupported" in error

    def test_multi_hop_filter_detection(self):
        """Test detection of multi-hop filters."""
        validator = FilterValidator()

        multi_hop_filters = [
            {"device__site__name": "NYC"},
            {"interface__device__rack_id": 5},
            {"cable__termination_a__device_id": 10},
        ]

        for filter_dict in multi_hop_filters:
            is_valid, error = validator.validate_filter(filter_dict)
            assert is_valid is False
            assert "relationship traversal" in error

    def test_django_lookup_detection(self):
        """Test detection of Django ORM lookups that lack a valid MCP equivalent.

        Note: Django spellings like `__icontains` are NOT on the MCP server's
        whitelist (which uses short forms like `__ic`). But `__gte` etc. ARE on
        the whitelist and must NOT be rejected (`__regex`/`__iregex` were dropped on
        2026-10-20: silently ignored on NetBox 4.3.3). `__in` is the one
        suffix the MCP server lists that this validator rejects: NetBox 4.3
        silently ignores it and returns the unfiltered set (verified live,
        2026-10-06), so the list-form bare key is the only multi-value form.
        """
        validator = FilterValidator()

        # Django-form lookups with case-insensitive short-form equivalents — all rejected
        rejected_django_forms = [
            {"name__icontains": "server"},
            {"name__contains": "server"},
            {"name__startswith": "core-"},
            {"name__endswith": "-01"},
            {"name__iexact": "Router01"},
        ]
        for filter_dict in rejected_django_forms:
            is_valid, error = validator.validate_filter(filter_dict)
            assert is_valid is False, f"{filter_dict} should be rejected"
            assert "not on the MCP server's whitelist" in error or "not supported" in error

        # `__in` is rejected with a hint pointing at the list form, because
        # NetBox drops the filter silently instead of returning 400.
        is_valid, error = validator.validate_filter({"device_id__in": [149, 150]})
        assert is_valid is False
        assert "__in" in error
        hint = validator.suggest_alternative("device_id__in")
        assert "silently ignored" in hint
        assert "{'device_id': [" in hint

        # These ARE on the MCP server's VALID_SUFFIXES whitelist — must pass
        accepted_lookups = [
            {"device_id": [149, 150]},        # list form IS the multi-value syntax
            {"created__gte": "2024-01-01"},
            {"created__gt": "2024-01-01"},
            {"vid__lt": 100},
            {"vid__lte": 100},
            {"name__ic": "switch"},
            {"name__n": "decom"},
        ]
        for filter_dict in accepted_lookups:
            is_valid, error = validator.validate_filter(filter_dict)
            assert is_valid is True, f"{filter_dict} should be accepted (was rejected: {error})"

    def test_suggest_alternative_for_icontains(self):
        """Test alternative suggestion for the Django `__icontains` form.

        The validator now translates Django forms to their MCP short-form
        equivalents directly (icontains -> ic), rather than redirecting to
        netbox_search_objects.
        """
        validator = FilterValidator()

        suggestion = validator.suggest_alternative("name__icontains")
        # The new suggestion points to the MCP short form, not search
        assert "__ic" in suggestion
        assert "filters={'name__ic'" in suggestion

    def test_suggest_alternative_for_relationship(self):
        """Test alternative suggestions for multi-hop relationship traversals."""
        validator = FilterValidator()

        suggestion = validator.suggest_alternative("device__site_id__name")
        assert "two-step query" in suggestion.lower()
        assert "device_id" in suggestion


class TestFilterErrorRecoveryMiddleware:
    """Test filter error recovery middleware."""

    def test_multi_hop_filter_recovery(self):
        """Multi-hop filters are caught and corrected."""
        middleware = FilterErrorRecoveryMiddleware()

        state = {"error": "Invalid filter: device__site_id"}
        result = middleware.after_model(state)

        assert result is not None
        assert "recovery_strategy" in result
        assert result["recovery_strategy"]["approach"] == "two_step_query"
        assert len(result["recovery_strategy"]["steps"]) == 2
        assert "Get device by name" in result["recovery_strategy"]["steps"][0]["description"]

    def test_django_lookup_recovery(self):
        """Django lookups trigger recovery."""
        middleware = FilterErrorRecoveryMiddleware()

        state = {"error": "Invalid filter: name__icontains"}
        result = middleware.after_model(state)

        assert result is not None
        assert result["recovery_strategy"]["approach"] == "use_search"
        assert "netbox_search_objects" in result["recovery_strategy"]["steps"][0]["example"]

    def test_no_recovery_for_valid_state(self):
        """No recovery attempted when no error present."""
        middleware = FilterErrorRecoveryMiddleware()

        state = {"messages": [], "error": None}
        result = middleware.after_model(state)

        assert result is None

    def test_recovery_attempt_tracking(self, query_metrics):
        """Test that recovery attempts are tracked."""
        middleware = FilterErrorRecoveryMiddleware(metrics=query_metrics)

        # First attempt
        state = {"error": "Invalid filter: device__site_id"}
        result1 = middleware.after_model(state)
        assert result1 is not None
        assert query_metrics.filter_errors == 1
        assert query_metrics.recovered_errors == 1

        # Second attempt (same error)
        result2 = middleware.after_model(state)
        assert result2 is not None
        assert query_metrics.filter_errors == 2
        assert query_metrics.recovered_errors == 2

        # Third attempt should be blocked (max 2 attempts)
        result3 = middleware.after_model(state)
        assert result3 is None
        assert query_metrics.filter_errors == 3
        assert query_metrics.recovered_errors == 2  # No additional recovery

    def test_error_pattern_extraction(self):
        """Test extraction of filter patterns from error messages."""
        middleware = FilterErrorRecoveryMiddleware()

        test_cases = [
            ("Invalid filter: device__site_id", "device__site_id"),
            ("MCP Filter Error: termination_a__device_id not supported", "termination_a__device_id"),
            ("Filter name__icontains is invalid", "name__icontains"),
        ]

        for error_msg, expected_filter in test_cases:
            extracted = middleware._extract_filter(error_msg)
            assert extracted == expected_filter

    def test_recovery_strategy_generation(self):
        """Test generation of recovery strategies."""
        middleware = FilterErrorRecoveryMiddleware()

        # Test multi-hop recovery
        strategy = middleware._generate_recovery_strategy(
            "multi_hop_filter", "device__site_id", "Invalid filter: device__site_id"
        )
        assert strategy["approach"] == "two_step_query"
        assert len(strategy["steps"]) == 2
        assert "tips" in strategy

        # Test Django lookup recovery
        strategy = middleware._generate_recovery_strategy(
            "django_lookup", "name__icontains", "Invalid filter: name__icontains"
        )
        assert strategy["approach"] == "use_search"
        assert len(strategy["steps"]) == 1


class TestNetBoxQueryHelper:
    """Test query helper utilities."""

    def test_create_two_step_filter(self):
        """Test creation of two-step query plans."""
        helper = NetBoxQueryHelper()

        steps = helper.create_two_step_filter("device", "router01", "dcim.interface")

        assert len(steps) == 2
        assert steps[0]["tool"] == "netbox_get_objects"
        assert steps[0]["params"]["filters"] == {"name": "router01"}
        assert steps[1]["params"]["filters"] == {"device_id": "{{previous_result.id}}"}

    def test_use_search_instead(self):
        """Test search query generation."""
        helper = NetBoxQueryHelper()

        search_query = helper.use_search_instead(
            "Dunder-Mifflin", ["dcim.site", "dcim.device"]
        )

        assert search_query["tool"] == "netbox_search_objects"
        assert search_query["params"]["query"] == "Dunder-Mifflin"
        assert search_query["params"]["object_types"] == ["dcim.site", "dcim.device"]


@pytest.mark.asyncio
async def test_filter_recovery_integration(query_metrics):
    """Integration test for filter recovery flow."""
    middleware = FilterErrorRecoveryMiddleware(metrics=query_metrics)

    # Simulate a series of queries with filter errors
    error_states = [
        {"error": "Invalid filter: device__site_id"},
        {"error": "Invalid filter: name__icontains=server"},
        {"error": "MCP Filter Error: termination_a__device_id"},
    ]

    for state in error_states:
        result = middleware.after_model(state)
        assert result is not None
        assert "recovery_strategy" in result
        assert result["recovery_strategy"]["steps"]

    # Verify metrics
    assert query_metrics.filter_errors == 3
    assert query_metrics.recovered_errors == 3
    assert query_metrics.recovery_rate == 100.0

class TestNullRelationAndContainmentFilters:
    """Filters NetBox silently ignores or inverts (verified live 2026-10-18, see
    docs/development/2026-10-18_filter-naming-after-in.md): the only form for
    "no <relation> assigned" is `<relation>_id: null`; on ipam.ipaddress the
    prefix containment keys are ignored/rejected and `vrf` wants an RD."""

    def test_relation_empty_rejected(self):
        validator = FilterValidator()
        for key in ("tenant__empty", "site__empty", "role_id__empty", "primary_ip4__empty"):
            is_valid, error = validator.validate_filter({key: "true"})
            assert is_valid is False, key
            assert "silently ignored" in error and "_id': null" in error

    def test_string_empty_still_valid(self):
        validator = FilterValidator()
        assert validator.validate_filter({"serial__empty": "true"})[0] is True
        assert validator.validate_filter({"description__empty": "true"})[0] is True

    def test_relation_negated_null_rejected(self):
        validator = FilterValidator()
        for value in (None, "null", "None"):
            is_valid, error = validator.validate_filter({"tenant__n": value})
            assert is_valid is False
            assert "HAVE a tenant" in error and "'tenant_id': null" in error
        # ordinary negation of a specific id is still fine
        assert validator.validate_filter({"role_id__n": 4})[0] is True

    def test_null_id_filter_is_the_valid_form(self):
        validator = FilterValidator()
        assert validator.validate_filter({"tenant_id": None})[0] is True
        assert validator.validate_filter({"vrf_id": None}, "ipam.ipaddress")[0] is True

    def test_suggestions_name_the_null_id_form(self):
        validator = FilterValidator()
        for key in ("tenant__null", "tenant__isnull", "tenant__empty", "site_id__empty"):
            assert "_id': null" in validator.suggest_alternative(key), key
        assert "'tenant_id': null" in validator.suggest_alternative("tenant__n")

    def test_ipaddress_containment_keys_rejected_only_there(self):
        validator = FilterValidator()
        for key in ("within", "within_include", "without", "contains", "prefix"):
            is_valid, error = validator.validate_filter({key: "10.0.0.0/8"}, "ipam.ipaddress")
            assert is_valid is False, key
            assert "parent" in error
            assert validator.validate_filter({key: "10.0.0.0/8"})[0] is True  # type unknown: hand rules only
        for key in ("within", "within_include", "contains"):  # real prefix filters, schema-listed
            assert validator.validate_filter({key: "10.0.0.0/8"}, "ipam.prefix")[0] is True
        assert validator.validate_filter({"without": "10.0.0.0/8"}, "ipam.prefix")[0] is False  # no such NetBox filter
        assert validator.validate_filter({"parent": "10.0.0.0/8"}, "ipam.ipaddress")[0] is True
        assert "parent" in validator.suggest_alternative("within")

    def test_vrf_name_filter_rejected_on_ipam(self):
        validator = FilterValidator()
        is_valid, error = validator.validate_filter({"vrf": "hvl-guest"}, "ipam.ipaddress")
        assert is_valid is False and "vrf_id" in error
        assert validator.validate_filter({"vrf": "65000:1"})[0] is True  # no object type: ipam-only hand rule does not apply
        assert "vrf_id" in validator.suggest_alternative("vrf")


class TestNullRelationRecovery:
    def test_null_relation_strategy(self):
        mw = FilterErrorRecoveryMiddleware()
        msg = ("TOOL_VALIDATION_ERROR: Invalid filter pattern: tenant__empty ('__empty' is "
               "silently ignored on relation fields - NetBox returns the UNFILTERED set; "
               "for objects with no tenant use {'tenant_id': null})")
        assert mw._detect_error_type(msg) == "null_relation"
        strategy = mw._generate_recovery_strategy("null_relation", "tenant__empty", msg)
        assert strategy["approach"] == "null_id_filter"
        assert '"tenant_id": null' in strategy["steps"][0]["example"]

    def test_negated_null_is_null_relation(self):
        mw = FilterErrorRecoveryMiddleware()
        msg = "Invalid filter pattern: tenant__n with value null ('tenant__n': null returns ...)"
        assert mw._detect_error_type(msg) == "null_relation"

    def test_ip_parent_strategy(self):
        mw = FilterErrorRecoveryMiddleware()
        msg = ("TOOL_VALIDATION_ERROR: Invalid filter pattern: within (on ipam.ipaddress "
               "'within' is ignored or rejected - it is a prefix filter; ...)")
        assert mw._detect_error_type(msg) == "ip_parent_filter"
        assert mw._extract_filter(msg) == "within"
        strategy = mw._generate_recovery_strategy("ip_parent_filter", "within", msg)
        assert strategy["approach"] == "parent_filter"


class TestChangelogAction:
    """NetBox's change-log `action` filter takes create / update / delete; the
    MCP server description taught the past-tense forms (400 on NetBox 4.3.3)."""

    def test_past_tense_rejected_with_verb(self):
        validator = FilterValidator()
        for bad, good in (("created", "create"), ("updated", "update"), ("deleted", "delete")):
            is_valid, error = validator.validate_filter({"action": bad})
            assert is_valid is False, bad
            assert f"'action': '{good}'" in error
        assert "create" in validator.suggest_alternative("action")

    def test_bare_verbs_valid(self):
        validator = FilterValidator()
        for good in ("create", "update", "delete"):
            assert validator.validate_filter({"action": good})[0] is True

    def test_recovery_strategy(self):
        mw = FilterErrorRecoveryMiddleware()
        msg = ("TOOL_VALIDATION_ERROR: Invalid filter pattern: action ('created' is not a "
               "change-log action; NetBox uses the bare verbs create / update / delete - "
               "use {'action': 'create'})")
        assert mw._detect_error_type(msg) == "changelog_action"
        strategy = mw._generate_recovery_strategy("changelog_action", "action", msg)
        assert strategy["approach"] == "bare_verb_action"


class TestWireNormalisationAndRegex:
    """2026-10-20 (OpenAPI research): JSON null never reached NetBox because
    `requests` drops None params; booleans must be the strings NetBox parses;
    __regex/__iregex are silently ignored on 4.3.3."""

    def test_none_and_bool_become_wire_strings(self):
        from src.tools.netbox_tools import normalise_filter_values
        out = normalise_filter_values({"tenant_id": None, "has_primary_ip": False, "role_id": [1, None], "name": "x", "vid": 100})
        assert out == {"tenant_id": "null", "has_primary_ip": "false", "role_id": [1, "null"], "name": "x", "vid": 100}
        assert normalise_filter_values({}) == {}
        assert normalise_filter_values(None) == {}

    def test_regex_rejected_with_anchored_hint(self):
        validator = FilterValidator()
        for key in ("name__regex", "name__iregex"):
            is_valid, error = validator.validate_filter({key: "^core-"})
            assert is_valid is False, key
            hint = validator.suggest_alternative(key)
            assert "silently ignored" in hint and "__isw" in hint


class TestSchemaLayers:
    """Key existence and enum membership from the vendored OpenAPI index
    (src/tools/netbox_filter_index.json.gz); see
    docs/development/2026-10-20_openapi-schema-driven-filter-validation.md."""

    def test_index_loads_and_resolves_object_types(self):
        from src.tools.netbox_tools import load_filter_index, endpoint_params
        idx = load_filter_index()
        assert idx and idx["netbox_version"].startswith("4.3")
        assert len(idx["endpoints"]) >= 140 and len(idx["object_types"]) >= 120
        assert "role_id" in endpoint_params("dcim.device")
        assert endpoint_params("not.a.type") is None

    def test_unknown_key_rejected_with_rename_suggestion(self):
        validator = FilterValidator()
        for bad, good, ot in (("device_role_id", "role_id", "dcim.device"), ("devicerole_id", "role_id", "dcim.device"),
                              ("device_role", "role", "dcim.device"), ("circuit_type_id", "type_id", "circuits.circuit"),
                              ("vlan_group_id", "group_id", "ipam.vlan"), ("parent_prefix", "parent", "ipam.ipaddress")):
            is_valid, error = validator.validate_filter({bad: 5}, ot)
            assert is_valid is False, bad
            assert "UNFILTERED" in error, (bad, error)
            assert f"'{good}'" in validator.suggest_alternative(bad, ot), (bad, validator.suggest_alternative(bad, ot))

    def test_known_keys_pass(self):
        validator = FilterValidator()
        assert validator.validate_filter({"role_id": 5, "tenant_id": 14, "name__ic": "pdu"}, "dcim.device")[0] is True
        assert validator.validate_filter({"parent": "10.0.0.0/8", "vrf_id": "null"}, "ipam.ipaddress")[0] is True

    def test_enum_values_checked(self):
        validator = FilterValidator()
        is_valid, error = validator.validate_filter({"status": "Active"}, "dcim.device")
        assert is_valid is False and "active" in error and "decommissioning" in error
        assert validator.validate_filter({"status": ["active", "planned"]}, "dcim.device")[0] is True

    def test_exempt_and_fail_open(self):
        validator = FilterValidator()
        assert validator.validate_filter({"cf_cust_id": "x", "fields": "id", "q": "hq"}, "tenancy.tenant")[0] is True
        assert validator.validate_filter({"anything": 1}, "no.such.type")[0] is True  # unknown type: hand rules only
        assert validator.validate_filter({"anything": 1})[0] is True  # no object type

    def test_no_negation_suggested_for_in_family(self):
        from src.tools.netbox_tools import _schema_suggestion, endpoint_params
        params = endpoint_params("dcim.powerfeed")
        for key in ("site_id__in", "site_id__isnull", "tenant__empty"):
            msg = _schema_suggestion(key, params)
            assert "__n" not in msg, (key, msg)


def test_index_version_warning():
    from src.tools.netbox_tools import index_version_warning, load_filter_index
    stamped = load_filter_index()["netbox_version"]
    assert index_version_warning(stamped) is None
    assert index_version_warning("4.3.3-Docker-3.3.0 (4.3)") is None
    assert index_version_warning(None) is None
    w = index_version_warning("4.3.5")
    assert w and "4.3.5" in w and "build_netbox_filter_index" in w


class TestWrapperReturnsContentAndArtifact:
    """The adapter's MCP tools return (content_blocks, artifact). Rebuilding them
    without response_format="content_and_artifact" stringified the whole pair into
    the ToolMessage, so the model read every result twice (2026-10-20)."""

    @pytest.mark.asyncio
    async def test_content_only_reaches_the_message(self):
        from langchain_core.tools import StructuredTool
        from src.tools.netbox_tools import NetBoxToolWrapper

        blocks = [{"type": "text", "text": '{"count": 1, "results": [{"id": 149}]}'}]
        artifact = {"structured_content": {"count": 1}}

        async def fake(object_type: str, filters: dict | None = None, limit: int = 5):
            return blocks, artifact

        raw = StructuredTool.from_function(coroutine=fake, name="netbox_get_objects", description="x",
                                           response_format="content_and_artifact")
        wrapped = NetBoxToolWrapper(mcp_client=None)
        wrapped.totals.seed("/api/dcim/devices/", 141)
        tool = wrapped._wrap_tool_with_validation(raw)
        msg = await tool.ainvoke({"name": "netbox_get_objects", "args": {"object_type": "dcim.device", "filters": {"tenant_id": 14}}, "id": "c1", "type": "tool_call"})
        # the result header is the first block, the adapter's blocks follow unchanged
        assert msg.content[0]["type"] == "text" and msg.content[0]["text"].startswith("NETBOX_RESULT ")
        assert msg.content[1:] == blocks, msg.content          # not a str starting with "[["
        assert msg.artifact == artifact
        # a validation error is still a plain string content, with no artifact
        msg = await tool.ainvoke({"name": "netbox_get_objects", "args": {"object_type": "dcim.device", "filters": {"device_role_id": 5}}, "id": "c2", "type": "tool_call"})
        assert isinstance(msg.content, str) and msg.content.startswith("TOOL_VALIDATION_ERROR")
        assert msg.artifact is None


class TestResultEnvelope:
    """Every list result starts with a header (scope, matched/returned counts,
    complete flag) and a WARNING when a scoped call returned the endpoint's whole
    table - the silently-unfiltered case the schema layer cannot see (2026-11-09)."""

    def _page(self, count, n, next_url=None):
        return {"count": count, "next": next_url, "previous": None, "results": [{"id": i} for i in range(n)]}

    def test_header_line_fields(self):
        from src.tools.netbox_tools import result_header
        h = result_header({"tenant_id": 14}, self._page(12, 12), 141, "dcim.device")
        assert h == 'NETBOX_RESULT scope={"tenant_id":14} matched_count=12 returned_count=12 complete=true'

    def test_incomplete_names_the_next_offset(self):
        from src.tools.netbox_tools import result_header
        h = result_header({}, self._page(14, 5, "http://x/?limit=5&offset=5"), None, "dcim.site")
        assert "complete=false" in h
        assert "INCOMPLETE: 5 of 14 returned" in h and "offset=5" in h
        h = result_header({}, self._page(14, 5, "http://x/?offset=10"), None, "dcim.site", offset=5)
        assert "offset=10" in h

    def test_warning_names_ignored_keys_note_on_coincidence_ambiguous_without_probe(self):
        from src.tools.netbox_tools import result_header
        page = self._page(141, 100, "n")
        h = result_header({"has_primary_ip": "no"}, page, 141, "dcim.device", ignored=["has_primary_ip"])
        assert "WARNING: filter(s) has_primary_ip had NO EFFECT" in h and "all 141" in h and "netbox-mcp-filters" in h
        h = result_header({"device_type_id": 8}, self._page(8, 8), 8, "dcim.poweroutlettemplate", ignored=[])
        assert "WARNING" not in h and "NOTE: the filters are honoured and happen to match every dcim.poweroutlettemplate (8 of 8)" in h
        h = result_header({"has_primary_ip": "no"}, page, 141, "dcim.device", ignored=None)
        assert "WARNING: the filters had no effect or coincide with the whole table" in h

    def test_no_warning_without_scope_or_below_total_or_empty(self):
        from src.tools.netbox_tools import result_header
        assert "WARNING" not in result_header({}, self._page(141, 100, "n"), 141, "dcim.device")
        assert "WARNING" not in result_header({"tenant_id": 14}, self._page(12, 12), 141, "dcim.device")
        assert "WARNING" not in result_header({"tenant_id": 99}, self._page(0, 0), 141, "dcim.device")
        # unknown total (probe failed, endpoint unknown): fail-open, counts still present
        h = result_header({"tenant_id": 14}, self._page(141, 100, "n"), None, "dcim.device")
        assert "WARNING" not in h and "matched_count=141" in h

    def test_scope_excludes_view_level_keys(self):
        from src.tools.netbox_tools import scope_filters
        assert scope_filters({"filters": {"limit": 100, "fields": ["id"], "q": "x", "site_id": 3}}) == {"site_id": 3}
        assert scope_filters({"filters": None}) == {} and scope_filters({}) == {}

    def test_list_payload_prefers_artifact_and_fails_open(self):
        from src.tools.netbox_tools import list_payload
        page = self._page(1, 1)
        assert list_payload([{"type": "text", "text": "garbage"}], {"structured_content": page}) == page
        assert list_payload([{"type": "text", "text": '{"count": 2, "results": []}'}], None) == {"count": 2, "results": []}
        assert list_payload([{"type": "text", "text": '{"dcim.site": []}'}], {"structured_content": {"dcim.site": []}}) is None
        assert list_payload("not json", None) is None

    def test_list_endpoint_from_index_and_changelogs(self):
        from src.tools.netbox_tools import list_endpoint
        assert list_endpoint("netbox_get_objects", {"object_type": "dcim.device"}) == "/api/dcim/devices/"
        assert list_endpoint("netbox_get_objects", {"object_type": "nope.nope"}) is None
        assert list_endpoint("netbox_get_changelogs", {"filters": {"user_id": 9}}) == "/api/core/object-changes/"

    @pytest.mark.asyncio
    async def test_totals_cache_seeded_and_ttl(self):
        from src.tools.netbox_tools import UnfilteredTotals
        t = UnfilteredTotals(ttl_s=3600)
        t.seed("/api/dcim/devices/", 141)
        assert await t.get("/api/dcim/devices/") == 141
        calls = []

        async def fake(endpoint):
            calls.append(endpoint)
            return 7
        t._fetch = fake  # type: ignore[method-assign]
        assert await t.get("/api/ipam/vlans/") == 7 and await t.get("/api/ipam/vlans/") == 7
        assert calls == ["/api/ipam/vlans/"]          # second call served from cache
        t.ttl_s = 0
        assert await t.get("/api/ipam/vlans/") == 7 and len(calls) == 2   # expired -> refetched

    @pytest.mark.asyncio
    async def test_ignored_keys_probe_verdicts(self):
        from src.tools.netbox_tools import UnfilteredTotals
        t = UnfilteredTotals(ttl_s=3600)
        probes = []

        async def fake_get(endpoint, filters):
            probes.append((endpoint, filters))
            key = next(iter(filters))
            return {"has_primary_ip": (200, 141),       # ignored: impossible value, unchanged total
                    "role_id": (400, None),              # honoured: NetBox rejects the impossible id
                    "device_type_id": (200, 0),          # honoured: impossible id matches nothing
                    "broken": (None, None)}[key]         # probe failed
        t._get = fake_get  # type: ignore[method-assign]
        ep = "/api/dcim/devices/"
        assert await t.ignored_keys(ep, {"has_primary_ip": "no", "role_id": 5}, 141) == ["has_primary_ip"]
        assert await t.ignored_keys(ep, {"device_type_id": [8, 9]}, 141) == []
        assert probes[-1] == (ep, {"device_type_id": [999999999]})          # list keeps list shape
        assert probes[0] == (ep, {"has_primary_ip": "zz-no-such-value-zz"})  # string value -> string nonsense
        assert await t.ignored_keys(ep, {"broken": 1}, 141) is None
        n = len(probes)
        assert await t.ignored_keys(ep, {"has_primary_ip": "false"}, 141) == ["has_primary_ip"] and len(probes) == n  # cached

    @pytest.mark.asyncio
    async def test_wrapper_warns_only_on_list_tools_with_whole_table(self):
        from langchain_core.tools import StructuredTool
        from src.tools.netbox_tools import NetBoxToolWrapper

        page = self._page(141, 100, "http://x/?offset=100")

        async def devices(object_type: str, filters: dict | None = None, limit: int = 5):
            return [{"type": "text", "text": json.dumps(page)}], {"structured_content": page}

        async def search(query: str, object_types: list | None = None):
            return [{"type": "text", "text": '{"dcim.site": []}'}], {"structured_content": {"dcim.site": []}}

        w = NetBoxToolWrapper(mcp_client=None)
        w.totals.seed("/api/dcim/devices/", 141)

        async def fake_get(endpoint, filters):
            return (200, 141)                      # every probe: unchanged total -> ignored
        w.totals._get = fake_get  # type: ignore[method-assign]
        get = w._wrap_tool_with_validation(StructuredTool.from_function(
            coroutine=devices, name="netbox_get_objects", description="x", response_format="content_and_artifact"))
        find = w._wrap_tool_with_validation(StructuredTool.from_function(
            coroutine=search, name="netbox_search_objects", description="x", response_format="content_and_artifact"))

        msg = await get.ainvoke({"name": "netbox_get_objects", "args": {"object_type": "dcim.device", "filters": {"has_primary_ip": "no"}, "limit": 100}, "id": "c1", "type": "tool_call"})
        head = msg.content[0]["text"]
        assert head.startswith('NETBOX_RESULT scope={"has_primary_ip":"no"} matched_count=141 returned_count=100 complete=false')
        assert "INCOMPLETE: 100 of 141" in head and "WARNING: filter(s) has_primary_ip had NO EFFECT" in head
        assert msg.artifact == {"structured_content": page}
        # same payload, no scope: counts only, no warning
        msg = await get.ainvoke({"name": "netbox_get_objects", "args": {"object_type": "dcim.device", "limit": 100}, "id": "c2", "type": "tool_call"})
        assert "WARNING" not in msg.content[0]["text"] and "matched_count=141" in msg.content[0]["text"]
        # the search tool has no paginated payload: untouched
        msg = await find.ainvoke({"name": "netbox_search_objects", "args": {"query": "hvl"}, "id": "c3", "type": "tool_call"})
        assert msg.content == [{"type": "text", "text": '{"dcim.site": []}'}]
