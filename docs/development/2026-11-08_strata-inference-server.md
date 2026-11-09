# 2026-11-08: Strata as the inference server — same weights, 1.67× the agent speed

## Summary

James installed [Strata](https://github.com/Niko1221) 0.2.10 (engine 0.1.57, a closed, precompiled
ggml/llama.cpp-derived CUDA 13 binary) on plenum on 2026-11-05 and launched the project's own
Qwen3.8-Flash-Next UD-Q4_K_XL files through it. It serves an OpenAI-compatible API on
`0.0.0.0:8080` behind a Bearer API key (`~/.strata-api-key.plenum`, required even from
localhost), with one slot, a request queue, int8 KV with KV streaming, an expert cache placed
from a usage profile, a layer split across both 2080 Tis, and speculative decoding with a shipped
draft model. It holds ~10.3 GB on each GPU and ~110 GB RSS, so `scripts/serve_qwen4exp.sh`
(llama-server on 58123) cannot run beside it.

The agent was pointed at it with a configuration change plus three small code changes, the
8-question v5 subset from 2026-10-17 was re-run (8/8, 1.73× faster agent time), and then the full
90-question v5 benchmark (90/90, **1.67× faster agent time, correctness 0.922 → 0.939**, identical
model-call count). `.env` now targets Strata.

## What changed in the code

All in `src/agents/llamacpp_config.py` and `src/web/llama_status.py`; additions only.

1. **Bearer header on the probes.** `GET /v1/models` (CLI start-up check, model listing) and
   `GET /slots` (web `/health` and `/status`) sent no `Authorization` header. Strata answers 401
   to both; llama-server does not care. A `_auth_headers()` helper adds
   `Authorization: Bearer $LLAMACPP_API_KEY` whenever the key is set and is not `not-needed`.
   `/health` is open on both servers.
2. **Cached-token fallback.** Strata reports `usage.prompt_tokens_details.cached_tokens = 0`
   even when it reused the prefix (16,197 of 16,202 tokens in a 16k test); the true count is in
   its llama.cpp-style `timings.cache_n`. `LlamaCppChatOpenAI` now copies `cache_n` into
   `usage_metadata.input_token_details.cache_read` when the OpenAI field is 0, so the web
   ledger's *cached* column is correct on both servers.
3. **`timings` kept on non-streaming calls too.** The subclass already preserved llama.cpp's
   `timings` block on the final streamed chunk (web chat). A matching `_create_chat_result`
   override does the same for `invoke()` (CLI, eval harness), reading it from the openai
   response model's `model_extra`. Every benchmark model call in LangSmith now carries
   `prompt_ms` / `predicted_ms` / `prompt_n` / `predicted_n` / `cache_n`, so queue wait
   (wall − compute) and server-side tok/s can be read per call instead of scraped from a log.

Verified against Strata before the benchmark: authenticated probe `ok=True, n_ctx=131072`;
model list `['qwen3.8-flash-next-unsloth-ud-q4_k_xl']` (Strata ignores the requested model
name and serves its loaded model, so `LLAMACPP_MODEL` is unchanged); streaming and
non-streaming calls both show `cache_read == cache_n` on the second call.

## Configuration

```
LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1
LLAMACPP_MODEL=qwen3.8-flash-next-UD-Q4_K_XL      # alias; Strata serves its loaded model
LLAMACPP_API_KEY=<contents of ~/.strata-api-key.plenum>
```

The web layer derives its `/health` + `/slots` base from `LLAMACPP_BASE_URL` (strips `/v1`), so
nothing else moves. To return to llama-server: stop Strata (`pkill -f strata.py`), start
`scripts/serve_qwen4exp.sh`, and set the URL back to `http://localhost:58123/v1` with
`LLAMACPP_API_KEY=not-needed`. Strata's `/slots` has no `n_prompt_tokens_cache`, so the web
status's `prompt_cache_tokens` is `None` on Strata (the per-call *cached* column is unaffected).

## Probe measurements before the benchmark (2026-11-07, idle box)

Agent-shaped requests (long system prompt + tool schemas, short output), both servers on the
same UD-Q4_K_XL files:

| metric | llama-server b11713 (`--numa isolate`, node 1) | Strata 0.1.57 |
|---|---|---|
| decode, tool-call / reasoning output | 13.5–14.7 tok/s | 16.1 tok/s (drafts ~50 % accepted) |
| decode at 16k context | ~14.5 tok/s | 14.5 tok/s |
| prefill at 16k context | 219–315 tok/s | 937 tok/s |
| prefix reuse | yes (`n_prompt_tokens_cache`) | yes (`timings.cache_n`; `cached_tokens` reads 0) |
| OpenAI tool calls / `enable_thinking=false` / `include_usage` | yes | yes |

James's 33.6 tok/s figure was short-prompt prose, where the draft model is accepted far more
often; it does not transfer to agent output.

## 8-question subset (2026-11-07), same examples as the 2026-10-17 subset

LangSmith `llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-strata-subset-2a33b51a` vs
`...-v5-newbuild-subset-a155acd7`. Root-run wall from LangSmith, 8/8 correct both times.

