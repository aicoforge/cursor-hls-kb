# Demo: N=16 Fixed-Point DFT — AI-Driven HLS Design via KB Rules

> **Project**: `DFT_Demo` | **Tool**: Vitis HLS 2023.2 | **Target**: xc7z020clg400-1
> 
> This demo shows how Cursor + KB iterates a 16-point fixed-point DFT through **4 iterations**, navigating the classic HLS tension between **II (throughput)** and **timing closure** — and how each trade-off round produces an **unnumbered P-rule candidate** that can be contributed back to the KB.

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
Make a DFT that takes N=16 complex inputs and outputs N=16 results.
Use fixed-point numbers and a simple double loop with pipeline.
Use precomputed sin/cos values and keep the design simple and correct.
Follow KB rules, and save to DFT_Demo project.
```

---

## Iteration 1 — Baseline: Maximum Parallelism, II=1

### KB Dual-Track Query

| Track                         | Result                                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| **Track 1** — similar designs | `GET /api/design/similar?project_type=dft` → empty → Path B (derive from rules)               |
| **Track 2** — effective rules | **P003** (overlap load/compute/store), **R035** (inner loop PIPELINE), **R036** (II=1 target) |

> Track 2 pre-step confirmed the 13 available categories (`code`, `memory`, `pipeline`, `synthesis`, `optimization`, `dataflow`, `fir`, `systolic`, …) via `GET /api/rules/categories`.

### Architecture

```
xr[N], xi[N]  (complex input, ap_fixed<16,6>)
COS_TABLE[256], SIN_TABLE[256]  (precomputed twiddle, twiddle.inc)
        │
  outer loop k = 0..15
    inner loop n = 0..15
    #pragma HLS PIPELINE II=1      ← hot loop
        │
  Xr[k] += xr[n]*cos(2πkn/16) - xi[n]*sin(2πkn/16)
  Xi[k] += xr[n]*sin(2πkn/16) + xi[n]*cos(2πkn/16)
        │
Xr[N], Xi[N]  (complex output)
```

All input and twiddle arrays fully partitioned to supply 4 simultaneous reads per pipeline cycle:

```cpp
#pragma HLS ARRAY_PARTITION variable=xr        complete
#pragma HLS ARRAY_PARTITION variable=xi        complete
#pragma HLS ARRAY_PARTITION variable=COS_TABLE complete
#pragma HLS ARRAY_PARTITION variable=SIN_TABLE complete
```

### Key Rules Applied

| Rule     | Type            | How It Was Used                                                                                                           |
| -------- | --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **P003** | 🔵 User-defined | Load and compute overlap: input arrays partitioned so the inner pipeline loop reads operands every cycle without stalling |
| **R035** | Official        | `#pragma HLS PIPELINE II=1` on the inner `n` loop                                                                         |
| **R036** | Official        | II=1 is the explicit target; partition strategy is chosen to support it                                                   |

> **Data type note** (surfaced during csim, recorded outside Applied Rules): `ap_fixed<16,4>` overflows at the DFT accumulation peak (~8.0). Widened to `ap_fixed<16,6>` before synthesis — avoiding a silent numerical mismatch that csim would otherwise have flagged.

### Synthesis Results (10 ns clock)

| Metric                   | Value                            |
| ------------------------ | -------------------------------- |
| Inner loop II (ii_bneck) | **1** ✅                          |
| Top Interval (ii_top)    | **262**                          |
| Latency (cycles)         | **261**                          |
| DSP                      | **4**                            |
| LUT / FF                 | **3380 / 521**                   |
| BRAM_18K                 | **0** (twiddle in LUT/FF)        |
| Timing                   | ❌ Slack **−0.84 ns** (violation) |

**csim**: PASS (impulse, single-frequency complex exponential, random) **KB record**: `DFT_Demo` / iteration #1, rules recorded: P003, R035, R036

> II=1 is achieved, but the complete partition of all four 256-element twiddle arrays creates a large combinational mux/fanout that exceeds the 10 ns budget. The timing failure is a direct consequence of maximum parallelism — the same partition that enables II=1 also lengthens the critical path.

---

## Iteration 2 — Reduce Parallelism: Timing First

### User Prompt

```
For iter2, make the design easier to meet timing by reducing parallel
operations per cycle, even if it slightly increases latency or II.
```

### What Changed

| Item                      | Iter 1                     | **Iter 2**                                 |
| ------------------------- | -------------------------- | ------------------------------------------ |
| `xr` / `xi` partition     | `complete` (16 ports)      | `cyclic factor=4` (4 banks)                |
| `COS/SIN_TABLE` partition | `complete` (large LUT mux) | **none** → single-port ROM → **2× BRAM18** |
| Inner PIPELINE            | `II=1`                     | **`II=4`**                                 |
| Clock                     | 10 ns                      | **15 ns**                                  |

