# Self-Hosting Frontier LLMs — Open Weights & GPU Rental Research

**Date:** 2026-06-08
**Status:** Research complete, recommendations pending implementation
**Author:** Three parallel web-research streams (open-weights audit, GPU rental pricing, inference stack)
**Purpose:** Determine which of the cloud LLMs from the `netbox-benchmark-v2` 10-model leaderboard could be self-hosted on rented GPU hardware, what the realistic configurations and costs look like, and whether self-hosting is economically rational for this project's NetBox agent workload

**Related:**
- `2026-06-03_langsmith-evaluation-research.md` — model-matrix evaluation plan that produced the leaderboard
- `2026-06-03_quickjs-code-interpreter-research.md` — orthogonal latency-reduction lever within DeepAgents

---

## Context

The 10-model cloud matrix sweep (run via `tests/eval/run_matrix.py` against `netbox-benchmark-v2`) finished 2026-06-08 at 06:33 BST and produced a sortable leaderboard. The clear winners on quality-vs-cost were `deepseek-v4-flash:cloud` (rank 1, entity 0.95 / completeness 1.00 / 34.6s) and `deepseek-v4-pro:cloud` (rank 2, identical quality, 54.5s). Three other models scored well: `minimax-m3:cloud`, `nemotron-3-ultra:cloud`, and `glm-5:cloud`.

The natural next question — given hot/cold quota friction during the matrix run, and the project's earlier postulate that "the privacy thesis is on hold pending hardware that could run a 600B+ MoE locally" — is whether any of these frontier models can be self-hosted on rented GPU hardware at meaningful cost. The Ollama Cloud session-limit pain during the matrix sweep is one of the operational signals that pushed this question forward.

Three areas needed factual research:

1. **Open-weights availability** — which leaderboard models actually have downloadable weights, with what license, at what parameter scale
2. **GPU rental market pricing** — current (June 2026) per-hour rates across providers, including new entrants
3. **Inference stack feasibility** — what GPU configuration is realistic per model, what software runs it, what throughput to expect

This document captures the findings and the economic verdict for this project's specific workload.

---

## 1. Open-weights audit — what's actually self-hostable

| Leaderboard model | Open weights? | License | Total / Active params | Architecture | HF repo |
|---|---|---|---|---|---|
| `deepseek-v4-flash` | **Yes** | MIT | 284B / 13B MoE | MoE + hybrid CSA/HCA attention, text-only, 1M ctx | `deepseek-ai/DeepSeek-V4-Flash` (FP4+FP8 mixed, ~158-160 GB on disk) |
| `deepseek-v4-pro` | **Yes** | MIT | 1.6T / 49B MoE | Same family as Flash, 1M ctx | `deepseek-ai/DeepSeek-V4-Pro` (64 shards, ~865 GB FP4+FP8) |
| `minimax-m3` | **Not yet** (promised) | TBD | Undisclosed | MoE w/ MSA, natively multimodal | `MiniMaxAI/MiniMax-M3` — returns 401, weights "within ~10 days" of 2026-06-01 launch → expected ~2026-06-11 |
| `nemotron-3-ultra` | **Yes** | OpenMDW-1.1 (commercial OK) | **550B / 55B MoE** (hybrid Mamba-Transformer with MTP) | Text-only, multilingual, 1M ctx | `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16` + NVFP4, Base, GenRM variants; `unsloth/...-GGUF` builds |
| `glm-5` | **Yes** | MIT (most permissive) | 744B / 40B MoE | DeepSeek Sparse Attention (DSA), text-only, 200K ctx | `zai-org/GLM-5` (BF16) and `zai-org/GLM-5-FP8` |

### Correction to a prior assumption

Nemotron-3-Ultra is a **550B MoE with hybrid Mamba-Transformer** architecture — NOT a 340B dense model as earlier discussion in this project speculated. NVIDIA shipped four official checkpoint variants on HF day-one (BF16 instruct, BF16 base, NVFP4 quantized, GenRM reward model) plus Unsloth has GGUF builds (UD-Q4_K_M) for llama.cpp. The NVFP4 variant is designed to run on Blackwell (B200/GB200) at near-BF16 quality, ~4× smaller footprint. This corrects the matrix interpretation: Nemotron's latency profile reflects MoE scaling, not dense compute.

### Per-model self-host notes

**DeepSeek-V4-Flash (284B/13B MoE).** Most practical of the bunch. 160 GB on-disk footprint fits a single 8×H100/H200 node (640 GB HBM) comfortably with room for KV cache, and because it's MoE only ~13B params are active per token so throughput is closer to a 13B dense model. vLLM, SGLang, and llama.cpp quantizations all work with safetensors out of the box. Strong agentic/coding scores (SWE-Bench Verified 79.0%) make it the V4-family pick for cost-sensitive self-hosting.

