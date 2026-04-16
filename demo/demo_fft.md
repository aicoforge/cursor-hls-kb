# Demo: N=16 Fixed-Point FFT — AI-Driven HLS Design via KB Rules

> **Project**: `FFT_Demo` | **Tool**: Vitis HLS 2023.2 | **Target**: xc7z020clg400-1
> 
> This demo shows how Cursor + KB drives a 16-point radix-2 DIT FFT from a staged baseline (II=2 at 25 ns) to a **fully pipelined II=1 design at 10 ns** — and how the tricky pipelining issues encountered on the way lead to **four new user-defined P-rule proposals** that can be contributed back to the KB.

---

## System Overview

```
Developer (Cursor prompt)
    │
    ▼
Cursor AI Agent  ──── SSH ────►  Vitis HLS Host
    │                               │  csim / csynth
    │                               │
    └───── HTTP API ──────►  HLS Knowledge Base
                              ┌─────────────────────────┐
                              │ R###  Official Rules    │
                              │ P###  User-defined Rules│
                              │ design_iterations       │
                              │ rules_effectiveness     │
                              └─────────────────────────┘
```

---

## User Prompt (Iteration 1)

```
Design a FFT_Demo project following KB rules, an FFT (N=16) that processes complex inputs in multiple stages.
Use fixed-point numbers and pipeline each stage, without fully unrolling everything. 
Use precomputed twiddle factors and aim for good performance without using too many resources.
```

---

## Iteration 1 — Staged Baseline: Radix-2 DIT, Per-Stage Pipeline

### KB Dual-Track Query

| Track                         | Result                                                                                                                                                                                       |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Track 1** — similar designs | No prior FFT records (`GET /api/design/similar?project_type=fft` → empty) → Path B (derive from rules)                                                                                       |
| **Track 2** — effective rules | **R035** (inner PIPELINE), **R036** (II=1 target), **R074** (pipeline inner loops, not whole function), **R063** (II>1 only as deliberate trade-off), **P035** (no full-array copy per step) |

### Architecture

Radix-2 decimation-in-time, four in-place stages over a shared `ap_fixed<16,6>` complex buffer:

```
x[N] (ap_fixed, complex)
    │
    ▼
bit-reverse load ──► buf_re[16], buf_im[16]
    │
    ├── stage 0  (span=2,  pairs=8)  ─┐
    ├── stage 1  (span=4,  pairs=8)  ─┤  fft_stage_inplace()
    ├── stage 2  (span=8,  pairs=8)  ─┤  one pipelined butterfly loop per stage
    └── stage 3  (span=16, pairs=8)  ─┘
    │
    ▼
X[N] (complex output)
```

Each stage runs a single unified butterfly loop (8 butterflies) with `#pragma HLS PIPELINE II=1`. Precomputed twiddles `W_RE[16] / W_IM[16]` live in `twiddle.inc`. Input, twiddle, and working buffers use `cyclic` partition factors chosen to feed the butterfly with real/imaginary pairs each cycle.

### Key Rules Applied

| Rule     | Type            | How It Was Used                                                                                       |
| -------- | --------------- | ----------------------------------------------------------------------------------------------------- |
| **R035** | Official        | `#pragma HLS PIPELINE` on every butterfly loop and bit-reverse load loop                              |
| **R036** | Official        | II=1 is the declared target for the butterfly loop                                                    |
| **R074** | Official        | Top `fft16` uses `ap_ctrl_hs`; pipeline the **inner** stage loops, not the whole function             |
| **R063** | Official        | When HLS schedules II=2 at 25 ns, accepted as deliberate trade-off (used to justify clock relaxation) |
| **P035** | 🔵 User-defined | Each stage does O(N) butterfly write-back only — no full-buffer `memcpy` between stages               |

### Synthesis Results

Initial synthesis at 10 ns failed timing (butterfly combinational path ~17.9 ns). At **25 ns**, timing met but the butterfly loop scheduled at II=2 (HLS could not achieve II=1 due to in-place RAW dependencies — flagged by R063 as acceptable baseline).

| Metric               | Value                  |
| -------------------- | ---------------------- |
| ii_bneck (butterfly) | **2**                  |
| ii_top (fft16)       | **117**                |
| Latency (cycles)     | **116**                |
| DSP                  | **8**                  |
| LUT / FF             | **3723 / 2814**        |
| BRAM_18K             | **0**                  |
| Clock                | 25 ns                  |
| Timing               | ✅ Met (slack +0.37 ns) |