Removing twiddle table partition eliminates the wide combinational mux entirely. Setting II=4 reduces the number of overlapping operations per cycle, shortening every per-cycle data path.

### Synthesis Results (15 ns clock)

| Metric           | Iter 1     | **Iter 2**     | Change         |
| ---------------- | ---------- | -------------- | -------------- |
| ii_bneck         | 1          | **4**          | −throughput    |
| Latency (cycles) | 261        | **1026**       | +3.9×          |
| LUT              | 3380       | **526**        | **−84%**       |
| BRAM_18K         | 0          | **2**          | twiddle → BRAM |
| Timing           | ❌ −0.84 ns | ✅ **+0.76 ns** | **Fixed**      |

**csim**: PASS **KB record**: `DFT_Demo` / iteration #2 (`timing_met: true`, `ii_bneck: 4`, `success: false` — II worsened from 1 → 4)

> Timing is now closed, but at the cost of II degrading from 1 to 4 and latency quadrupling. This establishes the two ends of the trade-off space: iter 1 has best II but fails timing; iter 2 meets timing but has worst II. The next iterations navigate the middle ground.

---

## Iteration 3 — Balance: II=2 at 10 ns (Timing Explored)

### User Prompt

```
Try increasing array partition factor or partial unrolling to improve II from 4 toward 1. 
Avoid full partition or full unroll that may break timing.
Target a balanced design (e.g., II=2) with timing met at 10 ns.
```

### What Changed

```cpp
// Moderate partition on all arrays: 2 banks each
#pragma HLS ARRAY_PARTITION variable=xr        cyclic factor=2
#pragma HLS ARRAY_PARTITION variable=xi        cyclic factor=2
#pragma HLS ARRAY_PARTITION variable=COS_TABLE cyclic factor=2
#pragma HLS ARRAY_PARTITION variable=SIN_TABLE cyclic factor=2

// Target II=2 (between iter1's 1 and iter2's 4)
#pragma HLS PIPELINE II=2
```

Attempts during this iteration:

- `cyclic factor=8` → slack −1.39 ns (worse than iter1)
- `cyclic factor=4` → slack −0.84 ns (same as iter1)
- `UNROLL factor=2` with II=2 → DSP jumps to 8, slack −1.39 ns (discarded)
- **`cyclic factor=2`** → slack −0.84 ns, II=2 ✅ (best balance found)

### Synthesis Results (10 ns clock)

| Metric           | Iter 2    | **Iter 3**             | Change                |
| ---------------- | --------- | ---------------------- | --------------------- |
| ii_bneck         | 4         | **2**                  | **improved** ✅        |
| Latency (cycles) | 1026      | **517**                | −50%                  |
| DSP              | 4         | **4**                  | —                     |
| LUT / FF         | 526 / ?   | **547 / 403**          | similar               |
| BRAM_18K         | 2         | **4**                  | twiddle still in BRAM |
| Timing           | ✅ (15 ns) | ❌ **−0.84 ns** (10 ns) | not met               |

**csim**: PASS **KB record**: `DFT_Demo` / iteration #3 (`timing_met: false`, `ii_bneck: 2`, `success: true` — II improved 4 → 2)

> II=2 is achieved and latency is halved vs iter2. Timing still fails at 10 ns with the same −0.84 ns gap seen in iter1 — this is a structural HLS estimation characteristic of this data path on this device, not addressable by partition tuning alone. The question becomes: does a 12 ns clock keep II=2?

### Quick Check (before committing iter 4)

User asked: *"Is 12 ns likely to keep II=2?"* Before committing a new iteration, the same `dft.cpp` was re-synthesized with only `create_clock -period 12` changed. Result:

| Item           | 12 ns result                                         |
| -------------- | ---------------------------------------------------- |
| Inner II       | **achieved=2, target=2** (II=2 preserved)            |
| Top slack      | **≈ +0.27 ns** (no timing violation)                 |
| Estimated path | ≈ 8.488 ns (vs 8.143 ns at 10 ns — normal variation) |

The −0.84 ns gap at 10 ns was on the order of 0.8–1 ns; a 12 ns budget comfortably absorbs it **without touching the schedule**. This confirmed the plan for iter 4.

---

## Iteration 4 — Final: II=2 + 12 ns, Timing Closed

### User Prompt

```
OK, please use the above configuration to create iter4.
(cyclic factor=2 + II=2 architecture, clock fixed at 12 ns)
```

### What Changed

RTL and pragmas are **identical to iter3**. Only the clock constraint is updated:

```tcl
# run_hls.tcl
create_clock -period 12   ;# was 10 in iter3
```