**DeepSeek-V4-Pro (1.6T/49B MoE).** Open but at the practical edge. ~865 GB BF16 footprint forces multi-node (8×B200 or 16×H100 minimum) or aggressive INT4/FP4 quantization to fit on one node. Inference compute scales with the 49B active params (≈3× Flash), but VRAM scales with total. This is the model where "rent GPU vs. pay Ollama" math gets hardest — you basically need a dense B200 box. If you don't need frontier benchmark scores, Flash dominates on $/token.

**MiniMax-M3.** Cannot currently self-host. HF page `MiniMaxAI/MiniMax-M3` returns 401 (not yet public). Predecessor MiniMax-Text-01 (456B/46B MoE) is a sizing proxy. Architecturally M3 is natively multimodal (image + video) — adds VRAM overhead vs. a text-only equivalent. Re-check `huggingface.co/MiniMaxAI` after 2026-06-11.

**NVIDIA Nemotron-3-Ultra (550B/55B MoE).** Cleanest self-host story. Four checkpoint variants on HF day-one, plus official vLLM/SGLang/TensorRT-LLM cookbooks. NVFP4 quant runs on Blackwell at ~4× smaller footprint. OpenMDW-1.1 license permits commercial use. Hybrid Mamba-2/Transformer/MoE means lower KV-cache cost than pure Transformer at 1M context — inference stacks need to be Mamba-aware (vLLM ≥0.22, SGLang ≥0.5.12). Min hardware: 8×H200 or 8×B200, or 16×H100.

**GLM-5 (744B/40B MoE).** Largest open MoE here after V4-Pro, but 40B active means inference throughput similar to Flash. MIT license is maximally permissive (no commercial restriction). BF16 footprint ~1.5 TB, FP8 variant roughly halves that. Context "only" 200K vs. 1M offered by others — for most uses plenty, but if 1M context is your reason for Ollama Cloud, GLM-5 is the wrong pick. Quantized builds explicitly compatible with llama.cpp, Ollama, LM Studio.

---

## 2. VRAM math by quantization (64K context anchor)

For each candidate model, weights dominate VRAM at realistic agent-workload context lengths (KV cache stays small for these MoE attention designs).

### Context-anchor justification

Earlier drafts of this doc used a 32K context anchor as a "reasonable for tool-call agents" estimate. Measurement against the actual `netbox-benchmark-v2` LangSmith experiments shows that assumption was too low. Peak prompt-token sizes per query, measured from the LLM call sub-traces of the `deepseek-v4-pro:cloud` experiment (`ollama-deepseek-v4-pro-cloud-941e58fc`):

| Query | LLM calls | Peak prompt tokens |
|---|---|---|
| Device IP lookup (dmi01-nashua-rtr01) | 7 | 17,674 |
| Rack elevation (Comms closet) | 4 | 22,355 |
| VLAN 100 / Jimbob's Banking | 5 | 30,547 |
| **Dunder Mifflin multi-aspect** | **5** | **55,264** |

The multi-aspect decomposition genuinely needs 55K+ tokens at peak — half a dozen NetBox tool messages of 5-20 KB JSON each, plus the system prompt (~1.5K tokens) and loaded skill body (~6K tokens), accumulate fast. **64K is the more honest anchor** with mild headroom for query-class variance.

### Why the GPU tier recommendations don't change at 64K

The candidates here use attention architectures that keep KV cache near-constant relative to weight VRAM even at higher context:

- **DeepSeek-V4 (Flash + Pro)** — hybrid CSA+HCA attention compresses KV cache to ~2% of vanilla GQA. At full 1M context KV cache is ~10 GB on V4-Flash; at 64K it's ~0.6 GB.
- **GLM-5** — DeepSeek Sparse Attention (DSA), similar compression behaviour to V4.
- **Nemotron-3-Ultra** — hybrid Mamba-2/Transformer; most layers use constant-size Mamba state, not linear-in-context KV cache.

So the per-model tables below stay accurate at 64K — the "+ KV/overhead" columns are dominated by activation buffers, workspace memory, and CUDA graph captures (NOT primarily KV cache). A move from 32K → 64K → 128K shifts those columns by under 1 GB on any of these models.

### Where the 64K anchor would start to matter

