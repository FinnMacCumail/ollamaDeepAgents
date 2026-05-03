#!/usr/bin/env python3
"""Basic usage examples for NetBox DeepAgents with Ollama."""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.netbox_agent import create_netbox_agent
from src.utils.config import load_config
from src.utils.logging import setup_logging


async def example_simple_queries():
    """Demonstrate simple queries that work with direct filters."""
    print("\n=== Simple Query Examples ===\n")

    # Initialize agent
    agent = await create_netbox_agent()

    # Example 1: Get device by ID
    print("1. Getting device by ID:")
    response = await agent.query_sync("Show device with ID 42")
    print(f"Response: {response[:200]}...\n")

    # Example 2: Get site by exact name
    print("2. Getting site by exact name:")
    response = await agent.query_sync("Get site named NYC-DC1")
    print(f"Response: {response[:200]}...\n")

    # Example 3: List all active devices
    print("3. Listing active devices:")
    response = await agent.query_sync("List all active devices")
    print(f"Response: {response[:200]}...\n")

    # Example 4: Search for pattern
    print("4. Searching for pattern:")
    response = await agent.query_sync("Search for devices with 'web' in the name")
    print(f"Response: {response[:200]}...\n")

    await agent.cleanup()


async def example_streaming_response():
    """Demonstrate streaming responses for real-time feedback."""
    print("\n=== Streaming Response Example ===\n")

    agent = await create_netbox_agent()

    query = "Show all interfaces on device router01"
    print(f"Query: {query}")
    print("Streaming response:")

    async for chunk in agent.query(query):
        print(chunk, end="", flush=True)

    print("\n")
    await agent.cleanup()


async def example_batch_queries():
    """Demonstrate batch query execution."""
    print("\n=== Batch Query Example ===\n")

    agent = await create_netbox_agent()

    queries = [
        "Count total devices",
        "List all sites",
        "Show VLANs in the network",
    ]

    print(f"Executing {len(queries)} queries in batch:\n")

    results = await agent.batch_query(queries)

    for query, response in results.items():
        print(f"Query: {query}")
        print(f"Response: {response[:150]}...\n")
        print("-" * 50)

    await agent.cleanup()


async def example_with_metrics():
    """Demonstrate query execution with metrics tracking."""
    print("\n=== Query with Metrics Example ===\n")

    # Create agent with metrics enabled
    agent = await create_netbox_agent(enable_metrics=True)

    # Execute several queries
    test_queries = [
        "Show all devices in site NYC-DC1",
        "List interfaces on router01",
        "Find all circuits",
        "Search for servers",
    ]

    for query in test_queries:
        print(f"Executing: {query}")
        try:
            response = await agent.query_sync(query)
            print(f"Success: {len(response)} chars\n")
        except Exception as e:
            print(f"Error: {str(e)}\n")

    # Display metrics
    print("\n=== Performance Metrics ===")
    print(agent.get_metrics_report())

    await agent.cleanup()


async def example_successful_vs_failed_patterns():
    """Demonstrate patterns that succeed vs those that need recovery."""
    print("\n=== Successful vs Failed Pattern Examples ===\n")

    agent = await create_netbox_agent()

    # Successful patterns (direct filters)
    print("✅ SUCCESSFUL PATTERNS:")
    successful_queries = [
        ("Direct ID filter", "Show device with device_id 123"),
        ("Exact name match", "Get device named 'server01'"),
        ("Simple status filter", "List active sites"),
        ("Search pattern", "Search for 'production' in all objects"),
    ]

    for pattern_name, query in successful_queries:
        print(f"\n{pattern_name}:")
        print(f"  Query: {query}")
        # In real usage, these would succeed
        print(f"  Result: ✅ Works directly\n")

    # Failed patterns (need recovery)
    print("\n❌ PATTERNS THAT NEED RECOVERY:")
    failed_patterns = [
        ("Multi-hop filter", "device__site_id=5", "Use two-step query"),
        ("Django lookup", "name__icontains='prod'", "Use search instead"),
        ("Relationship traversal", "interface__device__name='router'", "Break into steps"),
    ]

    for pattern_name, bad_filter, solution in failed_patterns:
        print(f"\n{pattern_name}:")
        print(f"  Bad filter: {bad_filter}")
        print(f"  Solution: {solution}\n")

    await agent.cleanup()


async def example_different_models():
    """Demonstrate using different Ollama models."""
    print("\n=== Different Model Examples ===\n")

    models = ["mixtral:8x7b", "qwen2.5:32b"]  # Add models you have pulled

    for model_name in models:
        print(f"\n--- Using model: {model_name} ---")

        try:
            agent = await create_netbox_agent(model_name=model_name)
            response = await agent.query_sync("Count total devices in the network")
            print(f"Response: {response[:150]}...")
            await agent.cleanup()

        except Exception as e:
            print(f"Error with {model_name}: {str(e)}")


async def main():
    """Run all examples."""
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
    print("NetBox DeepAgents with Ollama - Basic Usage Examples")
    print("=" * 60)

    # Run examples
    await example_simple_queries()
    await example_streaming_response()
    await example_batch_queries()
    await example_with_metrics()
    await example_successful_vs_failed_patterns()

    # Optional: Test different models (comment out if models not available)
    # await example_different_models()

    print("\n✅ All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())