"""Test the actual query that was failing."""
import asyncio
from src.agents.netbox_agent import NetBoxDeepAgent


async def test_sites_query():
    """Test the query: Show me all sites in NetBox"""
    print("Initializing NetBox DeepAgent...")
    agent = NetBoxDeepAgent(enable_metrics=True)

    try:
        await agent.initialize()
        print("✓ Agent initialized\n")

        query = "Show me all sites in NetBox"
        print(f"Testing query: '{query}'")
        print("=" * 60)

        response_parts = []
        async for chunk in agent.query(query):
            response_parts.append(chunk)
            print(chunk, end="", flush=True)

        print("\n" + "=" * 60)

        full_response = "".join(response_parts)

        if full_response and "error" not in full_response.lower():
            print("\n✅ Query executed successfully!")
            print(f"\nMetrics:")
            print(agent.get_metrics_report())
            return True
        else:
            print("\n❌ Query failed or returned error")
            return False

    except Exception as e:
        print(f"\n❌ Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    success = asyncio.run(test_sites_query())
    exit(0 if success else 1)