**csim**: PASS (checked against double-precision DFT reference, tolerance 0.25) **KB record**: `FFT_Demo` / iteration #1, rules recorded: R035, R036, R074, R063, P035

> II=2 and the 25 ns clock are the two compromises that iter 2 will attack. The root cause is the **butterfly's in-place write** (`buf[idx1]`, `buf[idx2]` both updated in the same iteration) combined with a long combinational multiply-add path.

---

## Iteration 2 — II=1 at 10 ns: Pipeline Restructuring

### User Prompt

```
Break the butterfly computation into multiple pipeline stages to shorten combinational delay. 
Target II=1 at a tighter clock (e.g., 10–15 ns) without relaxing timing constraints.
Resolve data dependency in in-place updates using buffering or partitioning.
```

### The Four Structural Changes

All four changes are needed together — each one alone leaves some bottleneck in place. This is where the **unnumbered P-rule candidates** emerge (Section below).

**1. Ping-pong double buffer** — replace in-place with read-bank / write-bank

```cpp
cplx_t buf_re[2][FFT_N];   // [bank][idx]
cplx_t buf_im[2][FFT_N];
// Stage s reads from buf_*[RD], writes to buf_*[WR]; alternates each stage.
```

The in-place update pattern (`buf[i] = f(buf[i], buf[j])`) creates a read-after-write dependency that forces II≥2 when pipelined. Splitting into two banks breaks the dependence entirely.

**2. Template-fixed banks** — compile-time bank indices

```cpp
template<int RD, int WR>
void fft_stage_t(...) { /* uses buf_re[RD], buf_re[WR] directly */ }

fft_stage_t<0,1>(...);   // stage 0
fft_stage_t<1,0>(...);   // stage 1
fft_stage_t<0,1>(...);   // stage 2
fft_stage_t<1,0>(...);   // stage 3
```

A runtime `rp` / `wp` index forces HLS to synthesize a `sparsemux` on every bank access — which lengthens the critical path. Fixing `RD`/`WR` at compile time removes the mux and lets the scheduler pack the butterfly much tighter.

**3. Butterfly decomposition** — split multiply from add/subtract

```cpp
// Four independent multiplies first
auto m_rr = a_re * w_re;
auto m_ii = a_im * w_im;
auto m_ri = a_re * w_im;
auto m_ir = a_im * w_re;
// Then compose (tr, ti) and do add/sub write-back
auto tr   = m_rr - m_ii;
auto ti   = m_ri + m_ir;
```

Decomposing gives the scheduler explicit pipeline boundaries — multiplies land in one cycle, add/sub and write-back in the next — instead of one long mul-add chain per butterfly.

**4. `complete` partition on the index dimension (the deciding fix)**

Even after changes 1–3, HLS still reported **II=2** with warning **200-880** (carried dependence). Root cause: each butterfly writes to **two** locations in the write bank (`buf[WR][idx1]` and `buf[WR][idx2]`) in the same loop iteration, but the default BRAM gives only a single write port per cycle.

```cpp
#pragma HLS ARRAY_PARTITION variable=buf_re dim=1 complete  // ping/pong banks
#pragma HLS ARRAY_PARTITION variable=buf_re dim=2 complete  // 16 independent index ports  ← key
#pragma HLS ARRAY_PARTITION variable=buf_im dim=1 complete
#pragma HLS ARRAY_PARTITION variable=buf_im dim=2 complete
```

With `dim=2 complete`, `idx1` and `idx2` land in **different registers**, giving two write ports in the same cycle. II drops 2 → 1.

Supporting: `#pragma HLS BIND_OP op=mul impl=dsp` inside `fft_stage_t` to bind butterfly multiplies to DSPs rather than fabric LUTs.

### Key Rules Applied

| Rule            | Type             | How It Was Used                                                                                  |
| --------------- | ---------------- | ------------------------------------------------------------------------------------------------ |
| **R035 / R036** | Official         | Butterfly loop `PIPELINE II=1`; goal achieved after the four structural changes                  |
| **R074**        | Official         | Top `fft16` chains **4 `fft_stage_t` calls** — no function-level DATAFLOW; inner loops pipelined |
| **P035**        | 🔵 User-defined  | Ping-pong buffer is still O(N) per stage, not a full `memcpy` — consistent with P035             |
| *(no number)*   | ⚪ User rule text | Four new unnumbered P-rule candidates, documented in the file header (see section below)         |