The 10 ns timing gap was consistently −0.84 ns across multiple experiments (estimated path ~8.14 ns vs budget ~7.3 ns). At 12 ns the effective timing budget rises above 8.14 ns, closing the gap without any architectural change.

### Synthesis Results (12 ns clock)

| Metric                | Iter 3 (10 ns) | **Iter 4 (12 ns)** | Change         |
| --------------------- | -------------- | ------------------ | -------------- |
| ii_bneck              | 2              | **2**              | —              |
| Top Interval (ii_top) | 518            | **517**            | —              |
| Latency (cycles)      | 517            | **516**            | —              |
| Top Slack             | −0.84 ns ❌     | **+0.27 ns** ✅     | **Fixed**      |
| DSP / LUT / FF        | 4 / 547 / 403  | **4 / 533 / 280**  | slightly lower |
| BRAM_18K              | 4              | **4**              | —              |

**csim**: PASS **KB record**: `DFT_Demo` / iteration #4 (`timing_met: true`, `clock_period_ns: 12.0`, `ii_bneck: 2`, `rules_applied: []` — clock-only change)

---

## How the Unnumbered P-Rule Candidates Emerged

This is the part worth studying if you plan to **contribute your own P-rules to the KB**. Each iteration's **design intent** had to be captured somewhere, but none of iter 2/3/4's core reasoning mapped cleanly to an existing `P###` / `R###` — so each was recorded as an **unnumbered rule** in the file header.

### Where unnumbered rules live (the mechanics)

| Location                                            | Unnumbered rules                                                                                      |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **`code_snapshot` file header `// Applied Rules:`** | **YES** — as plain `rule_text` bullets, not prefixed with `P###:` / `R###:`                           |
| **API `rules_applied` array**                       | **NO** — only entries with a real `rule_code` go here; unnumbered drafts do **not** update statistics |

So every iteration can (and should) carry design-intent bullets in the header comment, even when no numbered rule matches. A KB maintainer can later promote them to `P###`.

### Derivation trace (iter-by-iter)

| Iter       | Symptom / decision point                                                                | Concrete choice made                                       | Unnumbered rule text recorded in `dft.cpp` header                                                                                         |
| ---------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **iter 1** | First iteration, no prior DFT records; fixed-point range issue found in csim            | Maximum parallelism (complete partition + II=1)            | *(none)* — all reasoning mapped to P003 / R035 / R036; data-type fix recorded under **Optimizations Applied**, not Applied Rules          |
| **iter 2** | User accepts II / latency regression to close timing                                    | `cyclic factor=4`, no twiddle partition, II=4, 15 ns clock | Relaxed II and banking to trade throughput for timing closure.                                                                            |
| **iter 3** | Balanced II=2 at 10 ns is structurally blocked; HLS estimate ~8.14 ns vs budget ~7.3 ns | Keep `cyclic/2 + II=2`, document the estimation gap        | 10 ns HLS estimate still slightly negative on top-level path; use Vivado phys_opt/route or small frequency margin if hard 10 ns required. |
| **iter 4** | Same RTL as iter 3; only the clock is relaxed                                           | `create_clock -period 12`                                  | Clock period adjustment for setup closure when ii_bneck unchanged vs iter3.                                                               |

### From unnumbered text → formal P-rule: category selection

When promoting these three unnumbered entries into `hls_rules`, **category choice matters**. Below is the classification actually arrived at during the session, with reasoning preserved for future contributors:

| Unnumbered text (source iter)                                              | Recommended `category`                 | Why                                                                                                                           |
| -------------------------------------------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| iter 2: relax II + banking to trade throughput for timing                  | **`optimization`** *(alt: `pipeline`)* | Core message is a **design-space trade-off** (II ↔ memory structure ↔ timing), not a single-pragma directive                  |
| iter 3: HLS top-path estimate slightly negative → Vivado backend or margin | **`synthesis`**                        | Explicitly about **HLS estimate vs backend flow** (`phys_opt`, `route`) and clock margin — a **constraint / closure** concern |
| iter 4: clock relaxation when ii_bneck unchanged                           | **`synthesis`**                        | Clock-period adjustment and the principle of not judging success by `ii_bneck` alone live most cleanly in **synthesis**       |

Each of the three rules describes a **cross-cutting HLS methodology** concern (II vs banking, HLS estimate vs backend closure, clock-only tuning), so **technical categories** (`optimization`, `synthesis`) fit more naturally than any single-purpose label — a rule filed in a technical category is discoverable by any future design that hits the same class of decision.

