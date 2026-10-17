# llama-bench raw output — --moe-cache-mib A/B and NUMA affinity, 2026-10-17

Companion to `docs/development/2026-10-17_moe-cache-ab-and-server-switch.md`. Each block is one `llama-bench` invocation; common flags `-ngl 999 -ncmoe 48 -ot per_layer_token_embd=CPU --numa isolate -t 10 -fa 1 -b 2048 -ub 2048 -r 3`.

## old

build-new b11053, mmap, no cache

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |          pp2048 |        176.90 ± 5.18 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |           tg128 |         11.48 ± 0.06 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |  pp2048 @ d8192 |        170.35 ± 1.35 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |   tg128 @ d8192 |         10.97 ± 0.08 |

build: 1af554f8f (11053)

```
```

## 0

build-upstream b11713, mmap, LLAMA_BENCH_MOE_CACHE_MIB=0 split across both GPUs

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |          pp2048 |        188.96 ± 4.36 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |           tg128 |         15.92 ± 0.01 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |  pp2048 @ d8192 |        181.17 ± 1.82 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |   tg128 @ d8192 |         15.72 ± 0.02 |

build: 2744e48d1 (11713)

```
```

## 2048

build-upstream b11713, mmap, LLAMA_BENCH_MOE_CACHE_MIB=2048 split across both GPUs

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |          pp2048 |        187.45 ± 4.36 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |           tg128 |          4.69 ± 0.06 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |  pp2048 @ d8192 |        179.38 ± 1.53 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |   tg128 @ d8192 |          4.49 ± 0.05 |

build: 2744e48d1 (11713)

```
      4 impl:      CUDA0 MoE cache size =  1059.18 MiB for 38200.00 MiB of host experts
      3 impl:      CUDA1 MoE cache size =   981.45 MiB for 35250.00 MiB of host experts
      1 llama_moe_cache: ubatch <= 8: hits = 90539, misses = 94261, hit rate = 48.99%, uploaded = 282601.37 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 86380, misses = 98420, hit rate = 46.74%, uploaded = 294881.64 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 60, misses = 20, hit rate = 75.00%, uploaded = 68.36 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 22, misses = 18, hit rate = 55.00%, uploaded = 61.52 MiB
```

## 4096

build-upstream b11713, mmap, LLAMA_BENCH_MOE_CACHE_MIB=4096 split across both GPUs

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |          pp2048 |        189.90 ± 4.35 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |           tg128 |          7.87 ± 0.31 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |  pp2048 @ d8192 |        181.83 ± 1.21 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |   tg128 @ d8192 |          7.43 ± 0.25 |

build: 2744e48d1 (11713)

```
      4 impl:      CUDA0 MoE cache size =  2118.36 MiB for 38200.00 MiB of host experts
      2 impl:      CUDA1 MoE cache size =  1969.24 MiB for 35250.00 MiB of host experts
      1 llama_moe_cache: ubatch <= 8: hits = 60, misses = 20, hit rate = 75.00%, uploaded = 68.36 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 22, misses = 18, hit rate = 55.00%, uploaded = 61.52 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 133520, misses = 51280, hit rate = 72.25%, uploaded = 154694.04 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 130098, misses = 54702, hit rate = 70.40%, uploaded = 164603.81 MiB
```

## 6144

build-upstream b11713, mmap, LLAMA_BENCH_MOE_CACHE_MIB=6144 split across both GPUs

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |          pp2048 |        189.33 ± 4.39 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |           tg128 |         10.19 ± 0.47 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |  pp2048 @ d8192 |        181.16 ± 1.28 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |   tg128 @ d8192 |          9.77 ± 0.55 |

build: 2744e48d1 (11713)

```
      3 impl:      CUDA1 MoE cache size =  2954.10 MiB for 35250.00 MiB of host experts
      3 impl:      CUDA0 MoE cache size =  3177.54 MiB for 38200.00 MiB of host experts
      1 llama_moe_cache: ubatch <= 8: hits = 60, misses = 20, hit rate = 75.00%, uploaded = 68.36 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 22, misses = 18, hit rate = 55.00%, uploaded = 61.52 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 148408, misses = 36392, hit rate = 80.31%, uploaded = 110145.41 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 146447, misses = 38353, hit rate = 79.25%, uploaded = 115655.47 MiB
```