### Synthesis Results

| Metric               | Iter 1             | **Iter 2**             | Change                                |
| -------------------- | ------------------ | ---------------------- | ------------------------------------- |
| ii_bneck (butterfly) | 2                  | **1** ✅                | **II halved**                         |
| ii_top (fft16)       | 117                | **145**                | +24% (deeper pipeline, shorter cycle) |
| Latency (cycles)     | 116                | **144**                | +24%                                  |
| DSP                  | 8                  | **16**                 | +8 (2× for decomposed mul)            |
| LUT / FF             | 3723 / 2814        | **7427 / 5273**        | +100% (partition cost)                |
| Clock                | 25 ns              | **10 ns** ✅            | **2.5× tighter**                      |
| Timing               | ✅ (slack +0.37 ns) | ✅ **(slack +0.27 ns)** | met at 10 ns                          |
| **Effective time**   | 116 × 25 = 2900 ns | **144 × 10 = 1440 ns** | **−50%**                              |

**csim**: PASS **KB record**: `FFT_Demo` / iteration #2

> The resource cost (2× DSP, 2× LUT/FF) buys a 2.5× tighter clock and II=1 — net wall-clock speedup of **2×**. This is the classic "spend area to buy throughput" trade that FFT accelerators in practice always make.

---

## How the Unnumbered P-Rule Candidates Emerged

This is the part worth studying if you plan to **contribute your own P-rules to the KB**. None of the four candidates below existed in the KB before iter 2. Each one was **derived from a concrete debug round** in iter 2 and then generalized.

### Derivation trace

| Symptom in iter 2                                                                 | Concrete fix                                  | Generalized rule candidate                                   |
| --------------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------ |
| HLS 200-880 carried dependence on `buf[WR][idx1]`/`buf[WR][idx2]` → II stuck at 2 | `ARRAY_PARTITION dim=2 complete` on buffers   | **Candidate A (memory)**: dual-write detection               |
| In-place stage loops force RAW dependency whenever pipelined                      | Ping-pong `buf_re[2][N]`                      | **Candidate B (memory)**: ping-pong for multi-stage in-place |
| Runtime `rp`/`wp` index generates large `sparsemux`, lengthens critical path      | `template<int RD,int WR>` specialized calls   | **Candidate C (optimization)**: compile-time bank selection  |
| Fixed-point complex MAC pushes combinational path beyond 10 ns budget             | `BIND_OP mul impl=dsp` + split mul/add stages | **Candidate D (synthesis / pipeline)**: DSP bind + split MAC |

### The four proposed P-rules (draft text, not yet numbered)

| Category           | Draft `rule_text`                                                                                                                                                                                                                                                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`memory`**       | When a single loop iteration writes to the same logical array **two or more times**, use `complete` partition, a true dual-port memory, or explicit multi-port binding to prevent a carried dependence from forcing II>1. A shallow `cyclic` factor is not enough if `idx1` and `idx2` can still land in the same bank.                   |
| **`memory`**       | For multi-stage algorithms with a clean "read old / write new" separation (e.g. FFT stages, stencil sweeps), prefer **ping-pong double buffering** or fixed read/write banks over in-place updates when deep pipelining is required. If in-place is mandatory, prove index non-overlap across iterations or serialize the stage.          |
| **`optimization`** | In hot inner loops that select a memory bank per stage, prefer **compile-time bank selection** (template specialization or unrolled dispatch) over runtime index variables like `rp`/`wp`. Variable bank selection synthesizes as `sparsemux`, which inflates the critical path and defeats tight clock targets.                          |
| **`synthesis`**    | For fixed-point complex MAC / butterfly operators struggling to meet a tight clock, **bind multiplies to DSP** (`BIND_OP op=mul impl=dsp` or equivalent) and **split the operator** into explicit multiply → combine → add/subtract stages. This gives the scheduler clean pipeline boundaries and keeps fabric out of the critical path. |

### Category guidance (how to pick)

- **`memory`** — rule is about ports, partitioning, ping-pong, or multi-write patterns. *(First two candidates above.)*
- **`optimization`** — rule is about mux, address decode, template/expansion tricks. *(Third candidate.)*
- **`synthesis`** — rule is about DSP binding, resource/timing constraints. *(Fourth candidate; could also sit in `pipeline` if you emphasize II.)*
- **`pipeline`** — reserve for pure II / PIPELINE / dependence constraints that don't fit cleanly elsewhere.