- **Full 1M context** (very long conversations without reset, or large document-context dumps) pushes KV cache to ~10 GB on V4-Flash. That eats into headroom margin on tight configs like 2× H200.
- **A future leaderboard model with standard MHA or GQA** (no attention compression) at the same 55K context would consume 5-10× more KV cache. Re-check the math per-architecture before adopting.
- **Concurrent users** — KV cache is per-request. Two simultaneous Dunder-Mifflin-class queries at 55K each ≈ doubled KV pressure. The matrix harness only runs one query at a time (`EVAL_MAX_CONCURRENCY=1`); the production agent likewise. A multi-user deployment changes the math.

### Math basis
- Weights: `total_params × bytes_per_param` (FP16=2, FP8/INT8=1, INT4=0.5). MoE total params count — all expert weights must be VRAM-resident for the router, even though only ~5-10% activate per token.
- KV cache: dominated by attention design. DeepSeek MLA compresses to ~512 floats per token per layer vs. standard MHA's ~32K floats. V4's hybrid CSA+HCA cuts KV cache to ~10% of V3.2's, ~2% of vanilla GQA. GLM-5 uses DSA (DeepSeek's sparse attention). Nemotron-3-Ultra is hybrid Mamba-Transformer (most layers Mamba → small constant state, not linear-in-context KV).

### DeepSeek-V4-Flash

| Quant | Weights | + KV/overhead | Total VRAM | Realistic GPU |
|---|---|---|---|---|
| BF16 | ~520-570 GB | ~70 GB | ~640 GB | 8× H100/H200 80GB |
| FP8 mixed | ~290-295 GB | ~25 GB | ~320 GB | 4× H100/A100 80GB |
| **FP4+FP8 native (shipped)** | **~158-160 GB** | **~12-15 GB** | **~170-175 GB** | **2× H200 141GB or 4× A100 80GB** |
| INT4/Q4 GGUF | ~80 GB | ~10 GB | ~90-100 GB | 2× RTX 6000 Ada 48GB |
| Q3 GGUF | ~60 GB | ~10 GB | ~80-96 GB | 1× H100 80GB |
| Q2 | ~40 GB | ~8 GB | ~48-64 GB | 1× RTX 6000 Ada 48GB |

### DeepSeek-V4-Pro

| Quant | Weights | Total VRAM | Realistic GPU |
|---|---|---|---|
| BF16 | ~3.2 TB | ~3.5 TB+ | Multi-node only |
| FP8 mixed | ~1.6 TB | ~1.7 TB+ | Multi-node H200/B200 |
| **FP4+FP8 native** | **~862 GB** | **~1.0-1.2 TB** | **8× H200 141GB single node or GB200 NVL4 tray** |
| INT4 | ~430 GB | ~512-640 GB | 8× H100 80GB (tight) |
| Q2 | ~216 GB | ~256-320 GB | 4× H100 80GB |

### GLM-5

| Quant | Weights | Total VRAM | Realistic GPU |
|---|---|---|---|
| BF16 | ~1.5 TB | ~1.6 TB | Multi-node |
| **FP8** | **~800 GB** | **~850 GB** | **10× H100 80GB (tight) or 8× H200** |
| INT4 (AWQ) | ~200 GB | ~250-300 GB | 4× H100 80GB or 8× A100 |
| Q2 GGUF | ~100 GB | ~120 GB | 2× H100 80GB or 1× 24 GB GPU + 256 GB RAM offload |

### Nemotron-3-Ultra

Hybrid Mamba-Transformer means KV cache grows much slower than a pure transformer.

| Quant | Weights | Total VRAM | Realistic GPU |
|---|---|---|---|
| BF16 | ~1.1 TB | ~1.2 TB | 16× H100 or 8× B200 |
| FP8 | ~550 GB | ~600 GB | 8× H100 80GB (tight) or 8× H200 141GB |
| **NVFP4 (official)** | **~275 GB** | **~310 GB** | **4× H100/H200 or 4× B200** |
| INT4 GGUF (unsloth) | ~275 GB | ~310 GB | Same |

### MiniMax-M3

Unverified. Weights not yet public.

---

## 3. Inference framework recommendations

| Model | Best framework | Notes |
|---|---|---|
| **DeepSeek-V4-Flash** | **SGLang** (day-0 LMSYS recipe) or **vLLM recipes** | SGLang's `lmsysorg.mintlify.app/cookbook/.../DeepSeek-V4` is canonical. KTransformers added V4-Flash on 2026-05-02 for CPU-offload tier. ik_llama.cpp WIP. |
| **DeepSeek-V4-Pro** | **TensorRT-LLM** on B200/GB200 or **SGLang** | At 1.6T you're forced to multi-node; TensorRT-LLM has DeepSeek-V3.2 + Blackwell optimization track. vLLM recipes target a GB200 NVL4 tray. |
| **GLM-5** | **vLLM ≥ 0.19.0** or **SGLang ≥ 0.5.10** | Both have official support per Lushbinary's self-hosting guide. |
| **Nemotron-3-Ultra** | **vLLM (day-0, 2026-06-04)** or **TensorRT-LLM** | NVIDIA shipped vLLM/SGLang/TensorRT-LLM cookbooks simultaneously; Mamba hybrid means TensorRT-LLM likely has best kernel optimization. |
| **MiniMax-M3** | **Unverified** until weights drop | M2/M2.7 used vLLM + SGLang day-0; assume same. |

