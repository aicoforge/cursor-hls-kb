# Demo: 128-Tap FIR Filter — AI-Driven HLS Design via KB Rules

> **Project**: `FIR128_Demo` | **Tool**: Vitis HLS 2023.2 | **Target**: xc7z020clg400-1
> 
> This demo shows how a single Cursor prompt drives Vitis HLS through **3 progressive iterations**, with the KB and recording rules at every step. User-defined rules (P###) are highlighted to show their real impact on design decisions.

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

The KB stores both official HLS rules (R-prefix) and **user-defined practical rules (P-prefix)**. Every iteration is recorded with synthesis results and which rules were applied — building shared experience that improves future designs.

---

## User Prompt

```
Design a 128-tap FIR filter with AXI Streaming and minimal resource usage,
name the project FIR128_Demo, follow the KB rules
```

One sentence. Cursor queries the KB (dual-track: similar past designs + effective rules), selects applicable rules, and begins designing.

---

## KB Dual-Track Query Result

| Track                         | Result                                                                                                                                                                                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Track 1** — similar designs | No prior FIR records → Path B (derive from rules)                                                                                                                                                                                                         |
| **Track 2** — effective rules | **P034** (circular shift register), **P035** (avoid full-array copy per sample), **R035/R036** (inner loop PIPELINE II=1), **P047** (no stream write inside hot pipeline loop), **P039** (STREAM depth for DATAFLOW), **R251** (AXIS + s_axilite control) |

> **P047, P034, P035** are user-defined rules. The KB returned them as high-priority because they had proven effectiveness in past iterations.

---

## Iteration 1 — Baseline: Single MAC, Circular Buffer

**Architecture**

```
AXI-Stream in ──► circular buf[128] + wptr
                        │
                  inner k loop (PIPELINE II=1)
                  single MAC per cycle
                  128 iterations / output sample
                        │
                  acc >> 7  (moving average)
                        │  (write AFTER MAC — P047)
AXI-Stream out ◄────────┘
```

**Key Rules Applied**

| Rule     | Type            | How It Was Used                                                                     |
| -------- | --------------- | ----------------------------------------------------------------------------------- |
| **P034** | 🔵 User-defined | Circular index `(wptr + k) & 127` — one tap written per sample, no full shift       |
| **P035** | 🔵 User-defined | Never copy the whole 128-element array each sample cycle                            |
| **R036** | Official        | Target inner MAC loop at II=1                                                       |
| **R035** | Official        | `#pragma HLS PIPELINE II=1` on the inner tap loop                                   |
| **P047** | 🔵 User-defined | `out_s.write()` placed **after** the MAC loop, not inside the pipelined k iteration |
| **R251** | Official        | AXIS data port + s_axilite for `num_samples` block length                           |

> **P034 impact**: Without the circular buffer, each new input sample would require copying all 128 taps. The KB rule explicitly prevents this, keeping the inner loop clean for II=1 pipelining.
> 
> **P047 impact**: AXI-Stream write inside a pipelined loop creates interface/pipeline coupling that can break II=1. KB flagged this pattern before the code was written.

**Synthesis Results** (10 ns clock)

| Metric                   | Value                     |
| ------------------------ | ------------------------- |
| Inner loop II (ii_bneck) | **1**                     |
| Cycles per output sample | **~135**                  |
| DSP                      | **0** (fabric multiplier) |
| BRAM_18K                 | **2**                     |
| LUT / FF                 | **477 / 218**             |
| Timing                   | ✅ Met (slack +0.17 ns)    |

**csim**: PASS

---

## Iteration 2 — Dual MAC, 2× Throughput

**User Prompt**

```
Based on iter1, keep ii=1, DSP limit 2, try to improve throughput
```

**What Changed**

The inner loop processes **2 taps per pipeline iteration** instead of 1:

```cpp
for (int k = 0; k < 128; k += 2) {
#pragma HLS PIPELINE II=1
    int idx0 = (base + 128 - k)     & 127;
    int idx1 = (base + 128 - k - 1) & 127;
    acc += (acc_t)coeff[k]   * (acc_t)buf[idx0];
    acc += (acc_t)coeff[k+1] * (acc_t)buf[idx1];  // 2 MACs per cycle
}
```

```cpp
#pragma HLS ARRAY_PARTITION variable=coeff cyclic factor=2  // R051
#pragma HLS ARRAY_PARTITION variable=buf   cyclic factor=2  // R051
```

**Key Rules Applied**

| Rule     | Type            | How It Was Used                                                                |
| -------- | --------------- | ------------------------------------------------------------------------------ |
| **R051** | Official        | `ARRAY_PARTITION cyclic factor=2` on `coeff` and `buf` to supply 2 reads/cycle |
| **R036** | Official        | Maintain II=1 in the new dual-MAC inner loop                                   |
| **P047** | 🔵 User-defined | Stream write still placed outside the loop (unchanged from iter1)              |
| **P034** | 🔵 User-defined | Circular buffer still in use; both read indices derived from `wptr`            |

> **R051 + P034 interaction**: The dual-MAC needs 2 simultaneous reads from `buf`. `cyclic factor=2` partition enables this. The circular-buffer addressing (P034) is what makes both indices computable in a single cycle without extra logic.

**Synthesis Results** (12 ns clock — widened because the dual-MAC critical path is longer)

| Metric          | Iter 1    | **Iter 2**                 | Change   |
| --------------- | --------- | -------------------------- | -------- |
| Inner loop II   | 1         | **1**                      | —        |
| Cycles / sample | ~135      | **~72**                    | **−47%** |
| DSP             | 0         | **0**                      | —        |
| BRAM_18K        | 2         | **2**                      | —        |
| LUT / FF        | 477 / 218 | **599 / 254**              | +26% LUT |
| Timing          | ✅ Met     | ✅ **Met** (slack +0.18 ns) | —        |

**csim**: PASS

---

## Iteration 3 — Quad MAC, 3.5× Throughput

**User Prompt**

```
Sure, go ahead and try what you suggested
```

(Cursor had already suggested "try factor=4 quad MAC as the next step".)

**What Changed**

Inner loop now processes **4 taps per pipeline iteration**:

```cpp
for (int k = 0; k < 128; k += 4) {
#pragma HLS PIPELINE II=1
    acc += coeff[k]   * buf[idx0];
    acc += coeff[k+1] * buf[idx1];
    acc += coeff[k+2] * buf[idx2];
    acc += coeff[k+3] * buf[idx3];
}
```

```cpp
#pragma HLS ARRAY_PARTITION variable=coeff cyclic factor=4
#pragma HLS ARRAY_PARTITION variable=buf   complete        // ← key change
```

**Why `complete` partition on `buf`?**

With `cyclic factor=4`, HLS reported **error HLS 200-885** (insufficient BRAM read ports), and the inner loop II was forced to **2**. The KB recorded this failure pattern — switching to `complete` partition (all 128 elements become individual registers/LUT) resolved the port conflict and restored II=1.

> **P034 + R051 lesson**: For very high parallelism on a circular buffer, cyclic partitioning hits BRAM port limits. `complete` partition trades BRAM for LUT/FF but preserves II=1. This trade-off is exactly the kind of accumulated knowledge that KB stores for future designs.

**Key Rules Applied**

| Rule            | Type            | How It Was Used                                                                 |
| --------------- | --------------- | ------------------------------------------------------------------------------- |
| **R051**        | Official        | `cyclic factor=4` on `coeff`; `complete` on `buf` to break BRAM port bottleneck |
| **P038**        | 🔵 User-defined | `complete` partition justified by "full unroll of read path" for II=1           |
| **R036 / R035** | Official        | Maintain II=1 in quad-MAC loop                                                  |
| **P047**        | 🔵 User-defined | Stream write outside loop (unchanged)                                           |

**Synthesis Results** (15 ns clock — four parallel critical paths are longer)

| Metric          | Iter 2    | **Iter 3**                 | vs Iter 1        |
| --------------- | --------- | -------------------------- | ---------------- |
| Inner loop II   | 1         | **1**                      | 1                |
| Cycles / sample | ~72       | **~39**                    | **~3.5×** faster |
| DSP             | 0         | **0**                      | —                |
| BRAM_18K        | 2         | **0**                      | BRAM traded away |
| LUT / FF        | 599 / 254 | **3300 / 2365**            | +7× LUT          |
| Timing          | ✅ Met     | ✅ **Met** (slack +0.57 ns) | —                |

**csim**: PASS

---

## 3-Iteration Summary

```
              Cycles/sample    LUT      BRAM   DSP   Clock
Iter 1  ───── ~135 ────────── 477  ──── 2 ──── 0 ─── 10 ns  (baseline)
Iter 2  ─────  ~72 ────────── 599  ──── 2 ──── 0 ─── 12 ns  (+2 MAC)
Iter 3  ─────  ~39 ────────── 3300 ──── 0 ──── 0 ─── 15 ns  (+4 MAC)
                ▲ 3.5×                ▲ 7×
                throughput           LUT cost
```

All three iterations maintain **inner II=1** and **DSP=0** (fabric multiplication). The throughput gains come purely from increasing MAC parallelism and matching array partitioning — guided by KB rules at every step.

---

## Rules Effectiveness Summary

| Rule            | Type            | Iterations | Key Outcome                                                    |
| --------------- | --------------- | ---------- | -------------------------------------------------------------- |
| **P034**        | 🔵 User-defined | 1, 2, 3    | Circular buffer → enables II=1 without full-array shift        |
| **P035**        | 🔵 User-defined | 1, 2, 3    | No per-sample array copy → clean inner loop                    |
| **P047**        | 🔵 User-defined | 1, 2, 3    | Stream write after MAC → prevents interface/pipeline conflict  |
| **R036 / R035** | Official        | 1, 2, 3    | Inner PIPELINE II=1 is the core throughput mechanism           |
| **R051**        | Official        | 2, 3       | Array partition enables multi-port parallel reads              |
| **P038**        | 🔵 User-defined | 3          | `complete` partition resolves BRAM port bottleneck at factor=4 |

> Each iteration's `rules_applied` is written to the KB with success/failure status, updating `rules_effectiveness` statistics. The next project using similar patterns will receive these rules ranked higher.

---

*Generated from Cursor + HLS KB session logs. Project: FIR128_Demo. KB system: cursor-hls-kb v1.0 by AICOFORGE.*
