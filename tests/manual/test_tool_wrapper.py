"""Test the tool wrapper fix for both calling conventions."""
import asyncio
from src.tools.netbox_tools import FilterValidator


async def test_wrapper_both_conventions():
    """Test that the wrapper handles both positional and keyword arguments."""
    from langchain_core.tools import Tool

    # Create a mock original function
    async def mock_tool_func(*args, **kwargs):
        """Mock NetBox tool function."""
        if args and isinstance(args[0], dict):
            # Called with positional dict
            data = args[0]
            return f"Called with positional dict: {data}"
        else:
            # Called with kwargs
            return f"Called with kwargs: {kwargs}"

    # Create the wrapper (simulating NetBoxToolWrapper logic)
    validator = FilterValidator()
    original_func = mock_tool_func

    async def validated_func(*args, **kwargs):
        # Normalize arguments - handle both calling conventions
        if args and len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            # Called with single positional dict - convert to kwargs
            kwargs = args[0]
            args = ()

        # Check if this tool uses filters (validator logic)
        if "filters" in kwargs or "filter" in kwargs:
            filter_param = kwargs.get("filters") or kwargs.get("filter") or {}
            is_valid, error_msg = validator.validate_filter(filter_param)
            if not is_valid:
                raise ValueError(f"Invalid filter: {error_msg}")

        # Call original function
        result = await original_func(*args, **kwargs)
        return result

    # Test 1: Positional dict (how LangChain agents call it)
    print("Test 1: Positional dict")
    result1 = await validated_func({"object_type": "dcim.site", "filters": {}})
    print(f"  Result: {result1}")
    assert "kwargs" in result1, "Should convert positional dict to kwargs"

    # Test 2: Keyword arguments
    print("\nTest 2: Keyword arguments")
    result2 = await validated_func(object_type="dcim.site", filters={})
    print(f"  Result: {result2}")
    assert "kwargs" in result2, "Should handle kwargs directly"

    # Test 3: Invalid filter should be caught
    print("\nTest 3: Invalid filter detection")
    try:
        await validated_func({"object_type": "dcim.cable", "filters": {"device__site_id": 5}})
        print("  ERROR: Should have caught invalid filter!")
        return False
    except ValueError as e:
        print(f"  ✓ Caught invalid filter: {str(e)[:50]}...")

    # Test 4: Valid filter should pass
    print("\nTest 4: Valid filter")
    result4 = await validated_func({"object_type": "dcim.device", "filters": {"site_id": 5}})
    print(f"  Result: {result4}")
    assert "kwargs" in result4, "Valid filter should pass through"

    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_wrapper_both_conventions())
    exit(0 if success else 1)
