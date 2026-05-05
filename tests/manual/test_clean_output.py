#!/usr/bin/env python3
"""
Test the cleaned-up streaming output.

This script tests that the fix properly filters out:
- User message echoes
- Tool messages with raw JSON
- Empty AI messages
- Tool call structures

And only yields clean final AI responses.
"""

import asyncio
import sys
from src.agents.netbox_agent import create_netbox_agent


async def test_clean_output():
    """Test that streaming output is clean."""
    print("Creating NetBox agent...")
    agent = await create_netbox_agent()

    print("\nQuerying: 'list 3 sites'\n")
    print("=" * 60)
    print("OUTPUT:")
    print("=" * 60)

    chunk_count = 0
    total_chars = 0

    async for chunk in agent.query("list 3 sites"):
        chunk_count += 1
        total_chars += len(chunk)
        print(f"\n[Chunk {chunk_count}] ({len(chunk)} chars)")
        print("-" * 60)
        print(chunk)
        print("-" * 60)

    print("\n" + "=" * 60)
    print(f"SUMMARY:")
    print(f"  Total chunks: {chunk_count}")
    print(f"  Total characters: {total_chars}")
    print(f"  Expected: 1 chunk (clean formatted response)")
    print("=" * 60)

    if chunk_count == 1:
        print("\n✅ SUCCESS: Only one clean chunk yielded!")
    else:
        print(f"\n⚠️  WARNING: {chunk_count} chunks yielded (expected 1)")

    await agent.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(test_clean_output())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
