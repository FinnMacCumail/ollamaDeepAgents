#!/usr/bin/env python3
"""Examples demonstrating recovery from failed NetBox queries."""

import asyncio
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.netbox_agent import create_netbox_agent
from src.utils.config import load_config
from src.utils.logging import setup_logging


async def demonstrate_cable_query_recovery():
    """Show recovery for cable queries with relationship filters."""
    print("\n=== Cable Query Recovery ===\n")

    agent = await create_netbox_agent(enable_metrics=True)

    # Query that fails in baseline
    query = "Show cables connected to device dmi01-nashua-pdu01"

    print(f"Query: {query}")
    print("\n❌ Baseline approach would use: {'termination_a__device_id': 19}")
    print("   This fails with: Invalid filter: termination_a__device_id")

    print("\n✅ Our approach uses two-step query:")
    print("   Step 1: Get device by name")
    print("   Step 2: Query cables with device_id")

    # Execute with recovery
    print("\nExecuting with automatic recovery...")
    response = await agent.query_sync(query)
    print(f"Response: {response[:300]}...")

    print(f"\nMetrics: {agent.metrics.filter_errors} errors, {agent.metrics.recovered_errors} recovered")

    await agent.cleanup()


async def demonstrate_site_search_recovery():
    """Show recovery for site searches with Django lookups."""
    print("\n=== Site Search Recovery ===\n")

    agent = await create_netbox_agent(enable_metrics=True)

    query = "Show all Dunder-Mifflin sites with device counts"

    print(f"Query: {query}")
    print("\n❌ Baseline approach would use: {'name__icontains': 'dunder'}")
    print("   This fails with: Invalid filter: name__icontains")

    print("\n✅ Our approach uses search:")
    print("   netbox_search_objects(query='Dunder-Mifflin')")
    print("   Then counts devices per site")

    print("\nExecuting with automatic recovery...")
    response = await agent.query_sync(query)
    print(f"Response: {response[:300]}...")

    await agent.cleanup()


async def demonstrate_multi_step_recovery():
    """Show recovery for complex multi-hop queries."""
    print("\n=== Multi-Step Query Recovery ===\n")

    agent = await create_netbox_agent(enable_metrics=True)

    query = "Find all power outlets in rack R01"

    print(f"Query: {query}")
    print("\n❌ Baseline might try: {'device__rack__name': 'R01'}")
    print("   This fails with multi-hop filter error")

    print("\n✅ Our approach uses three steps:")
    print("   Step 1: Get rack by name")
    print("   Step 2: Get devices in rack")
    print("   Step 3: Get power outlets for each device")

    print("\nExecuting with automatic recovery...")
    try:
        response = await agent.query_sync(query)
        print(f"Response: {response[:300]}...")
    except Exception as e:
        print(f"Error (will be recovered): {str(e)[:100]}...")

    await agent.cleanup()


async def test_all_failed_queries():
    """Test all queries from the failed queries dataset."""
    print("\n=== Testing All Failed Queries ===\n")

    # Load failed queries from test data
    with open("tests/data/failed_queries.json", "r") as f:
        data = json.load(f)
        failed_queries = data["failed_queries"]

    agent = await create_netbox_agent(enable_metrics=True)

    success_count = 0
    failure_count = 0

    for query_data in failed_queries:
        query = query_data["query"]
        expected_error = query_data["baseline_error"]
        approach = query_data["expected_approach"]

        print(f"\n📝 Query: {query}")
        print(f"   Baseline error: {expected_error}")
        print(f"   Recovery approach: {approach}")

        try:
            response = await agent.query_sync(query)
            print(f"   ✅ Success! Response length: {len(response)} chars")
            success_count += 1

        except Exception as e:
            print(f"   ❌ Failed: {str(e)[:100]}...")
            failure_count += 1

    # Calculate success rate
    total = success_count + failure_count
    success_rate = (success_count / total * 100) if total > 0 else 0

    print("\n" + "=" * 50)
    print("📊 Final Results:")
    print(f"   Total queries: {total}")
    print(f"   Successful: {success_count}")
    print(f"   Failed: {failure_count}")
    print(f"   Success rate: {success_rate:.1f}%")
    print(f"   Target rate: 85%")
    print(f"   {'✅ PASSED' if success_rate >= 85 else '❌ BELOW TARGET'}")

    # Show detailed metrics
    print("\n📈 Performance Metrics:")
    print(agent.get_metrics_report())

    await agent.cleanup()