| question | Sept legacy | Oct llama-server | Strata | ×/Oct | LLM calls Oct/Strata | prompt tokens Oct/Strata |
|---|---|---|---|---|---|---|
| serial of sea-dc1-leaf04 | 25.4 s | 58.6 s (cold prefix) | 17.0 s | 3.44 | 2 / 2 | 17k / 18k |
| devices at HVL-SEA-DC1 | 43.1 | 33.0 | 29.1 | 1.13 | 3 / 3 | 27k / 27k |
| active access switches at HVL-SEA-HQ | 73.9 | 183.2 | 60.9 | 3.01 | 12 / 5 | 142k / 46k |
| providers for Dunder-Mifflin circuits | 98.2 | 81.0 | 55.8 | 1.45 | 3 / 3 | 30k / 29k |
| hypervisor hosts with no VMs | 242.1 | 444.3 | 236.7 | 1.88 | 7 / 9 | 216k / 191k |
| two circuit tenants comparison | 173.8 | 113.3 | 55.7 | 2.03 | 4 / 3 | 43k / 30k |
| nested active prefix | 223.5 | 153.6 | 92.8 | 1.65 | 5 / 4 | 79k / 44k |
| branch sites firewall | 405.4 | 113.4 | 134.7 | 0.84 | 4 / 7 | 39k / 68k |
| **sum** | 1,285 | 1,180 | **683** | **1.73** | 40 / 36 | 596k / 456k |

Per model call 29.5 → 19.0 s; per prompt token 1.98 → 1.50 ms. The one slower question is the
model taking seven calls instead of four. Two validator rejections during the run were both
`device_role_id` (should be `role_id`) — a model error, recovered, unrelated to the server.

## Full 90-question v5 run (2026-11-08)

Harness: `EVAL_MODELS=llamacpp:qwen3.8-flash-next-UD-Q4_K_XL EVAL_VARIANT=strata-full
EVAL_MAX_CONCURRENCY=1 ./venv/bin/python -m tests.eval.run_matrix_v5`, 09:57–15:54 UTC.
LangSmith `llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-strata-full-00b39a92`; harness record in
`docs/traces/2026-11-08_netbox-benchmark-v5_strata-full.md`. Compared with the 2026-10-17
`...-v5-newbuild-full-2865e34b` run: same dataset, evaluators and judge (`gpt-oss:20b`).

| | October (llama-server) | Strata |
|---|---|---|
| wall, first start to last end | 5.30 h | 5.91 h |
| agent time, sum of 90 root runs | 14,396 s | **8,603 s (1.67×)** |
| mean / median / max per question | 160.0 / 119.9 / 761 s | **95.6 / 63.1 / 688 s** |
| simple tier mean | 96.7 s | 51.9 s (1.86×) |
| medium tier mean | 167.6 s | 91.4 s (1.83×) |
| advanced tier mean | 215.6 s | 143.5 s (1.50×) |
| questions faster than October | — | 74 of 90 |
| correctness | 0.922 | **0.939** (8 up, 6 down) |
| completeness | 0.944 | 0.972 |
| entity coverage (n=71) | 0.859 | 0.908 |
| tool calls per question | 4.878 | 4.444 |
| tool runs / tool errors | 439 / 0 | 400 / 0 |
| root-run errors | 0 | 0 |
| model calls / seconds inside the model | 411 / 13,938 s | 412 / 7,910 s |
| seconds per model call | 33.9 | **19.2** |
| prompt tokens / completion tokens | 6.57 M / 122.6k | 5.62 M / 121.6k |
| ms per prompt token (incl. cached) | 2.12 | **1.41** |

From the new per-call `timings` (present on 412/412 calls): prompt 1,929 s for 555,474 new
tokens (**288 tok/s**), generation 5,959 s for 121,635 tokens (**20.4 tok/s**); compute accounts
for 7,889 of the 7,910 s inside model calls, so **queue wait was 21 s in total** — Hermes
(James's agent, pinned to the same single slot) did not touch the slot during the run. Strata's
engine log gained 413 request lines against 412 recorded model calls.

### Reading

- The speed-up is the server, not the plan: 412 vs 411 model calls, 400 vs 439 tool runs, and
  each call took 43 % less time.
- Correctness moved 8 up / 6 down on an LLM judge; read as "no regression", not as a gain.
- **Wall time got worse** because the `gpt-oss:20b` judge ran at 100 % CPU through Ollama
  (Strata leaves < 1 GB free per GPU) and competed with Strata's CPU expert path; load average
  36 on 40 threads. Agent time excludes judging and is the number that matters. The 288 tok/s
  prefill under that load is well below the 937 tok/s measured idle.
- Long tool results are the one thing the prefix cache cannot help with, and they are where
  prefill speed matters most: a 14k-token GraphQL result costs ~60 s to read on llama-server,
  ~49 s on Strata under judge load, ~15 s on Strata idle — once; it is cached on later calls
  until compaction changes the prefix. Field selection and page limits are worth as much as
  before.

## What is not claimed

- Nothing about why Strata is faster beyond what its own log states (expert cache 72.8 % hit rate
  during decode, 99.9 % of KV reads from VRAM, draft acceptance). It is a closed binary: no
  flags of ours (e.g. `--numa isolate`, +56 % on llama-server) can be applied, and its log
  reports NUMA placement per node as a known limitation.
- Comparability with llama-server at equal CPU load: the October run had no CPU-resident judge.
- The AGENTS.md cloud-matrix re-run (`EVAL_FORCE_RERUN=1`, `deepseek-v4-flash:cloud`) remains
  owed from the 2026-10-06 validator change; this note does not discharge it.
- Operational: one slot shared with Hermes; the per-call `timings` now make any future
  contention measurable (wall − `prompt_ms` − `predicted_ms`).
