#!/usr/bin/env python3
"""Test MCP connection in isolation."""

import asyncio
import sys
from langchain_mcp_adapters.client import MultiServerMCPClient

async def test_mcp():
    print("1. Creating MCP config...")
    mcp_config = {
        "netbox": {
            "transport": "stdio",
            "command": "uv",
            "args": ["--directory", "/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server", "run", "netbox-mcp-server"],
            "env": {
                "NETBOX_URL": "http://localhost:8000",
                "NETBOX_TOKEN": "c4af48e5b315a5baf92f7ca449ac5d664239916a",
                "TRANSPORT": "stdio",  # Override .env file
            }
        }
    }

    print("2. Creating MultiServerMCPClient...")
    sys.stdout.flush()

    try:
        client = MultiServerMCPClient(mcp_config)
        print("3. Client created successfully!")

        print("4. Attempting to get tools (30s timeout)...")
        sys.stdout.flush()

        tools = await asyncio.wait_for(client.get_tools(), timeout=30.0)
        print(f"5. Success! Got {len(tools)} tools")

        for tool in tools:
            print(f"   - {tool.name}")

    except asyncio.TimeoutError:
        print("ERROR: Timeout after 30 seconds")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting MCP connection test...")
    asyncio.run(test_mcp())
    print("Test complete!")
