"""Quick test to verify MCP connection."""
import asyncio
import sys
from src.agents.netbox_agent import NetBoxDeepAgent


async def main():
    print("Initializing NetBox DeepAgent...")
    agent = NetBoxDeepAgent(enable_metrics=False)

    try:
        await agent.initialize()
        print("✓ Agent initialized successfully!")
        print("✓ MCP client connected!")

        # Test getting tools
        tools = await agent.tool_wrapper.get_tools()
        print(f"✓ Found {len(tools)} tools")

        # List first few tools
        print("\nAvailable tools:")
        for tool in tools[:5]:
            print(f"  - {tool.name}")

        print("\n✅ Connection test successful!")

    except Exception as e:
        print(f"\n❌ Connection test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
