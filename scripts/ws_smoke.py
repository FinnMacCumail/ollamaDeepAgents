#!/usr/bin/env python3
"""WebSocket smoke client for the NetBox web chat (adapted from claude-agentic-sdk/netbox_cli.py).

Speaks the exact protocol the browser uses, so it doubles as the reference client.

Examples:
  ./venv/bin/python scripts/ws_smoke.py "What sites do I have?"
  ./venv/bin/python scripts/ws_smoke.py "Show devices at site DM-Akron" --follow-up "How many are active?"
  ./venv/bin/python scripts/ws_smoke.py "Describe everything" --cancel-after 20
  ./venv/bin/python scripts/ws_smoke.py "Say OK" --usage
"""

import argparse
import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets

DEFAULT_URL = "ws://127.0.0.1:8010/ws/chat"


def _fmt_int(v):
    return f"{int(v):,}" if v is not None else "n/a"


def _fmt_tps(v):
    return f"{float(v):.1f} t/s" if v is not None else "n/a"


async def run_turn(ws, conversation_id: str, text: str, cancel_after: float | None, as_json: bool):
    await ws.send(
        json.dumps({"type": "message", "conversation_id": conversation_id, "message": text})
    )
    started = time.monotonic()
    cancelled_sent = False
    got_terminal = None
    while True:
        timeout = None
        if cancel_after is not None and not cancelled_sent:
            timeout = max(0.05, cancel_after - (time.monotonic() - started))
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except TimeoutError:
            await ws.send(json.dumps({"type": "cancel"}))
            cancelled_sent = True
            print(f"\n[cancel sent at {time.monotonic() - started:.1f}s]")
            continue
        chunk = json.loads(raw)
        if as_json:
            print(raw)
        else:
            _print_chunk(chunk)
        if chunk.get("completed"):
            got_terminal = chunk
            break
    return got_terminal


def _print_chunk(chunk: dict) -> None:
    t = chunk.get("type")
    m = chunk.get("metadata") or {}
    if t == "text":
        sys.stdout.write(chunk.get("content", ""))
        sys.stdout.flush()
    elif t == "tool_use":
        print(f"\n[tool_use] {m.get('name')} {json.dumps(m.get('args'))[:200]}")
    elif t == "tool_result":
        print(
            f"[tool_result] {m.get('name')} status={m.get('status')} truncated={m.get('truncated')}"
        )
    elif t == "usage":
        print(
            f"\n[call {m.get('call_index')}] ctx {_fmt_int(m.get('input_tokens'))} "
            f"(cached {_fmt_int(m.get('cache_read'))}) out {_fmt_int(m.get('output_tokens'))} "
            f"| {m.get('context_pct')}% of {_fmt_int(m.get('n_ctx'))} "
            f"| prefill {_fmt_tps(m.get('prefill_tps'))} decode {_fmt_tps(m.get('decode_tps'))}"
        )
    elif t == "context_compacted":
        print(f"\n===== {chunk.get('content')} =====")
    elif t == "queued":
        print(f"[queued position {m.get('position')}]")
    elif t == "status":
        print(f"[status {m.get('phase')} {m.get('elapsed_s')}s]")
    elif t in ("done", "error", "cancelled"):
        u = m.get("usage") or {}
        print(
            f"\n[{t}] elapsed {m.get('elapsed_s', u.get('elapsed_s'))}s tools={m.get('tool_calls')} "
            f"model_calls={u.get('model_calls')} finish={m.get('finish_reason')} "
            f"read={_fmt_int(u.get('prompt_tokens_total'))} cached={_fmt_int(u.get('cache_read_total'))} "
            f"written={_fmt_int(u.get('completion_tokens_total'))} ctx_end={_fmt_int(u.get('context_end'))}"
        )
        if m.get("trace_url"):
            print(f"    trace: {m['trace_url']}")
        if t != "done":
            print(f"    {chunk.get('content')}")
    else:
        print(f"[{t}] {chunk.get('content', '')} {json.dumps(m)[:200]}")


async def print_usage(api_url: str, conversation_id: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{api_url}/conversations/{conversation_id}/usage")
        r.raise_for_status()
        u = r.json()
    print("\nLedger for", conversation_id)
    print(
        f"{'turn':>4} {'read':>9} {'cached':>9} {'written':>8} {'ctx_end':>9} {'calls':>5} {'s':>7}"
    )
    for i, t in enumerate(u["turns"], 1):
        print(
            f"{i:>4} {t['prompt_tokens_total']:>9,} {t['cache_read_total']:>9,} "
            f"{t['completion_tokens_total']:>8,} {_fmt_int(t['context_end']):>9} {t['model_calls']:>5} {t['elapsed_s']:>7.1f}"
        )
    print(
        f"{'sum':>4} {u['prompt_tokens_total']:>9,} {u['cache_read_total']:>9,} "
        f"{u['completion_tokens_total']:>8,} {_fmt_int(u['context_end']):>9} {u['model_calls_total']:>5} {u['elapsed_s_total']:>7.1f}"
    )


async def main() -> int:
    p = argparse.ArgumentParser(description="NetBox web chat smoke client")
    p.add_argument("message", help="first user message")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--conversation-id", default=None, help="reuse a thread id")
    p.add_argument("--follow-up", default=None, help="second message on the same conversation")
    p.add_argument("--cancel-after", type=float, default=None, help="send cancel after N seconds")
    p.add_argument("--usage", action="store_true", help="print the server ledger afterwards")
    p.add_argument("--json", action="store_true", help="print raw chunks")
    args = p.parse_args()

    conversation_id = args.conversation_id or uuid.uuid4().hex
    api_url = args.url.replace("ws://", "http://").replace("wss://", "https://").split("/ws/")[0]

    async with websockets.connect(args.url, max_size=None) as ws:
        first = json.loads(await ws.recv())
        print(
            f"[connected] model={first.get('metadata', {}).get('model')} conversation={conversation_id}"
        )
        await ws.send(json.dumps({"type": "resume", "conversation_id": conversation_id}))
        print(f"[resumed] {json.loads(await ws.recv()).get('metadata')}")

        terminal = await run_turn(ws, conversation_id, args.message, args.cancel_after, args.json)
        if args.cancel_after is not None and (terminal or {}).get("type") != "cancelled":
            print("EXPECTED a cancelled chunk", file=sys.stderr)
            return 2
        if args.follow_up:
            print("\n--- follow-up ---")
            await run_turn(ws, conversation_id, args.follow_up, None, args.json)

    if args.usage:
        await print_usage(api_url, conversation_id)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
