#!/usr/bin/env bash
# Serve Qwen3.8-Flash-Next (qwen4exp) for the NetBox agent's llamacpp backend.
#
# Flags here are MEASURED, not guessed — see ADR-0038 and
# docs/phases/phase-5-production-deepagents/local-frontier-inference.md in
# rtf-research. The two that matter most on this box:
#
#   --numa isolate -t 10   +56% decode. llama.cpp defaults --numa to DISABLED,
#                          so threads straddle both NUMA nodes and stream expert
#                          weights across the socket interconnect. -t 10 == the
#                          physical cores of ONE node; -t 20 and -t 40 are worse.
#   -c 131072              32k is NOT enough. A 12-question stratified run lost
#   --no-kv-offload        3 of 12 questions to context at -c 32768: two hard
#                          overflows and one SILENT truncation (the worse case —
#                          the model then answers from data it no longer has).
#                          At 131072 the same 12 scored 11/12 with ZERO context
#                          failures, peaking at 44,295 tokens.
#   -b 2048 -ub 2048       3.8x PREFILL (34.0 -> 129.7 tok/s on a 9k prompt;
#                          2.8x wall clock on the same request). llama.cpp only
#                          copies CPU-resident expert weights to the GPU once a
#                          microbatch is big enough to amortise the PCIe
#                          transfer; the default -ub 512 never reaches that
#                          threshold, so every microbatch pays full freight.
#                          With 112 GB of experts in RAM this one threshold
#                          dominates prefill — and prefill is where this agent
#                          lives (187,272 prompt tokens vs 21,825 generated in
#                          a 12-question run). Raises peak VRAM during prefill;
#                          2048 was verified to fit alongside -c 131072 on
#                          21 GiB, so do not raise it blindly.
#
# KV cache stays f16 — quantised KV (-ctk/-ctv) is unverified on this hybrid
# Gated-DeltaNet architecture — and lives in SYSTEM RAM via --no-kv-offload.
# The context ceiling was never a VRAM problem: this box has 376 GB of RAM
# against 21 GB of VRAM, so the scarce resource was not the one under pressure.
#
# The cost is real and worth knowing: decode 11.2 -> 7.0 tok/s, and the
# 12-question run went 82 -> 155 min with 60 -> 88 tool calls. It got slower
# because it stopped hitting a wall and started finishing the work.
#
# MEASURED DEAD END — do NOT add `--spec-type ngram-simple`.
# It looks made for this workload (the agent constantly echoes device names,
# IDs and JSON keys back out of tool results) and it is not. Measured on the
# same 9k prompt: 163 drafts proposed, ZERO accepted, decode 5.0 -> 3.8 tok/s
# (-24%) because the model pays verification cost for drafts it always
# rejects. Combined with -ub 2048 it degrades BOTH axes (prefill 129.7 ->
# 101.4, decode 5.9 -> 3.7). ngram-simple needs an exactly-repeating 12-token
# run to predict the next 48; a table of DISTINCT device names has almost
# none. This is not a tuning problem — no --spec-ngram-*-size-n value fixes a
# 0% acceptance rate. Draft-model speculation is separately impossible here:
# common/speculative.cpp throws on vocab mismatch, and no qwen4exp-vocab draft
# model exists (the MTP head PRs #27836/#28243 are still unmerged).
#
# Usage:  scripts/serve_qwen4exp.sh [port]        (default 58123)
set -euo pipefail

PORT="${1:-58123}"
LLAMA_BIN="${LLAMA_BIN:-/home/ola/dev/rnd/llama-cpp/llama.cpp/build-new/bin/llama-server}"
HF_REPO="${HF_REPO:-unsloth/Qwen3.8-Flash-Next-GGUF:UD-Q4_K_XL}"
ALIAS="${ALIAS:-qwen3.8-flash-next-UD-Q4_K_XL}"

[ -x "$LLAMA_BIN" ] || { echo "llama-server not found/executable at $LLAMA_BIN" >&2; exit 1; }

if ss -ltn 2>/dev/null | grep -q ":${PORT}\b"; then
  echo "something is already listening on ${PORT}; stop it first" >&2
  exit 1
fi

echo "serving ${HF_REPO} on 127.0.0.1:${PORT}"
echo "(first load pages ~105 GiB from disk; subsequent starts are warm)"

exec "$LLAMA_BIN" \
  -hf "$HF_REPO" \
  --alias "$ALIAS" \
  --numa isolate -t 10 \
  -ngl 999 -ncmoe 48 \
  -ot 'per_layer_token_embd=CPU' \
  -c 131072 --no-kv-offload -fa auto --jinja \
  -b 2048 -ub 2048 \
  --host 127.0.0.1 --port "$PORT"
