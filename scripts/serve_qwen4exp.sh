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
  --host 127.0.0.1 --port "$PORT"