**CPU-offload tier (the cheap path for MoE).** KTransformers is purpose-built (Tsinghua, SOSP'25 paper). ik_llama.cpp for GGUF-quant heavy CPU work. MLX for Apple Silicon only. llama.cpp upstream has WIP branch for V4 — not yet merged as of 2026-06-08.

---

## 4. Throughput expectations (single batch decode, real benchmarks)

| Model + Config | Tok/s | Source |
|---|---|---|
| DeepSeek-V4-Flash, SGLang, 2× H200, FP4+FP8 + spec decoding | **266** (240 w/ spec overhead) | LMSYS day-0 blog |
| DeepSeek-V4-Pro, SGLang, 8× B200, FP4+FP8 + spec decoding | **199** (180 w/ spec) | LMSYS |
| DeepSeek-V4-Flash, KTransformers, 1× RTX 5090 + 256 GB DDR5 | **20+** | KTransformers official docs |
| DeepSeek-V4-Flash, KTransformers, 8× RTX 5090 + MTP/EAGLE | ~32 | KTransformers docs |
| DeepSeek-V3 671B, SGLang, 8× H100, batch=1 | ~13-33 (varies) | SGLang #3196 / #3102 |
| DeepSeek-R1, TensorRT-LLM, 8× B200, latency-tuned | **368 per user** | NVIDIA TensorRT-LLM tech blog |
| DeepSeek-V3 4-bit MLX, M3 Ultra 512 GB | ~20 small context, drops at 16K+ | Awni Hannun / VentureBeat |
| Nemotron-3-Ultra served via Blackbox AI | **400+ per user** | artificialanalysis.ai |
| GLM-5 on M3 Ultra 192 GB heavy quant | **<1** | codersera / lalatenduswain |

For a 5-10 tool-call workflow at ~500-2000 output tokens per call (the NetBox agent's pattern): a 200+ tok/s config completes each call in 2-10s plus TTFT (typically 2-5s on SGLang V3-class). The 20 tok/s offload tier yields 25-100s per-call latency — workable for batch agents, painful for interactive.

**TTFT caveat.** SGLang on DeepSeek-V3 at H100 measured TTFT 2-5s and ITL ~100ms — effective ~10 tok/s for short responses. For tool-call agents where each turn is short, TTFT matters more than steady-state throughput. **TensorRT-LLM on Blackwell is the only stack documented at sub-second TTFT for DeepSeek-class.**

---

## 5. GPU rental pricing matrix (June 2026)

### Marketplaces & community clouds (cheapest tier)

| Provider | H100 80GB | H200 141GB | B200 192GB | A100 80GB | RTX 4090 | RTX 5090 | Notes |
|---|---|---|---|---|---|---|---|
| **Vast.ai** | $1.47-$2.27 | per-host | rare | $0.78-$1.50 | $0.18-$0.58 | $0.51-$0.89 | Peer-to-peer marketplace. Reliability varies by host score. Interruptible = lowest. |
| **RunPod Community** | PCIe $1.99, SXM $2.69 spot | $4.39 / $3.59 spot | $5.89 spot | $1.39-$1.49 | $0.69 | $0.99 | Multi-tenant. Per-second billing. Storage $0.05-$0.14/GB-mo. |
| **RunPod Secure** | PCIe $2.89, SXM $3.29 | $4.39 | $5.89 | $1.39-$1.49 | n/a | n/a | Dedicated. ~47% premium over Community. |
| **Hyperbolic** | $1.49-$1.99 (weekly refresh) | **$2.15** | listed | n/a | $0.30-$0.35 | n/a | Decentralized; quality varies by supplier. |
| **TensorDock** | SXM5 $2.25 / $1.91 spot; reserved $1.50-$2.00 | not published | not published | ~$0.90 | listed | n/a | Per-second billing. Bare-metal 8× H100 from $12-$16/hr. |
| **Thunder Compute** | **$1.38** | listed | n/a | $0.78 | listed | n/a | Aggressively cheap; newer neocloud. |
| **Spheron** | SXM $2.50 / spot $1.03 | $4.54 | $6.02 / spot $2.12 | $1.07 / spot $0.60 | $0.55 | $0.76 | Decentralized; spot floor among lowest published. |

### Mid-tier / dedicated neoclouds

| Provider | H100 80GB | H200 | B200 | A100 80GB | Notes |
|---|---|---|---|---|---|
| **Lambda On-Demand** | SXM $3.99-$4.29, PCIe $3.29 | clusters only | SXM6 $6.69-$6.99 | $2.79 | GH200 $2.29. |
| **CoreWeave** | 8x node $49.24/hr ≈ $6.16/GPU; spot $19.71/hr ≈ $2.46 | 8x $50.44/hr ≈ $6.31 | 8x $68.80/hr ≈ $8.60 | 8x $21.60/hr ≈ $2.70 | No egress fee. Reserved up to 60% off. |
| **Crusoe Cloud** | $3.90 | $4.29 | contact | SXM $2.30 | Per-minute billing. No ingress/egress. |
| **Together AI Clusters** | $5.49 on-demand / reserved $3.99-$4.99 | $6.79 / $4.55-$5.95 | $9.95 / $9.09-$9.65 | not published | 6-day minimum reserved. Storage $0.16/GiB-mo. |
| **Modal (serverless)** | $3.95/hr ($0.001097/s) | $4.54/hr | $6.25/hr | 80GB $2.50/hr | Per-ms billing, no idle charge. Volumes $0.09/GiB-mo (1 TiB free). |

### Hyperscalers (premium reference)

| Provider | H100 80GB | H200 | B200 | A100 80GB | Notes |
|---|---|---|---|---|---|
| **AWS p5.48xlarge (8× H100)** | $55.04/hr ($6.88/GPU); spot $23.86/hr | p5e ~$39.80/GPU; p5en ~$41.61 | p6-b200 ~$14.24/GPU; spot $3.24 | p4d/p4de $4.10-$5.12/GPU | Capacity Blocks often required. June-2025 price cut: P5 -45%, P4 -33%. |
| **Azure ND H100 v5** | $6.98/GPU | ND H200 ~$13.78 | not yet | $3.67/GPU; spot $0.74 | Spot heavily discounted. |
| **Oracle BM.GPU.H100.8** | $10.00/GPU | listed | listed | listed | Bare-metal; expensive. MI300X 8-GPU $48/hr ($6/GPU). |

### Best-value summary

| GPU tier | Cheapest credible | Mid-confidence | Premium reference |
|---|---|---|---|
| **1× H100 80GB** | **Thunder Compute $1.38** or Hyperbolic $1.49-$1.99 | RunPod Community $1.99 | AWS p5 ~$6.88 |
| **8× H100 bare-metal** | **TensorDock 1-mo reserved $16/hr ($2/GPU)** | Lambda OnDemand $31.92/hr | AWS p5.48xlarge $55.04/hr |
| **1× H200 141GB** | **Hyperbolic $2.15** | GMI Cloud $2.60 | AWS p5e ~$4.98 |
| **1× B200 192GB** | **Spheron spot $2.12** or Lambda $6.69 | RunPod $5.89 | AWS p6-b200 $14.24 |
| **1× A100 80GB** | **Thunder $0.78** or Spheron spot $0.60 | Crusoe $2.00 | AWS p4de $5.12 |
| **RTX 5090** | **Vast.ai $0.51-$0.89** | RunPod $0.99 | Not on hyperscalers |

### Hidden-cost gotchas (read before committing)

1. **AWS Capacity Blocks now mandatory for P5/P5e in many regions.** Headline $55.04/hr p5.48xlarge requires confirmed inventory; Capacity Blocks premium = $31.46/hr minimum.
2. **Hyperscaler egress: $0.05-$0.09/GB.** For LLM inference streaming long completions, 100 GB/day = ~$15/day. CoreWeave, Crusoe, and Modal advertise zero egress.
3. **RunPod Secure premium = 35-50% over Community** — only pay for isolation/SLA/persistent IPs.
4. **Reserved pricing requires committed billing** — TensorDock's $1.50/hr 3-yr H100 only beats spot if you actually run 24/7 for 3 years.
5. **Marketplace pricing is per-host, not per-platform.** Vast.ai's "$1.47/hr H100" might be a single host promo; median sits closer to $2.10.
6. **Serverless cold starts** — Modal/RunPod Serverless cold container loading 30-80 GB model = 30-60s GPU time per cold start. Pre-warming negates the "no idle" advantage.
7. **Spot eviction** — Vast, AWS, GCP, CoreWeave, Spheron all preemptible with 30 sec to 2 min notice.
8. **Decentralized marketplaces** — Hyperbolic/Vast/Spheron benchmarks vary 30-50% by host quality even at same nominal GPU.
9. **CoreWeave 8× node trap** — they price nodes, not GPUs. Can't rent <8.
10. **Together dedicated endpoint ≠ cluster** — $6.49 vs $5.49 same hardware; endpoint adds inference engine + autoscaler.

---

## 6. Per-model concrete config + hourly cost

### DeepSeek-V4-Flash — the standout best-value pick

This is the model the matrix told us to switch to (rank 1, 0.95/1.00). Also the cheapest to self-host meaningfully.

| Tier | Config | Provider | $/hr |
|---|---|---|---|
| **Production sweet spot** | 2× H200 141GB, SGLang FP4+FP8 + EAGLE spec decode | Hyperbolic ($2.15 × 2) | **~$4.30/hr** |
| Comfortable | 4× H100 80GB | RunPod Community ($1.99 × 4) | ~$8/hr |
| **Budget single-GPU** | 1× RTX 5090 32GB + ~256 GB DDR5 via KTransformers | Vast.ai 5090 + RAM-rich host | **~$1-2/hr** |

**Documented throughput**: 266 tok/s single-batch decode on 2× H200 SGLang (LMSYS day-0). 20+ tok/s on 1× RTX 5090 + DDR5 KTransformers. Strong agentic scores (SWE-Bench Verified 79.0%).

### Nemotron-3-Ultra — second-cleanest self-host story

| Tier | Config | $/hr |
|---|---|---|
| Production | 4× H200 NVFP4 (official NVIDIA quant) | ~$8-10/hr |
| Comfortable | 8× B200 | ~$50-60/hr |
| Budget | 4× H100 NVFP4 | ~$8/hr |

Day-0 vLLM/SGLang/TensorRT-LLM cookbooks plus Unsloth GGUF for llama.cpp. Mamba-hybrid means low KV-cache pressure → long contexts cost less VRAM. Blackbox AI serving at 400+ tok/s per user.

### GLM-5 — possible but expensive

Despite scoring well (rank 5, fastest in matrix at 25.9s), the 744B total params force serious hardware:

| Tier | Config | $/hr |
|---|---|---|
| Production | 8× H200 FP8 (`zai-org/GLM-5-FP8`) | ~$17-25/hr |
| Comfortable | 8× B200 | ~$50/hr |
| Budget Q2 GGUF | 1× 24GB GPU + 256GB RAM via llama.cpp `--n-cpu-moe` | ~$1-2/hr (single-digit tok/s) |

MIT licensed (most permissive). User-experienced speed advantage from the matrix may evaporate when self-hosted unless you afford the full 8× H200 setup.

### DeepSeek-V4-Pro — don't bother self-hosting

The 1.6T parameter weight footprint (~865 GB even at native FP4+FP8) requires 8× H200 single-node minimum, or GB200 NVL4. That's $30-60/hr territory. Better off paying for the cloud model given quality is only marginally above V4-Flash.

### MiniMax-M3 — wait

Weights not public as of 2026-06-08. Check `huggingface.co/MiniMaxAI` after 2026-06-11.

---

## 7. The CPU-offload tier (the unique value of MoE class)

MoE models route to a small subset of experts per token. Expert weights are largely cold; attention/router/shared-expert weights are hot. So: keep hot weights on GPU, push cold expert weights to system RAM, fetch on demand. Dramatically reduces required VRAM.

### V4-Flash (officially supported by KTransformers as of 2026-05-02)

- **Validated config**: 1× RTX 5090 32 GB + Intel Xeon w/ AVX-512 + ≥256 GB DDR5 + ~340 GB SSD for weights
- **Quant**: MXFP4 default; AMXINT4 for CPU experts on Xeons with AMX
- **Performance**: 20+ tok/s decode; ~32 tok/s on 8× 5090 with MTP/EAGLE
- **Startup**: 4-5 min weight load + CUDA graph capture
- ik_llama.cpp also supports it via tensor overrides — community reports 8-12 tok/s on 96 GB VRAM + 146 GB GGUF setups

### GLM-5

Same trick works. Unsloth provides 2-bit dynamic GGUF that runs on **1× 24 GB GPU + 256 GB RAM** via llama.cpp `--n-cpu-moe` / MoE-offload flag. Tradeoff: long context reasoning works, throughput single-digit tok/s. No public single-user benchmark — **unverified throughput**, only "remains usable" qualitative from Unsloth.

### V4-Pro

Not feasible single-machine. At Q2 still ~256 GB and routing overhead crushes single-GPU.

### Nemotron-3-Ultra

No public CPU-offload recipe yet. Hybrid Mamba changes the offload pattern (Mamba state is small but sequential). **Unverified**.

---

## 8. Apple Silicon (M3 Ultra) viability

| Model | M3 Ultra 192 GB | M3 Ultra 256-512 GB | Verdict |
|---|---|---|---|
| DeepSeek-V4-Flash | Q4 fits (~80 GB weights) | Comfortable at Q4-Q6 | **Plausible** but no V4 MLX benchmark published — extrapolate from V3 |
| DeepSeek-V4-Pro | No | Even 512 GB only handles Q2 | Not viable |
| DeepSeek-V3 (reference) | Q4 marginal | **20+ tok/s at 4-bit on 512 GB** (Awni Hannun) | Works but degrades sharply past 16K context |
| GLM-5 | <1 tok/s at heavy quant | 2-bit dynamic GGUF "somewhat better, still far from practical" | Not viable for interactive |
| Nemotron-3-Ultra | No (needs ~275 GB at FP4) | Possible at Q4 on 512 GB; **no published MLX benchmark** | Unverified |

**MLX bottom line** for agentic 5-10 tool calls: only **M3 Ultra 512 GB + DeepSeek-V4-Flash @ 4-bit** is plausibly interactive (~20 tok/s, V3 baseline). Everything ≥500B total is too slow for tool-call latency. Mac Studio cost ($9-15k) vs. RunPod H200 at ~$3/hr (4-5 days break-even, but you own it).

---

## 9. The economics question — is self-hosting actually worth it for this project?

Current spend on Ollama Cloud Pro: **~$30/mo** + extra usage.

Self-host break-even math for DeepSeek-V4-Flash on 2× H200 ($4.30/hr):

| Usage pattern | Monthly self-host cost | vs. Ollama Pro $30/mo |
|---|---|---|
| 24/7 always-on | $3,096/mo | ~100× more expensive |
| 8 hrs/day weekdays | $688/mo | ~23× more expensive |
| 2 hrs/day | $258/mo | ~9× more expensive |
| **On-demand only when querying** (5 min × 50 queries/mo = ~4 hrs) | **~$17/mo** | **Cheaper than Ollama** |
| Modal serverless H100 ($0.001097/s × 2000s of actual compute) | $2.20/mo pure inference | Far cheaper — but cold-start overhead distorts this |

**Modal serverless** is the only path where naive math beats Ollama Pro, but cold-start reality (30-60s loading 80 GB model per request) makes the real cost ~$20-50/mo if you can't pre-warm.

### Honest verdict for this project's workload

For single-user, low-volume NetBox agent usage: **self-hosting is financially irrational** unless one of these applies:

1. **Privacy / compliance** — NetBox data can't go to a cloud LLM (the original "privacy thesis" from `2026-05-05_local-netbox-ai-assistant.md`)
2. **Quota frustration** — the 429s from the matrix sweep were because Ollama Pro doesn't fit a matrix-eval pattern, not your normal usage
3. **Model curiosity** — wanting to run something Ollama Cloud doesn't offer (fine-tuned variants, test-driving open weights, custom HarnessProfile experiments)
4. **A specific frontier model isn't on Ollama Cloud** — e.g. if MiniMax-M3 weights drop and Ollama Cloud delays adding it

---

## 10. Concrete recommendations

If one of those reasons applies:

| Recommendation | Cost | Purpose |
|---|---|---|
| **Easiest credible spike** | DeepSeek-V4-Flash on 1× RTX 5090 + 256 GB DDR5 via KTransformers on a Vast.ai host (~$1-2/hr). Half a day fiddling, ~$10 total. | Validate the self-host workflow without buying H200 time. See frontier-class quality at 20 tok/s. |
| **Production-grade spike** | DeepSeek-V4-Flash on 2× H200 SGLang FP4+FP8 on Hyperbolic (~$4.30/hr). Half-day cost ~$20. | Run the matrix harness against it as the "self-hosted-flash" experiment, verify quality matches cloud baseline. |
| **Daily Ollama Cloud replacement** | Don't. Math is wrong unless usage is dramatically higher OR there's a privacy mandate. | — |
| **Keep option open without spending** | Mac Studio M3 Ultra 512GB ($9-15k capex). Only verified single-purchase path documented to work for DeepSeek-V4-Flash at ~20 tok/s. | Equivalent to 3-4 years of 8h/day H200 rental — only justified if buying for other reasons. |

---

## 11. Open questions worth answering

- **Does GLM-5 deliver its matrix-leading speed (25.9s) when self-hosted, or is the speed an Ollama-Cloud-side optimization that disappears on a 8× H200 rental?** Worth a $20 spike before committing.
- **What's MiniMax-M3's actual parameter count?** Determines whether it lands closer to V4-Flash (easy self-host) or V4-Pro (hard) territory. Check HF after ~2026-06-11.
- **Does DeepSeek-V4-Flash on KTransformers (1× RTX 5090) preserve the entity-coverage 0.95 score, or does the offload quality loss show up in the eval?** Easy to test once spike is up.
- **Does the QuickJS Code Interpreter middleware (from `2026-06-03_quickjs-code-interpreter-research.md`) help more or less on self-hosted models?** The cost-per-tool-call shifts from "Ollama API" to "rented GPU per token" — could change the calculus for tool-call-heavy workloads.

---

## 12. Sources

### Open weights / model architecture
- [deepseek-ai/DeepSeek-V4-Pro — Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)
- [deepseek-ai/DeepSeek-V4-Flash — Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash)
- [DeepSeek V4 Preview — DeepSeek API Docs](https://api-docs.deepseek.com/news/news260424)
- [DeepSeek is back among the leading open weights models with V4 — Artificial Analysis](https://artificialanalysis.ai/articles/deepseek-is-back-among-the-leading-open-weights-models-with-v4-pro-and-v4-flash)
- [MiniMax M3 — MiniMax Blog](https://www.minimax.io/blog/minimax-m3)
- [MiniMaxAI — Hugging Face organization](https://huggingface.co/MiniMaxAI)
- [nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16)
- [unsloth/NVIDIA-Nemotron-3-Ultra-550B-A55B-GGUF](https://huggingface.co/unsloth/NVIDIA-Nemotron-3-Ultra-550B-A55B-GGUF)
- [Nemotron 3 Ultra: NVIDIA's 550B Open-Weights Model — ChatForest](https://chatforest.com/builders-log/nvidia-nemotron-3-ultra-550b-moe-open-weights-computex-2026/)
- [zai-org/GLM-5 — Hugging Face](https://huggingface.co/zai-org/GLM-5)
- [GLM-5: China's First Public AI Company Ships a Frontier Model — HF blog](https://huggingface.co/blog/mlabonne/glm-5)

### Inference stacks & throughput
- [DeepSeek-V4 on Day 0: From Fast Inference to Verified RL with SGLang — LMSYS Blog](https://www.lmsys.org/blog/2026-04-25-deepseek-v4/)
- [DeepSeek V4 VRAM & GPU Requirements — codersera](https://codersera.com/blog/deepseek-v4-vram-gpu-requirements-2026/)
- [DeepSeek V4 Flash KTransformers doc](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/DeepSeek-V4-Flash.md)
- [GLM-5 VRAM — GMI Cloud](https://www.gmicloud.ai/en/blog/where-to-run-glm-5-inference-in-the-cloud-gpu-requirements-deployment-options-and-scaling-considerations)
- [Announcing Day-0 Support for Nemotron 3 Ultra — vLLM Blog](https://vllm.ai/blog/2026-06-04-nemotron-3-ultra-vllm)
- [Optimizing DeepSeek-V3.2 on NVIDIA Blackwell — TensorRT-LLM](https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog15_Optimizing_DeepSeek_V32_on_NVIDIA_Blackwell_GPUs)
- [KTransformers SOSP'25 paper — ACM](https://dl.acm.org/doi/10.1145/3731569.3764843)
- [Performant local MoE CPU inference with GPU acceleration in llama.cpp — HuggingFace blog](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- [DeepSeek-V3 runs at 20 tokens/sec on Mac Studio — VentureBeat](https://venturebeat.com/ai/deepseek-v3-now-runs-at-20-tokens-per-second-on-mac-studio-and-thats-a-nightmare-for-openai)

### GPU rental pricing
- [RunPod pricing](https://runpod.io/pricing)
- [TensorDock H100 pricing](https://tensordock.com/gpu-h100.html)
- [Lambda Labs pricing](https://lambda.ai/pricing)
- [CoreWeave pricing](https://coreweave.com/pricing)
- [Crusoe Cloud pricing](https://crusoe.ai/cloud/pricing)
- [Modal pricing](https://modal.com/pricing)
- [Together AI pricing](https://together.ai/pricing)
- [Vast.ai pricing](https://vast.ai/pricing)
- [Hyperbolic.ai](https://hyperbolic.ai/)
- [Spheron GPU cloud pricing comparison 2026](https://spheron.network/blog/gpu-cloud-pricing-comparison-2026)
- [Thunder Compute providers](https://thundercompute.com/blog/cheapest-providers)
- [GMI Cloud H200 provider pricing](https://gmicloud.ai/en/blog)
- [Vantage AWS p5.48xlarge tracker](https://instances.vantage.sh/aws/ec2/p5.48xlarge)
- [Vantage GCP a3-ultragpu-8g](https://instances.vantage.sh/gcp/a3-ultragpu-8g)
