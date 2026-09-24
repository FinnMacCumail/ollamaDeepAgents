"""Multi-turn session harness — the case the matrix deliberately does not test.

`run_matrix*.py` assigns a fresh `thread_id` per question (see run_matrix.py:89),
so every score this project has is a SINGLE-QUESTION measurement. The interactive
app does the opposite: `main.py` reuses one rolling thread, so every turn replays
the whole prior transcript including raw tool results.

Nothing downstream of that has ever been exercised:

  * decode degradation as context grows (measured once, ad hoc: 5.11 -> 1.45
    tok/s between ~9k and ~76k tokens of context)
  * the summarization/compaction path — trigger, eviction to
    conversation_history/, tool_call_id preservation — which never fires in the
    matrix because context never gets large enough
  * whether a later turn actually USES an earlier answer, or silently re-fetches
  * `--no-reasoning-preserve`, which only has an effect across turns

THIS IS DIAGNOSTIC INSTRUMENTATION, NOT A SCOREBOARD.

Question ORDER is a confound in a session: turn 1 is cheap, turn 10 is dear, so
session totals are not comparable across different orderings the way independent
matrix items are. Read the per-turn CURVE, not the mean. And note that
same-question tool-call variance has been measured at 9 vs 14 under identical
config, so a single session separates only large effects.

Usage
-----
    LLAMACPP_SERVER_LOG=/path/to/llama-server.log \
    ./venv/bin/python -m tests.eval.run_session

    SESSION_QUESTIONS=/path/to/questions.json   # optional, overrides the default
    SESSION_TURNS=15                            # optional, truncate the sequence
    EVAL_BACKEND=llamacpp EVAL_MODEL=...        # optional

The server log is optional. Without it the run still records wall time, tool
calls, message growth and compaction, but NOT context occupancy or decode rate —
those come from llama.cpp itself and cannot be derived client-side. See the
MEASUREMENT NOTE below for why the obvious client-side substitute is wrong.

MEASUREMENT NOTE
----------------
`count_tokens_approximately(state["messages"])` UNDERCOUNTS by roughly 19x: a
turn reporting 454 tokens of state had 8,751 tokens actually resident on the
server. The system prompt is a `create_deep_agent` kwarg and the tool schemas and
skills are injected by middleware at call time, so none of it lives in
`state["messages"]`. Ground truth is the server's own slot-release line.

Note also that the `prompt processing ... progress = 1.00` line reports only the
NEWLY prefilled tokens, which with ~85% prefix-cache hits is a small residual.
The slot RELEASE line carries the full context the slot held. Use that.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO / ".env", override=True)

_TRACES_DIR = _REPO / "docs" / "traces"
_SERVER_LOG = os.getenv("LLAMACPP_SERVER_LOG", "").strip()

# Slot RELEASE line: full context the slot held, plus llama.cpp's own truncation
# flag. `truncated = 1` is the dangerous case — the model answers confidently
# from a transcript it no longer holds in full.
_RELEASE = re.compile(r"stop processing: n_tokens = (\d+), truncated = (\d+)")
_DECODE = re.compile(r"tg = *([0-9.]+) t/s")

# A domain-coherent default: one estate (Halvorsen), dcim openers establishing
# the site then a power ladder over the same hardware, ordered simple -> advanced
# so the cost curve ramps. Coherence is deliberate — a session that hops domains
# measures context growth without measuring whether context is USED.
#
# Turns 1-10 are quoted VERBATIM from netbox-benchmark-v5 so each one carries a
# reference answer and scores for free. The strings must match exactly: a single
# stray character silently drops that turn to unscored. `_v5_references()` keys
# on the question text, and the match rate is printed at startup — check it.
#
# Several of these have known SINGLE-question baselines from the full v5 run and
# the GraphQL A/B (the two-PSU host, the PDU-outlet count, the inactive feeds),
# so a session run shows directly what accumulation costs versus running cold.
#
# Turn 11 is deliberately NOT a v5 item and will not score. It is the only turn
# that can reveal whether the transcript is being used rather than re-fetched.
DEFAULT_QUESTIONS: list[str] = [
    # --- dcim: cheap openers that establish the site ---
    "How many devices are recorded at site HVL-SEA-DC1? Include every device status and report a single number.",
    "List the names of every rack at site HVL-SEA-DC1.",
    "At site HVL-SEA-DC1, which rack holds the most mounted devices? Name the rack and give its device count.",
    # --- power: same estate, escalating ---
    "How many power outlets does each Halvorsen Logistics PDU provide, and how many PDUs are there?",
    "Across all Halvorsen Logistics PDUs, how many of the available power outlets are actually in use?",
    "Which Halvorsen Logistics PDUs have any outlet in use, and how many outlets are in use on each?",
    "Which Halvorsen Logistics power feeds are not in the active state, and which rack does each serve?",
    "Do any Halvorsen Logistics PDUs draw power from a modelled power feed, or is the upstream connection missing?",
    "Each Halvorsen Logistics hypervisor host has two power supplies. Which host has exactly one of its two supplies connected to a PDU outlet, and which outlet is it?",
    "Comparing the power feeds at the Halvorsen data centre with those serving NC State's racks, which estate has more feeds and how do their electrical ratings differ?",
    # --- synthesis: unscored by design, tests whether memory is used ---
    "Summarise everything you have established about the Halvorsen power estate so far.",
]


def _load_questions() -> list[str]:
    path = os.getenv("SESSION_QUESTIONS", "").strip()
    qs = json.loads(Path(path).read_text()) if path else list(DEFAULT_QUESTIONS)
    limit = os.getenv("SESSION_TURNS", "").strip()
    return qs[: int(limit)] if limit else qs


def _v5_references() -> dict[str, dict]:
    """Reference answers keyed by question, for turns that match a v5 item.

    Most hand-written session questions will NOT match, and that is fine: the
    degradation curve is the deliverable and it needs no ground truth. Where a
    turn does match, we get reference-grounded correctness for free.
    """
    try:
        from tests.eval.dataset_v5 import BENCHMARK_EXAMPLES_V5
    except Exception:
        return {}
    out = {}
    for e in BENCHMARK_EXAMPLES_V5:
        try:
            out[e.question] = {"ref": e.to_reference_output(),
                               "tier": getattr(e, "difficulty", None)}
        except Exception:
            continue
    return out


class _ServerLog:
    """Tails the llama-server log, returning per-turn occupancy and decode."""

    def __init__(self, path: str):
        self.path = path
        self.offset = 0
        if path and os.path.exists(path):
            self.offset = os.path.getsize(path)

    @property
    def available(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def since_last(self) -> dict:
        """Stats for log lines written since the previous call."""
        if not self.available:
            return {"context_peak": None, "decode_tok_s": None, "truncated": None}
        try:
            with open(self.path, "r", errors="replace") as fh:
                fh.seek(self.offset)
                chunk = fh.read()
                self.offset = fh.tell()
        except OSError:
            return {"context_peak": None, "decode_tok_s": None, "truncated": None}
        peak = 0
        trunc = 0
        for m in _RELEASE.finditer(chunk):
            peak = max(peak, int(m.group(1)))
            trunc += 1 if int(m.group(2)) else 0
        rates = [float(m.group(1)) for m in _DECODE.finditer(chunk)]
        return {
            "context_peak": peak or None,
            "decode_tok_s": round(sum(rates) / len(rates), 2) if rates else None,
            "truncated": trunc,
        }


def _score(inputs: dict, outputs: dict, reference: dict | None) -> dict:
    """Run the project evaluators directly.

    Deliberately NOT via `aevaluate`: that assigns a fresh thread per example,
    which is precisely the behaviour this harness exists to avoid.
    """
    if not reference:
        return {"scored": False}
    from tests.eval.evaluators import ALL_EVALUATORS

    got: dict = {"scored": True}
    for fn in ALL_EVALUATORS:
        try:
            res = fn(inputs, outputs, reference)
            if isinstance(res, dict) and res.get("key") is not None:
                got[res["key"]] = res.get("score")
        except Exception as e:  # noqa: BLE001 - a judge failure must not kill the run
            got[getattr(fn, "__name__", "evaluator")] = f"ERROR {type(e).__name__}: {e}"
    return got


def _write_trace(rows: list[dict], meta: dict, stamp: str) -> Path:
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    path = _TRACES_DIR / f"{stamp[:10]}_netbox-session_{meta['label']}.md"
    ctx = [r["context_peak"] for r in rows if r.get("context_peak")]
    dec = [r["decode_tok_s"] for r in rows if r.get("decode_tok_s")]
    lines = [
        f"# NetBox multi-turn session [{meta['label']}] — {stamp}",
        "",
        f"- Model: **{meta['model']}** ({meta['backend']})",
        f"- Turns: **{len(rows)}**, ONE accumulating thread (`{meta['thread'][:12]}…`)",
        f"- Compaction trigger: {meta['trigger']}",
        "",
        "> Diagnostic instrumentation, not a scoreboard. Question ORDER is a",
        "> confound in a session — read the per-turn curve, not the mean.",
        "",
        "## Per-turn",
        "",
        "| turn | secs | context | decode t/s | msgs | tool calls | compacted | correctness | question |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['turn']} | {r['seconds']:.0f} | "
            f"{r['context_peak'] or '—'} | {r['decode_tok_s'] or '—'} | "
            f"{r['messages']} | {r['tool_calls']} | "
            f"{'**yes**' if r['compacted'] else 'no'} | "
            f"{r.get('correctness', '—')} | {r['question'][:52]} |"
        )
    lines += ["", "## Degradation", ""]
    if len(ctx) >= 2 and len(dec) >= 2:
        lines += [
            f"- context: **{ctx[0]:,} → {ctx[-1]:,}** tokens ({ctx[-1] / ctx[0]:.1f}×)",
            f"- decode: **{dec[0]} → {dec[-1]} tok/s** "
            f"({100 * (1 - dec[-1] / dec[0]):.0f}% slower)",
            f"- turn time: **{rows[0]['seconds']:.0f}s → {rows[-1]['seconds']:.0f}s**",
        ]
    else:
        lines.append("- server log unavailable; context/decode not captured")
    lines += [
        "",
        f"- truncations reported by llama.cpp: "
        f"**{sum(r.get('truncated') or 0 for r in rows)}**",
        f"- compaction fired: **{sum(1 for r in rows if r['compacted'])}** turn(s)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def main() -> None:
    backend = os.getenv("EVAL_BACKEND", "llamacpp")
    model = os.getenv("EVAL_MODEL") or os.getenv("LLAMACPP_MODEL") or "unknown"
    label = os.getenv("SESSION_LABEL", "baseline")
    questions = _load_questions()
    refs = _v5_references()
    log = _ServerLog(_SERVER_LOG)

    from src.agents.netbox_agent import create_netbox_agent

    trigger = "unknown"
    try:
        from deepagents.middleware.summarization import compute_summarization_defaults
        from src.agents.llamacpp_config import create_llamacpp_model
        if backend == "llamacpp":
            t = compute_summarization_defaults(
                create_llamacpp_model(model, validate=False))["trigger"]
            trigger = f"{t}"
    except Exception:
        pass

    print(f"session [{label}]: {len(questions)} turns, backend={backend} model={model}")
    print(f"  server log : {_SERVER_LOG or '(none — context/decode will be blank)'}")
    print(f"  compaction : {trigger}")
    print(f"  v5 refs    : {len(refs)} available for scoring matched turns\n")

    agent = await create_netbox_agent(backend=backend, model_name=model)
    thread = agent.thread_id
    cfg = {"configurable": {"thread_id": thread}}
    print(f"thread (never rotated): {thread}\n")
    print(f"{'turn':>4} {'secs':>7} {'context':>9} {'dec':>6} {'msgs':>5} "
          f"{'calls':>6} {'cmpct':>6}  note")

    rows: list[dict] = []
    prev_tools = 0
    for i, q in enumerate(questions, 1):
        t0 = time.time()
        err = None
        try:
            answer = await agent.query_sync(q)      # no thread_id -> ACCUMULATES
        except Exception as e:  # noqa: BLE001
            answer, err = "", f"{type(e).__name__}: {e}"
        dt = time.time() - t0

        srv = log.since_last()
        st = await agent.agent.aget_state(cfg)
        vals = (st.values if st and st.values else {}) or {}
        msgs = vals.get("messages", [])
        total_tools = sum(1 for m in msgs if getattr(m, "type", None) == "tool")
        row = {
            "turn": i, "question": q, "seconds": round(dt, 1),
            "messages": len(msgs), "tool_calls": total_tools - prev_tools,
            "compacted": bool(vals.get("_summarization_event")),
            "answer_chars": len(answer or ""), "error": err,
            **srv,
        }
        prev_tools = total_tools

        match = refs.get(q)
        row.update(_score({"question": q},
                          {"answer": answer, "tool_call_count": row["tool_calls"]},
                          match["ref"] if match else None))
        if match:
            row["tier"] = match["tier"]
        rows.append(row)

        note = f"ERROR {err[:60]}" if err else ""
        if row["compacted"]:
            note = (note + " COMPACTION FIRED").strip()
        if row.get("truncated"):
            note = (note + " TRUNCATED").strip()
        print(f"{i:>4} {dt:>7.1f} {str(row['context_peak'] or '—'):>9} "
              f"{str(row['decode_tok_s'] or '—'):>6} {len(msgs):>5} "
              f"{row['tool_calls']:>6} {str(row['compacted']):>6}  {note}", flush=True)
        if err:
            break

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = {"label": label, "model": model, "backend": backend,
            "thread": thread, "trigger": trigger}
    out_json = _TRACES_DIR / f"{stamp[:10]}_netbox-session_{label}.json"
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"meta": meta, "turns": rows}, indent=2),
                        encoding="utf-8")
    trace = _write_trace(rows, meta, stamp)

    hist = _REPO / "conversation_history" / f"{thread}.md"
    print(f"\neviction file for this thread: {'YES' if hist.exists() else 'no'}")
    print(f"wrote {trace}")
    print(f"wrote {out_json}")
    await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
