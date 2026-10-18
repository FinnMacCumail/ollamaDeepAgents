# llama.cpp --moe-cache-mib A/B on Qwen3.8-Flash-Next (2026-10-17)

Box: 2x Xeon Silver 4210 (Cascade Lake, no AMX), 2x RTX 2080 Ti 11 GB on PCIe 3.0, GPU at PCI 3b on NUMA node 0 and GPU at PCI af on node 1, 376 GB DDR4, kernel.numa_balancing=1.
Model: unsloth/Qwen3.8-Flash-Next-GGUF UD-Q4_K_XL (103.68 GiB, 176.94 B params, 73.4 GB of host experts).
Common flags (mirror the production server): `-ngl 999 -ncmoe 48 -ot per_layer_token_embd=CPU --numa isolate -t 10 -fa 1 -b 2048 -ub 2048 -r 3`.
Builds: old = build-new b11053 (1af554f8f, 2026-09-19); new = build-upstream b11713 (2744e48d1, 2026-10-17).
llama-bench has no cache flag; a 5-line env-var hook (saved as `llama-bench-moe-cache-env-hook.patch` next to the raw logs) set `cparams.moe_cache_size`.
Raw llama-bench tables: `docs/traces/2026-10-17_llama-bench_moe-cache-ab.md`. The llama-bench env-var hook patch is reproduced at the end of this note.

## Results (tokens/s, mean of 3)

| run | build | load mode | GPUs | pinned node | cache (MiB) | hit rate | pp2048 | tg128 | tg128 @ d8192 |
|---|---|---|---|---|---|---|---|---|---|
| old baseline | old | mmap | 2 | default | 0 | - | 176.9 | 11.48 | 10.97 |
| new baseline | new | mmap | 2 | default | 0 | - | 189.0 | 15.92 | 15.72 |
| cache 2 GiB (1.0+1.0) | new | mmap | 2 | default | 2048 | 47-49% | 187.5 | 4.69 | 4.49 |
| cache 4 GiB (2.1+2.0) | new | mmap | 2 | default | 4096 | 70-72% | 189.9 | 7.87 | 7.43 |
| cache 6 GiB (3.2+3.0) | new | mmap | 2 | default | 6144 | 79-80% | 189.3 | 10.19 | 9.77 |
| no cache, pinned memory | new | none | 2 | node 0 | 0 | - | 389.9 | 11.67 | - |
| no cache, pinned memory | new | none | 2 | node 1 | 0 | - | 391.4 | 15.71 | - |
| cache 2.5 GiB, GPU0 only | new | none | 1 (3b) | node 0 | 2560 | 60% | 412.7 | 13.31 | - |
| cache 2.5 GiB, GPU0 only | new | none | 1 (3b) | node 1 | 2560 | 60% | 413.6 | 13.47 | - |
| cache 2.5 GiB split | new | none | 2 | node 0 | 2560 | ~60% | 383.8 | 13.48 | - |
| cache 2.5 GiB split | new | none | 2 | node 1 | 2560 | ~60% | 385.4 | 13.67 | - |

"pinned node" = `taskset -c 0-9,20-29` (node 0) or `taskset -c 10-19,30-39` (node 1) before `--numa isolate`; "default" = no taskset, isolate picks the node the process starts on (decode matches the node-1 rows).
Cache uploads at 2 GiB: ~290 GB for 384 generated tokens (~750 MB per token over PCIe); at 6 GiB: ~113 GB (~290 MB per token).

## Findings

