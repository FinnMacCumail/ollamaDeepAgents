"""Tests for MCP filter constraint handling and recovery."""

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
        whitelist (which uses short forms like `__ic`). But `__gte`, `__regex`
        etc. ARE on the whitelist and must NOT be rejected. `__in` is the one
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
            {"status__regex": ".*active.*"},
            {"name__iregex": "^router-.*"},
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
        for key in ("within", "within_include", "without", "contains"):
            is_valid, error = validator.validate_filter({key: "10.0.0.0/8"}, "ipam.ipaddress")
            assert is_valid is False, key
            assert "parent" in error
            assert validator.validate_filter({key: "10.0.0.0/8"}, "ipam.prefix")[0] is True
            assert validator.validate_filter({key: "10.0.0.0/8"})[0] is True  # type unknown
        assert validator.validate_filter({"parent": "10.0.0.0/8"}, "ipam.ipaddress")[0] is True
        assert "parent" in validator.suggest_alternative("within")

    def test_vrf_name_filter_rejected_on_ipam(self):
        validator = FilterValidator()
        is_valid, error = validator.validate_filter({"vrf": "hvl-guest"}, "ipam.ipaddress")
        assert is_valid is False and "vrf_id" in error
        assert validator.validate_filter({"vrf": "65000:1"}, "dcim.device")[0] is True
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
