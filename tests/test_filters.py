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
        whitelist (which uses short forms like `__ic`). But `__in`, `__gte`,
        `__regex` etc. ARE on the whitelist and must NOT be rejected.
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

        # These ARE on the MCP server's VALID_SUFFIXES whitelist — must pass
        accepted_lookups = [
            {"id__in": [1, 2, 3]},
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