1. The expert cache loses at every size that fits in VRAM. 2 GiB is 3.4x slower than no cache, 6 GiB (the most the 131k-context server could spare, and more) is still 36% slower. Even with pinned host memory and a single local GPU at a 60% hit rate it is 14% slower. Prefill is unaffected (the cache is bypassed for batches above 32 tokens).
2. Cross-socket PCIe is not why: pinning to the GPU's own node versus the far node changed the cached decode by about 1%. The miss path is slow on its own: ~250 expert uploads of ~2.7 MB per token, serialised against compute.
3. The upstream pull alone is worth +39% decode and +7% prefill in llama-bench (11.48 -> 15.92 tg128, 176.9 -> 189.0 pp2048). Production decode was 13.5 tok/s median on the old build.
4. `--load-mode none` (copy weights into pinned RAM instead of mmap) doubles prefill: 189 -> 390 pp2048, decode unchanged. The old server itself warns at startup: "tensor overrides to CPU are used with mmap enabled - consider using --load-mode none". Cost: ~74 GB of anonymous RAM plus a slower cold start.
5. Decode is node-sensitive: pinned to node 1 it is 15.7, pinned to node 0 it is 11.7 (-26%), prefill equal. Likely because node 0 carries the desktop/VS Code/other load, or memory spill; not isolated further. The unpinned default landed on the fast node this time, but that is luck of where the process starts.

## Recommendation

- Switch the server to the new build and add `--load-mode none`; keep `--numa isolate -t 10`; start it under `taskset -c 10-19,30-39` so isolate lands on node 1 deterministically. Expected: ~2x prefill and ~+20-40% decode versus today, no quality change.
- Do not enable `--moe-cache-mib` on this hardware.
- Re-verify after the switch with the production context (`-c 131072`), where KV and the 2048 ubatch compute buffers leave less VRAM than llama-bench had.

## Follow-up: production switch and agent rerun (2026-10-17, later the same day)

Server now runs build-upstream b11713 with `--load-mode none` under `taskset -c 10-19,30-39`
(script: ollamaDeepAgents/scripts/serve_qwen4exp.sh, uncommitted). Caches were dropped once so
the 74 GB pinned buffer sits on node 1.

