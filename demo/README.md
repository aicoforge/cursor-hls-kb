# HLS Knowledge Base — Demo Walkthrough Guide

[中文](./README-ZH.md) | English

---

> **Project Name**: cursor-hls-kb **Version**: v1.0
> 
> **Target Audience**: Cursor HLS User (newcomers and rule contributors)

---

## Purpose

This guide walks through the 6 demo projects shipped with the KB and describes how the Knowledge Base operates in practice. The demos are real Cursor + Vitis HLS sessions, not simplified teaching examples.

After reading, you can:

- Determine, based on what the KB returns, whether a new design is likely to reach II=1 on iter 1
- Recognize when architectural guidance from the user is needed, and how that guidance is converted into future P-rules
- Pick a starting demo to read for your own situation

---

## The Two Usage Patterns

The 6 demos split into two groups based on whether the KB already contains mature P-rules for that design class. This distinction helps estimate how many iterations a design will take.

### Pattern A — Mature P-rules exist; specification prompts are sufficient

| Demo          | P-rules retrieved (Track 2)      | Iter 1 result                 | Prompt style                                   |
| ------------- | -------------------------------- | ----------------------------- | ---------------------------------------------- |
| **Systolic**  | 5 (P085, P084, P090, P094, P047) | II=1, only timing to relax    | "Design a systolic array... follow KB rules"   |
| **Matmul3x3** | 3 (P047, P035, P039)             | II=1 (clock relaxed to 20 ns) | FIFO interface + matrix size                   |
| **FIR128**    | 2 (P047, P079)                   | II=1, timing met at 12 ns     | "AXI streaming, minimize area"                 |
| **CORDIC**    | 2 (P071, P072)                   | II=1, 0 DSP                   | Algorithm spec (mode, fixed-point, iterations) |

In Pattern A, prior testing has already organized the HLS architectural decisions for this design class (where to place `PIPELINE`, how to partition arrays, where stream I/O may not appear) as P-rules. The user describes the design goal, and Cursor combines the KB rules to complete the optimization.

### Pattern B — Few P-rules; architectural guidance needed; produces new draft rules

| Demo            | P-rules retrieved (Track 2) | Iter 1 result                 | What the user provides                       |
| --------------- | --------------------------- | ----------------------------- | -------------------------------------------- |
| **DFT (16-pt)** | 1 (P003)                    | II=1, timing fails (−0.84 ns) | Iter 2–4: II vs timing trade-off direction   |
| **FFT (16-pt)** | 1 (P035)                    | II=2 at 25 ns, missed II=1    | Iter 2: ping-pong, template banks, MAC split |

In Pattern B, the KB contains limited rules for the design class. The user must guide architectural decisions through follow-up prompts. Each successful piece of guidance is recorded as a draft rule in the file header `Applied Rules` block`. A KB maintainer can later promote it to a numbered `P###`.

```cpp
// Applied Rules (FFT_Demo iter2):
//  - R035: inner loops use #pragma HLS PIPELINE
//  - P035: no full-buffer memcpy between stages
//  - (no code): when a single loop iteration writes to the same logical
//               array twice, use complete partition or dual-port memory
//               to avoid a carried dependence forcing II>1.
//  - (no code): prefer ping-pong buffering over in-place updates for
//               multi-stage pipelined algorithms.
```

DFT produced 3 draft rules; FFT produced 4. After review and numbering, subsequent designs of the same class follow the Pattern A flow.

---

## Rule Feedback Loop

The KB rule library expands through a two-stage cycle: Pattern B produces draft rules during iterative debugging, which the KB maintainer reviews and promotes to `P###`; subsequent designs of the same class then enter Pattern A, where a specification prompt is sufficient for iter 1 to reach II=1.

**Pattern B (rules not yet established)**
New design class, KB has few P-rules → User provides architectural guidance in follow-up prompts → Iter 2+ debug, draft rules written to file header → KB maintainer reviews, promotes to `P###`

↓ New P-rules enter KB ↓

**Pattern A (rules ready)**
Same design class, mature P-rules available → User provides specification only → Iter 1 reaches II=1

In other words, optimization experience accumulated in one project becomes available for subsequent designs of the same class. This is how the KB rule library expands over time.

---

## How to Apply This to Your Own Design

1. Start with a specification prompt describing the design's function, interface, and constraints. End with `follow KB rules`.
2. Observe what Track 2 returned. Many P-rules typically indicates Pattern A; few or no P-rules indicates Pattern B.
3. If iter 1 reaches II=1 with timing met, the design is in Pattern A. Iterate further for area or throughput as needed.
4. If iter 1 misses the target, the design is in Pattern B. In the next prompt, adjust one architectural parameter at a time (II target, pipeline placement, dependency resolution, partition strategy).
5. Successful guidance is recorded as `(no code)` entries in the file header. When enough draft rules accumulate, notify the KB maintainer for review and promotion to `P###`.

> **Why "one parameter at a time" is recommended in Pattern B**: HLS optimization results are context-dependent. The same `complete partition` enables II=1 in a systolic design but causes DFT iter 1 to miss timing. Changing one variable per iteration preserves cause-and-effect traceability, which also makes the resulting draft rules easier to verify when promoted.

---

## Demo Index

| File                | Domain               | Iters | Pattern | What it shows                                               |
| ------------------- | -------------------- | ----- | ------- | ----------------------------------------------------------- |
| `demo_systolic.md`  | Systolic GEMM        | 3     | A       | One prompt → II=1; 5 P-rules cover the architecture         |
| `demo_matmul3x3.md` | Matrix multiply      | 3     | A       | FIFO interface; DATAFLOW overlap of 3 matrices in flight    |
| `demo_fir128.md`    | FIR filter (128-tap) | 3     | A       | Streaming, circular BRAM buffer, 2-way parallel MAC         |
| `demo_cordic.md`    | sin/cos              | 3     | A       | Shift-add only (0 DSP); DATAFLOW vs PIPELINE vs time-shared |
| `demo_dft.md`       | DFT (16-pt)          | 4     | B       | II vs timing trade-off; 3 draft rules emerged               |
| `demo_fft.md`       | FFT (16-pt)          | 2     | B       | Ping-pong + template banks for II=1; 4 draft rules emerged  |

---

## Suggested Reading Order

- **First time using the KB**: read `demo_systolic.md` — shows the one-prompt → II=1 flow and the role of each P-rule.
- **To understand the rule contribution flow**: read `demo_fft.md` — traces 4 draft rules from concrete debug rounds (HLS warning 200-880, sparsemux on bank selection, etc.) to file header comment of `code snapshot` ready for promotion.
- **For design-space exploration**: read `demo_dft.md` — 4 iterations covering the trade-offs among II=1, timing, and area, including the practice of running a quick pre-check before committing iter 4.
- **To compare optimization styles**: read `demo_cordic.md` — three implementations of the same algorithm (DATAFLOW, single PIPELINE, time-shared) presenting the trade-offs with synthesis numbers.

---

**Version**: v1.0 **Last Updated**: 2026-04-16

---

*KB system: cursor-hls-kb v1.0 by AICOFORGE.*
