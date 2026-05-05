#!/usr/bin/env python3
"""Debug script to understand what's being streamed."""

import asyncio
import sys

async def debug_stream():
    """Debug the streaming output."""
    # Simulate the agent streaming behavior
    print("=== SIMULATING AGENT STREAM ===\n")

    # Step 1: User message
    print("Step 1: User message added to state")
    print("  last_msg.content would be: 'list all sites'")
    print("  ✓ This gets yielded\n")

    # Step 2: Agent plans
    print("Step 2: Agent thinks/plans")
    print("  last_msg.content might be: thinking content or empty")
    print("  ✓ This gets yielded if not empty\n")

    # Step 3: Agent makes tool call
    print("Step 3: Agent makes tool call")
    print("  last_msg is a ToolCall message")
    print("  last_msg.content might be: the tool call structure")
    print("  ✓ This gets yielded\n")

    # Step 4: Tool returns result
    print("Step 4: Tool execution completes")
    print("  last_msg is a ToolMessage")
    print("  last_msg.content is: RAW JSON from NetBox API")
    print("  ✓ This gets yielded (THE PROBLEM!)\n")

    # Step 5: Agent formats response
    print("Step 5: Agent processes and formats")
    print("  last_msg.content is: Formatted human-readable response")
    print("  ✓ This gets yielded\n")

    print("=== RESULT ===")
    print("All 5 chunks are concatenated together:")
    print("1. 'list all sites' (user echo?)")
    print("2. Tool call structure")
    print("3. RAW JSON (the messy part)")
    print("4. Maybe intermediate thinking")
    print("5. Final formatted response")
    print("\nThis explains the messy output!")

if __name__ == "__main__":
    asyncio.run(debug_stream())