> **Also worth adding as `dft`** — the KB already has application categories (`fir`, `systolic`, `cordic`, …) and Track 2 Step 0 queries them first (`category=${project_type}`) when a matching application is inferred. Adding **`dft`** alongside the technical category means a future DFT project's Step 0 retrieves these three rules directly, while the technical-category query path (`optimization` / `synthesis`) keeps them discoverable for non-DFT designs facing the same trade-offs. The two are merged and do not override each other.

### Guidance for your own unnumbered rules

1. **Write during the iteration, not after.** If the decision was non-trivial but no `P###`/`R###` matches, add an unnumbered bullet to the file header Applied Rules immediately.
2. **Say the principle, not the parameters.** "Relax II and banking to trade throughput for timing" travels to other designs; "set II=4 and cyclic factor=4" does not.
3. **Pick the category by the rule's nature.** Use a technical category (`optimization`, `synthesis`, `pipeline`, `memory`, …) matching what the rule is actually about.
4. **Record it alongside synthesis numbers.** Unnumbered rules with no accompanying measurement are hard for a reviewer to validate.

Example header format (iter 4, as stored in the KB `code_snapshot`):

```cpp
// Applied Rules:
// - R035: Apply #pragma HLS PIPELINE to innermost or performance-critical loops.
// - R036: Always target Initiation Interval (II) = 1 so the loop accepts
//         new data each cycle.
// - (no code): Clock period adjustment for setup closure when ii_bneck
//              unchanged vs iter3.
// ============================================================================
```

The first two are numbered (and go into the API's `rules_applied`); the third is the unnumbered draft — shown here with the `(no code)` marker used consistently across demos, so it is easy to spot and later promote.

---

## 4-Iteration Summary

```
         II    Timing    Slack     LUT    BRAM   Clock    Strategy
Iter 1 ─  1 ─ ❌ fail ─ −0.84 ns ─ 3380 ─  0 ─ 10 ns ─ complete partition, max parallelism
Iter 2 ─  4 ─ ✅ met  ─ +0.76 ns ─  526 ─  2 ─ 15 ns ─ no partition, II=4, clock relaxed
Iter 3 ─  2 ─ ❌ fail ─ −0.84 ns ─  547 ─  4 ─ 10 ns ─ cyclic/2, II=2, balance attempt
Iter 4 ─  2 ─ ✅ met  ─ +0.27 ns ─  533 ─  4 ─ 12 ns ─ same as iter3, clock to 12 ns ✓
              ▲ target met                        ▲
              II=2 + timing                   final answer
```

The design journey traces a clear path: iter 1 maximizes II but breaks timing → iter 2 fixes timing at the cost of II → iter 3 finds the structural balance (II=2, cyclic/2) → iter 4 closes timing with a minimal clock relaxation while preserving the iter 3 architecture.

---

## Rules Effectiveness Summary

| Rule                                    | Type               | Iterations | Key Outcome                                                                                                     |
| --------------------------------------- | ------------------ | ---------- | --------------------------------------------------------------------------------------------------------------- |
| **P003**                                | 🔵 User-defined    | 1, 2, 3, 4 | Guides array partition strategy: how much to partition determines the load/compute overlap and the resulting II |
| **R035**                                | Official           | 1, 2, 3, 4 | `#pragma HLS PIPELINE` on the inner `n` loop throughout all iterations                                          |
| **R036**                                | Official           | 1, 2, 3, 4 | II=1 is the stated target; achieved in iter 1, then traded for timing in iters 2–4                              |
| **Throughput ↔ timing trade-off**       | ⚪ Unnumbered draft | 2          | Captures the iter 2 decision to accept II / latency regression in exchange for timing closure                   |
| **HLS estimate vs backend flow**        | ⚪ Unnumbered draft | 3          | Flags that HLS top-path negative slack may still route cleanly in Vivado; avoids over-tuning HLS pragmas        |
| **Clock-only tuning when II unchanged** | ⚪ Unnumbered draft | 4          | Formalizes the "clock-period-only" iteration pattern when `ii_bneck` is already at target                       |

> **P003 as a navigation rule**: P003 does not prescribe a fixed partition factor — it establishes the principle that partition depth controls load/compute overlap. This is what makes it useful across all four iterations: iter 1 applies it maximally (complete), iter 2 removes it entirely, and iters 3–4 apply it at the level (`cyclic factor=2`) that best balances II and timing margin.

> **Takeaway for KB contributors**: the three unnumbered drafts above came from **real decision points** in iter 2, 3, and 4 — each one a reasoning step that no existing `P###`/`R###` cleanly covered. Record them as plain text bullets in the file header alongside numbered rules; when a KB maintainer promotes them, classify iter 2's under **`optimization`** and iter 3/4's under **`synthesis`**.

---

*Generated from Cursor + HLS KB session logs. Project: DFT_Demo. KB system: cursor-hls-kb v1.0 by AICOFORGE.*