> **Also worth adding as `fft`** — the KB already has application categories (`fir`, `systolic`, `cordic`, …) and Track 2 Step 0 queries them first (`category=${project_type}`) when a matching application is inferred. Adding **`fft`** alongside each technical category means a future FFT project's Step 0 retrieves these four rules directly, while the technical-category query path keeps them discoverable for any non-FFT design facing the same class of issue (dual-write, ping-pong, bank selection, DSP/MAC split). The two are merged and do not override each other.

### How these were recorded (important mechanics)

Only rules **with a `rule_code`** go into the API's `rules_applied` array when calling `complete_iteration`. Unnumbered proposals live in **the file header comment** of `fft.cpp` as bullets under `Applied Rules`, in the same format as numbered rules but without the code:

```cpp
// Applied Rules (FFT_Demo iter2):
//  - R035: inner loops use #pragma HLS PIPELINE
//  - R036: II=1 target on butterfly loop
//  - R074: pipeline inner stage loops, not whole fft16
//  - P035: no full-buffer memcpy between stages
//  - (no code): when a single loop iteration writes to the same logical array
//               twice, use complete partition or dual-port memory to avoid
//               a carried dependence forcing II>1.
//  - (no code): prefer ping-pong buffering over in-place updates for
//               multi-stage pipelined algorithms.
//  - (no code): fix memory bank selection at compile time (template
//               specialization) instead of runtime rp/wp indices.
//  - (no code): for tight-clock fixed-point MAC, bind multiplies to DSP
//               and split mul → combine → add/sub across pipeline stages.
```

This pattern — **numbered rules in the API + textual drafts in the code header** — is the suggested workflow for proposing new P-rules. A KB maintainer can later review the drafts, assign `P###` numbers, and promote them into `hls_rules`.

---

## 2-Iteration Summary

```
         II   Clock   Latency   DSP   LUT    Architecture
Iter 1 ─ 2  ─ 25 ns ─ 116 ─────  8 ─ 3723 ─ In-place stages, inner PIPELINE, timing relaxed
Iter 2 ─ 1  ─ 10 ns ─ 144 ─── 16 ─ 7427 ─ Ping-pong + template banks + split MAC + dim=2 partition
         ▼             ▼
      II halved    Wall-clock 2× faster (1440 ns vs 2900 ns)
```

The journey from iter 1 to iter 2 is a textbook example of buying throughput with area — **and** of converting hard-won debug experience into reusable P-rule candidates for the KB.

---

## Rules Effectiveness Summary

| Rule                       | Type               | Iterations | Key Outcome                                                                            |
| -------------------------- | ------------------ | ---------- | -------------------------------------------------------------------------------------- |
| **R035 / R036**            | Official           | 1, 2       | Butterfly `PIPELINE II=1` target throughout; achieved in iter 2 after structural fixes |
| **R074**                   | Official           | 1, 2       | Top `fft16` pipelines inner stage loops; not a function-level streaming kernel         |
| **R063**                   | Official           | 1          | Justified iter 1's II=2 as deliberate trade-off pending the iter 2 restructuring       |
| **P035**                   | 🔵 User-defined    | 1, 2       | Stage updates stay O(N); no full-buffer copies even with ping-pong                     |
| **Dual-write / partition** | ⚪ Unnumbered draft | 2          | Resolves HLS 200-880 on two-write-per-iter butterflies → enables II=1                  |
| **Ping-pong vs in-place**  | ⚪ Unnumbered draft | 2          | Eliminates stage RAW dependency blocking deep pipelines                                |
| **Compile-time bank**      | ⚪ Unnumbered draft | 2          | Removes `sparsemux` from bank selection → shortens critical path                       |
| **BIND_OP + split MAC**    | ⚪ Unnumbered draft | 2          | DSP binding + staged multiply/add → fixed-point complex MAC meets 10 ns                |

> **Takeaway for KB contributors**: new P-rules should come from a **concrete debug round** — a specific HLS warning, a measured critical-path regression, a reproducible II stall. Record the rule alongside the synthesis numbers that motivated it, and put the draft text in the file header until a maintainer assigns a `P###`.

---

*Generated from Cursor + HLS KB session logs. Project: FFT_Demo. KB system: cursor-hls-kb v1.0 by AICOFORGE.*
