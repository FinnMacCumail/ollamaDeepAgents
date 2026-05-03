"""Direct test of tool invocation to verify signature fix."""
import asyncio
from src.tools.netbox_tools import create_netbox_mcp_client, NetBoxToolWrapper


async def test_tool_invocation():
    """Test direct tool invocation with both calling conventions."""
    from dotenv import load_dotenv
    import os

    load_dotenv()

    print("Creating MCP client...")
    client = await create_netbox_mcp_client(
        os.getenv("NETBOX_URL"),
        os.getenv("NETBOX_TOKEN"),
        os.getenv("MCP_SERVER_PATH"),
    )

    print("Creating tool wrapper...")
    wrapper = NetBoxToolWrapper(client)
    tools = await wrapper.get_tools()

    # Get the netbox_get_objects tool
    get_objects_tool = next(t for t in tools if t.name == "netbox_get_objects")

    print(f"\nTool: {get_objects_tool.name}")
    print(f"Type: {type(get_objects_tool)}")

    # Test 1: Invoke with keyword arguments
    print("\n" + "=" * 60)
    print("Test 1: Invoke with keyword arguments")
    print("=" * 60)
    try:
        result = await get_objects_tool.ainvoke(
            {"object_type": "dcim.site", "filters": {}, "limit": 3}
        )
        print(f"✅ SUCCESS - Tool executed")
        print(f"   Result type: {type(result)}")
        print(f"   Result preview: {str(result)[:200]}...")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Try with invalid filter to test validation
    print("\n" + "=" * 60)
    print("Test 2: Invalid filter validation")
    print("=" * 60)
    try:
        result = await get_objects_tool.ainvoke(
            {"object_type": "dcim.cable", "filters": {"device__site_id": 5}, "limit": 3}
        )
        print(f"❌ FAILED - Should have caught invalid filter!")
    except ValueError as e:
        print(f"✅ SUCCESS - Caught invalid filter: {str(e)[:80]}...")
    except Exception as e:
        print(f"❓ Unexpected error: {e}")

    print("\n" + "=" * 60)
    print("✅ Tool invocation tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_tool_invocation())