Real agent traffic, from llama-server print_timing lines (legacy = old server log over 24 days,
new = today's log incl. the 8-question rerun):

| metric | legacy | new |
|---|---|---|
| prefill, requests with >=256 new tokens, aggregate | 96.9 tok/s (n=601) | 218.5 tok/s (n=22) |
| prefill, requests with >=4000 new tokens, aggregate | 113.3 tok/s | 242.0 tok/s |
| decode, requests with >=32 generated, aggregate | 13.64 tok/s (n=1047) | 14.60 tok/s (n=43) |
| decode median | 14.28 | 14.62 |

Eight v5 questions rerun through the agent (LangSmith experiment
`llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-newbuild-subset-a155acd7`, all 8 correct):
sum of agent wall 1285 s -> 1180 s (1.09x), but the new run made 40 LLM calls vs 35 and read
597k vs 412k prompt tokens (the model chose 12 tool calls instead of 4 on one question, 7 vs 6
with 3x the tool-result tokens on another), and its first question paid the cold prefix.
Per LLM call: 35.7 s -> 28.5 s. Per prompt token: 3.0 -> 1.9 ms. Questions with the same call
count both times: 1.22x, 1.34x, 1.56x faster.
Conclusion: inference is ~2.2x faster at prefill and ~+7% at decode; end-to-end turn time is
dominated by how many calls the model decides to make, which these changes do not touch.

## Appendix: the llama-bench hook used for the cache runs

llama-bench has no `--moe-cache-mib`; this uncommitted 5-line patch read the size from `LLAMA_BENCH_MOE_CACHE_MIB` and was reverted after the runs.

```diff
diff --git a/tools/llama-bench/llama-bench.cpp b/tools/llama-bench/llama-bench.cpp
index 96ae4870f..1992b2adc 100644
--- a/tools/llama-bench/llama-bench.cpp
+++ b/tools/llama-bench/llama-bench.cpp
@@ -1316,6 +1316,11 @@ struct cmd_params_instance {
         cparams.op_offload      = !no_op_offload;
         cparams.swa_full        = false;
 
+        // TEMP local A/B hook: set the MoE expert cache size from the environment
+        if (const char * mcm = getenv("LLAMA_BENCH_MOE_CACHE_MIB")) {
+            cparams.moe_cache_size = (size_t) atoll(mcm) * 1024 * 1024;
+        }
+
         return cparams;
     }
 };
```

## Addendum: kernel.numa_balancing=0 (2026-10-17, evening)

Five 200-token generations on the running server (pinned to node 1, weights node-local), same
prompts each time:

| state | median tok/s | range |
|---|---|---|
| numa_balancing=1 | 14.45 | 14.13-14.86 |
| numa_balancing=1, repeated | 14.65 | 14.65-14.80 |
| numa_balancing=0 | 14.72 | 14.67-14.80 |

No material effect: +2% median, inside the spread of the two runs taken with the setting on.
With the process already pinned and its memory already on the same node, the balancer had
nothing to fix and apparently little to cost. Left off (harmless, and llama-server warns about
it), but not persisted across reboots; nothing in the serve script depends on it.

## Full 90-question v5 rerun on the new configuration (2026-10-17/18)

Harness: `EVAL_MODELS=llamacpp:qwen3.8-flash-next-UD-Q4_K_XL EVAL_VARIANT=newbuild-full
EVAL_FORCE_RERUN=1 EVAL_MAX_CONCURRENCY=1 python -m tests.eval.run_matrix_v5`. Experiment
`llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-newbuild-full-2865e34b`; scored trace in
`docs/traces/2026-10-17_netbox-benchmark-v5_newbuild-full.md`. Server: build b11713,
`--load-mode none`, taskset node 1, `kernel.numa_balancing=0`. Compared against the 2026-09-23
run `...-v5-kvvram-full-31701ffc` (same dataset, same evaluators, same judge), root-run
latencies from LangSmith.

| | September (old build, mmap) | October (new config) |
|---|---|---|
| wall, first start to last end | 6.78 h | **5.30 h** |
| agent time, sum of 90 root runs | 19,345 s | **14,396 s** (1.34x) |
| mean / median / max per question | 214.9 / 152.7 / 1,588 s | **160.0 / 119.9 / 761 s** |
| simple tier, mean | 108.5 s | 96.7 s (1.12x) |
| medium tier, mean | 205.9 s | 167.6 s (1.23x) |
| advanced tier, mean | 330.5 s | **215.6 s (1.53x)** |
| questions faster than September | - | 73 of 90 |
| correctness | 0.906 | **0.922** (5 up, 4 down) |
| completeness | 0.944 | 0.944 |
| entity coverage (n=71) | 0.866 | 0.859 |
| tool calls per question | 5.522 | **4.878** |
| root-run errors | 0 | 0 |
| model calls / seconds inside the model | 462 / 18,869 s | 411 / 13,938 s |
| seconds per model call | 40.8 | **33.9** |
| ms per prompt token (incl. cached) | 2.77 | **2.12** |

Reading: the per-call gain (1.20x) is the server change; the rest of the 1.34x comes from the
model making 11% fewer calls this time, which is run-to-run planning variance in the same
direction. The advanced tier gains most because its turns prefill the largest tool results.
Correctness movement is nine questions in both directions, i.e. judge and planning noise around
the same ~0.91 level, not a quality change. The September 26-minute outlier (IP addresses
outside every prefix) took 761 s this time.

**Attribution: the server change, not ADR-0041.** The September run predates the `__in`
rejection (2026-10-06), so both are in the October run. They act on different quantities. In
September the model used `__in` in 8 of 497 tool calls across 5 questions, 3 of them returning
the oversized unfiltered result; October used it 0 times. Yet October read *more* tool text, not
less: 61 tool results over 20k characters vs 45, 6.2M vs 4.9M characters in total. The rates
only the server can change moved (40.8 -> 33.9 s per model call, 2.77 -> 2.12 ms per prompt
token), and 73 of 90 questions got faster while the fix could touch at most 5. The one entangled
quantity is the call count (462 -> 411), where the fix is a bounded contributor on those 5
questions and run-to-run planning variance is the rest.
