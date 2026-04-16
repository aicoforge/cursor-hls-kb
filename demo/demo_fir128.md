# Demo: 128-Tap FIR Filter — AI-Driven HLS Design via KB Rules

> **Project**: `FIR128_Demo` | **Tool**: Vitis HLS 2023.2 | **Target**: xc7z020clg400-1
>
> This demo shows how Cursor + KB drives a **128-tap streaming FIR filter** from a minimal single-DSP baseline, through continuous streaming redesign, to a **2-way parallel MAC** — each step guided by KB rules. User-defined rules (P###) prevent common pitfalls before they occur.

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
Design a 128-tap FIR filter with AXI Streaming interface using a streaming loop architecture,
with minimal resource usage. Name the project FIR128_Demo, follow the KB rules.
```

---

## Iteration 1 — Area-Minimal Streaming-Loop Baseline

### KB Dual-Track Query

| Track                         | Result                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------- |
| **Track 1** — similar designs | No prior FIR records → Path B                                                               |
| **Track 2** — effective rules | **R035/R036** (II=1), **P047** (no stream I/O in hot MAC loop), **P079** (circular buffer)  |

> **P047** prevents placing `axis.read()`/`write()` inside the pipelined MAC loop — a classic FIR mistake that kills II=1.
> **P079** mandates a circular delay line in BRAM instead of shifting all 128 taps every sample.

### Architecture

```
s_axis_data ──► sample_loop (read 1 sample) ─┐
                                             │
              delay_line[128] (BRAM, circ.) ─┤──► tap_mac (k=0..127, PIPELINE II=1)
              coeff_rom[128] (BRAM)         ─┘        │  single DSP MAC
                                                      ▼
                                              m_axis_data ──► (write outside MAC: P047 ✓)
```

Two nested loops in a single `ap_ctrl_hs` function:

1. **`sample_loop`** — reads one AXI-Stream beat, writes one output beat (P047: stream I/O here only)
2. **`tap_mac`** — inner `k = 0..127`, `#pragma HLS PIPELINE II=1`, serial multiply-accumulate

### Key Rules Applied

| Rule            | Type            | How It Was Used                                                             |
| --------------- | --------------- | --------------------------------------------------------------------------- |
| **R035 / R036** | Official        | Inner `tap_mac` targets II=1                                                |
| **P047**        | 🔵 User-defined | AXIS `read()`/`write()` only in `sample_loop`, never inside pipelined MAC   |
| **P079**        | 🔵 User-defined | Circular `delay_line[128]` in single-port BRAM (`BIND_STORAGE ram_1p bram`) |

> **P047 impact**: Placing `s_axis_data.read()` inside the 128-tap MAC loop would force the stream and pipeline to interlock, destroying II=1. KB flagged this before coding began.
>
> **P079 impact**: A naive shift-register approach (`for i=127..1: delay[i]=delay[i-1]`) would consume ~128 registers and create routing pressure. The circular buffer uses a single write pointer and two BRAM reads per cycle.

### Synthesis Results (12 ns clock)

| Metric              | Value                     |
| ------------------- | ------------------------- |
| **tap_mac II**      | **1** ✅                  |
| Latency (512 block) | **70657** cycles          |
| Per-sample cycles   | ~138 (128 MAC + overhead) |
| **DSP**             | **1**                     |
| **BRAM_18K**        | **2**                     |
| LUT / FF            | **295 / 145**             |
| Timing              | ✅ Met (slack ~1.01 ns)   |

**csim**: PASS
**KB record**: `FIR128_Demo` / iteration #1, rules: R035, R036, P047, P079

---

## User Prompt (Iteration 2)

```
Re-design for iter2: outer streaming loop (no NUM_SAMPLES, no fixed packet length).
Process one sample per outer loop iteration with an inner pipelined MAC loop.
```

---

## Iteration 2 — Continuous Streaming (No Fixed Block Length)

### What Changed

| Aspect                 | Iter 1                             | Iter 2                                          |
| ---------------------- | ---------------------------------- | ----------------------------------------------- |
| **Top-level control**  | `ap_ctrl_hs` (block of 512)       | **`ap_ctrl_none`** (free-running, always-on)     |
| **Outer loop**         | `for (n = 0; n < NUM_SAMPLES)`    | **`while (1)`** (synthesis) / finite (csim only) |
| **Packet dependency**  | Fixed `NUM_SAMPLES = 512`         | **None** — true streaming                        |

Core structure:

```cpp
#pragma HLS INTERFACE ap_ctrl_none port=return   // R259: free-running

sample_loop:
#ifdef __SYNTHESIS__
    while (1) {                         // RTL: never terminates
#else
    for (unsigned n = 0; n < FIR128_CSIM_SAMPLES; n++) {  // csim: finite
#endif
        axis_pkt_t in_pkt = s_axis_data.read();

        tap_mac:
        for (int k = 0; k < NUM_TAPS; k++) {
#pragma HLS PIPELINE II = 1            // R035/R036
            // ... single MAC ...
        }

        m_axis_data.write(out_pkt);    // P047: outside tap_mac
    }
```

### Key Rules Applied

| Rule            | Type            | How It Was Used                                           |
| --------------- | --------------- | --------------------------------------------------------- |
| **R035 / R036** | Official        | Inner `tap_mac` still II=1                                |
| **P047**        | 🔵 User-defined | Stream I/O remains outside MAC loop                       |
| **P079**        | 🔵 User-defined | Circular delay line unchanged                             |

### Synthesis Results (12 ns clock)

| Metric           | Iter 1       | **Iter 2**               | Change           |
| ---------------- | ------------ | ------------------------ | ---------------- |
| **tap_mac II**   | 1            | **1**                    | —                |
| Top-level        | block of 512 | **unbounded** (streaming) | true streaming   |
| Per-sample cycles| ~138         | **~138**                 | —                |
| DSP              | 1            | **1**                    | —                |
| BRAM_18K         | 2            | **2**                    | —                |
| LUT / FF         | 295 / 145    | **259 / 135**            | slightly smaller |

**csim**: PASS
**KB record**: `FIR128_Demo` / iteration #2

---

## User Prompt (Iteration 3)

```
Based on iter2, keep ii=1/DSP limit 2/more MAC, try to improve throughput
```

---

## Iteration 3 — 2-Way Parallel MAC (Throughput ×2)

### What Changed

Inner loop step changed from `k += 1` to **`k += 2`** — two products per pipeline stage, two DSPs:

```cpp
tap_mac:
for (int k = 0; k < NUM_TAPS; k += 2) {
#pragma HLS PIPELINE II = 1

    sample_t s0 = delay_line[idx0];
    sample_t s1 = delay_line[idx1];
    coeff_t  c0 = coeff_rom[k];
    coeff_t  c1 = coeff_rom[k + 1];

#pragma HLS BIND_OP variable = m0 op = mul impl = dsp   // Force DSP #1
#pragma HLS BIND_OP variable = m1 op = mul impl = dsp   // Force DSP #2
    m0 = (acc_t)s0 * (acc_t)c0;
    m1 = (acc_t)s1 * (acc_t)c1;
    acc += m0 + m1;
}
```

**Memory**: Cyclic partition (factor=2) hit II=2 (two reads can land in the same bank). Solution: **`ARRAY_PARTITION complete`** on both `delay_line` and `coeff_rom` — guarantees two arbitrary reads per cycle at II=1, at the cost of BRAM → LUT/FF.

### Key Rules Applied

| Rule            | Type            | How It Was Used                                                       |
| --------------- | --------------- | --------------------------------------------------------------------- |
| **R035 / R036** | Official        | II=1 on the 2-way MAC loop (64 iterations instead of 128)            |
| **P047**        | 🔵 User-defined | Stream I/O still outside MAC loop                                    |

### Synthesis Results (12 ns clock)

| Metric            | Iter 2 (1 MAC) | **Iter 3 (2 MAC)** | Change          |
| ----------------- | --------------- | ------------------- | --------------- |
| **tap_mac II**    | 1               | **1**               | —               |
| **Per-sample**    | ~138 cycles     | **~72 cycles**      | **1.9× faster** |
| **DSP**           | 1               | **2**               | +1 (budget met) |
| **BRAM_18K**      | 2               | **0**               | arrays in LUT   |
| **LUT / FF**      | 259 / 135       | **4199 / 4252**     | +16× (full partition cost) |
| Timing            | ✅ Met          | ✅ Met              | —               |

**csim**: PASS
**KB record**: `FIR128_Demo` / iteration #3

---

## 3-Iteration Summary

```
          Per-Sample    DSP   BRAM   LUT    Architecture
Iter 1 ── ~138 cycles ── 1 ─── 2 ──── 295 ─ Block-mode, serial MAC, BRAM delay line
Iter 2 ── ~138 cycles ── 1 ─── 2 ──── 259 ─ Continuous streaming (ap_ctrl_none)
Iter 3 ──  ~72 cycles ── 2 ─── 0 ─── 4199 ─ 2-way parallel MAC, full partition
              ↑ 1.9× throughput        ↑ BRAM→LUT trade-off
```

The progression moves from area-minimal correctness (iter 1) → true streaming without fixed packet length (iter 2) → doubled throughput via parallel MAC under a 2-DSP budget (iter 3).

---

## Rules Effectiveness Summary

| Rule            | Type            | Iterations | Key Outcome                                                                |
| --------------- | --------------- | ---------- | -------------------------------------------------------------------------- |
| **P047**        | 🔵 User-defined | 1, 2, 3    | Stream I/O always outside MAC loop → II=1 preserved across all iterations  |
| **P079**        | 🔵 User-defined | 1, 2       | Circular buffer in BRAM → 1 DSP + 2 BRAM baseline (no 128-tap shift reg)  |
| **R035 / R036** | Official        | 1, 2, 3    | Inner MAC loop `PIPELINE II=1` throughout                                  |

> **P047** is the single most impactful user-defined rule in this project. Without it, the natural instinct is to place `axis.read()` at the top of the MAC loop body — which would immediately break II=1 and require a debug cycle to diagnose. KB prevented this on the very first attempt.

---

*Generated from Cursor + HLS KB session logs. Project: FIR128_Demo. KB system: cursor-hls-kb v1.0 by AICOFORGE.*