## n0_both

b11713, -lm none, taskset node 0, no cache

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |         lm |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | ---------: | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |       none |          pp2048 |        389.89 ± 8.53 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |       none |           tg128 |         11.67 ± 0.22 |

build: 2744e48d1 (11713)

```
```

## n1_both

b11713, -lm none, taskset node 1, no cache

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ot                    |         lm |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | --------------------- | ---------: | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |       none |          pp2048 |        391.43 ± 6.72 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | per_layer_token_embd=CPU |       none |           tg128 |         15.71 ± 0.09 |

build: 2744e48d1 (11713)

```
```

## n0_gpu0_c2560

b11713, -lm none, taskset node 0, cache 2560 MiB; -ts 1,0 parsed as two configs: GPU0 only, then default split

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ts           | ot                    |         lm |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | ------------ | --------------------- | ---------: | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 1.00         | per_layer_token_embd=CPU |       none |          pp2048 |        412.67 ± 8.12 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 1.00         | per_layer_token_embd=CPU |       none |           tg128 |         13.31 ± 0.26 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 0.00         | per_layer_token_embd=CPU |       none |          pp2048 |        383.82 ± 6.45 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 0.00         | per_layer_token_embd=CPU |       none |           tg128 |         13.48 ± 0.32 |

build: 2744e48d1 (11713)

```
      2 llama_moe_cache: ubatch <= 8: hits = 22, misses = 18, hit rate = 55.00%, uploaded = 61.52 MiB
      2 impl:      CUDA0 MoE cache size =  2554.49 MiB for 73450.00 MiB of host experts
      2 impl:      CUDA0 MoE cache size =  1318.17 MiB for 38200.00 MiB of host experts
      1 llama_moe_cache: ubatch <= 8: hits = 110808, misses = 73992, hit rate = 59.96%, uploaded = 222655.27 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 109205, misses = 75595, hit rate = 59.09%, uploaded = 227215.33 MiB
      1 impl:      CUDA1 MoE cache size =  1232.91 MiB for 35250.00 MiB of host experts
```

## n1_gpu0_c2560

b11713, -lm none, taskset node 1, cache 2560 MiB; same two configs

| model                          |       size |     params | backend    | ngl |  n_cpu_moe | threads | n_ubatch |  fa | ts           | ot                    |         lm |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | --: | ------------ | --------------------- | ---------: | --------------: | -------------------: |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 1.00         | per_layer_token_embd=CPU |       none |          pp2048 |        413.61 ± 7.89 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 1.00         | per_layer_token_embd=CPU |       none |           tg128 |         13.47 ± 0.25 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 0.00         | per_layer_token_embd=CPU |       none |          pp2048 |        385.36 ± 6.73 |
| qwen4exp A3B Q4_K - Medium     | 103.68 GiB |   176.94 B | CUDA       | 999 |         48 |      10 |     2048 |   1 | 0.00         | per_layer_token_embd=CPU |       none |           tg128 |         13.67 ± 0.32 |

build: 2744e48d1 (11713)

```
      2 llama_moe_cache: ubatch <= 8: hits = 22, misses = 18, hit rate = 55.00%, uploaded = 61.52 MiB
      2 impl:      CUDA0 MoE cache size =  2554.49 MiB for 73450.00 MiB of host experts
      2 impl:      CUDA0 MoE cache size =  1318.17 MiB for 38200.00 MiB of host experts
      1 llama_moe_cache: ubatch <= 8: hits = 110808, misses = 73992, hit rate = 59.96%, uploaded = 222655.27 MiB
      1 llama_moe_cache: ubatch <= 8: hits = 109205, misses = 75595, hit rate = 59.09%, uploaded = 227215.33 MiB
      1 impl:      CUDA1 MoE cache size =  1232.91 MiB for 35250.00 MiB of host experts
```