async def demonstrate_recovery_strategies():
    """Show different recovery strategies in action."""
    print("\n=== Recovery Strategy Examples ===\n")

    strategies = [
        {
            "name": "Two-Step Query",
            "bad_query": "List interfaces on devices in site NYC-DC1",
            "bad_filter": "interface__device__site_id",
            "recovery": [
                "1. Get site NYC-DC1 by name",
                "2. Get devices in site",
                "3. Get interfaces for each device",
            ],
        },
        {
            "name": "Search Alternative",
            "bad_query": "Find sites with 'production' in the name",
            "bad_filter": "name__icontains='production'",
            "recovery": [
                "1. Use netbox_search_objects(query='production')",
                "2. Filter results for site objects",
            ],
        },
        {
            "name": "Direct ID Usage",
            "bad_query": "Get cables for device with known ID 42",
            "bad_filter": "termination_a__device_id=42",
            "recovery": [
                "1. Use device_id=42 directly if known",
                "2. Or get device first, then use ID",
            ],
        },
    ]

    agent = await create_netbox_agent()

    for strategy in strategies:
        print(f"\n🔧 {strategy['name']}:")
        print(f"   Query: {strategy['bad_query']}")
        print(f"   ❌ Bad filter: {strategy['bad_filter']}")
        print(f"   ✅ Recovery steps:")
        for step in strategy["recovery"]:
            print(f"      {step}")

    await agent.cleanup()


async def demonstrate_metrics_improvement():
    """Show improvement in metrics with recovery enabled."""
    print("\n=== Metrics Improvement Demonstration ===\n")

    # Queries that would fail without recovery
    problematic_queries = [
        "Show cables for device router01",
        "Find sites containing 'lab'",
        "List VMs on host server01",
        "Get prefixes in VRF production",
        "Show interfaces with IPs in subnet 192.168.1.0/24",
    ]

    print("Testing queries that typically fail...\n")

    # Test with recovery enabled (our system)
    agent_with_recovery = await create_netbox_agent(enable_metrics=True)

    for query in problematic_queries:
        print(f"📝 {query}")
        try:
            response = await agent_with_recovery.query_sync(query)
            print(f"   ✅ Handled successfully")
        except Exception as e:
            print(f"   ⚠️ Needs manual intervention: {str(e)[:50]}...")

    print("\n📊 Results with Recovery Middleware:")
    metrics = agent_with_recovery.metrics
    print(f"   Success rate: {metrics.success_rate:.1f}%")
    print(f"   Filter errors caught: {metrics.filter_errors}")
    print(f"   Errors recovered: {metrics.recovered_errors}")
    print(f"   Recovery rate: {metrics.recovery_rate:.1f}%")

    await agent_with_recovery.cleanup()


async def main():
    """Run all recovery examples."""
    # Setup logging
    setup_logging("INFO")

    # Check configuration
    try:
        load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set NETBOX_URL and NETBOX_TOKEN in .env file")
        return

    print("=" * 60)
    print("NetBox DeepAgents - Failed Query Recovery Examples")
    print("=" * 60)

    # Run examples
    await demonstrate_cable_query_recovery()
    await demonstrate_site_search_recovery()
    await demonstrate_multi_step_recovery()
    await demonstrate_recovery_strategies()
    await demonstrate_metrics_improvement()

    # Full test suite (optional - requires NetBox connection)
    print("\n" + "=" * 60)
    print("Running full failed query test suite...")
    print("=" * 60)
    await test_all_failed_queries()

    print("\n✅ Recovery examples completed!")


if __name__ == "__main__":
    asyncio.run(main())