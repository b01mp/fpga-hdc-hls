# Architecture Narrative — how the library exploits parallelism while managing resources

The theme: the library exposes parallelism as a knob, but **each function's
hardware architecture decides how well that knob pays off** — ranging from perfect
linear scaling to reduction-limited sub-linear scaling, with the memory subsystem
as the enabler underneath all of it. Datatype specialization then changes what the
per-lane hardware actually *is* (LUT vs DSP). Four functions span the spectrum.

All numbers: Vitis 2026.1 csynth, D=256, xc7z020 @ 100 MHz.

---

## 1. `bind` — embarrassingly parallel (the cheapest speedup)

- **Operation:** element-wise combine two hypervectors, `out[i] = op(a[i], b[i])`.
- **Dependency structure:** each output element depends *only* on its own two
  inputs — **zero cross-element dependencies**. This is the easy case.
- **Architecture:** because nothing depends on anything else, you literally
  replicate the op into `DP` identical lanes. The vectors are stored in
  **cyclically-banked memory** so all `DP` lanes read/write in the same cycle.
  It's a wide, flat datapath — `DP` copies of a tiny op fed by `DP` memory banks.
- **Knob → hardware:** `DP` = number of lanes. DP=8 → 8 ops + 8 banks → 8
  elements/cycle.
- **Numbers:** 258 → 35 cycles (**7.4×**) at DP=8; LUT only 63 → 82 (each lane is
  one gate). Datatype picks the lane op: XOR = **0 DSP** (binary), multiply = **8
  DSP** (fixed, one per lane).
- **Insight:** near-perfect *linear* scaling at minimal cost. This sets the ceiling
  for what parallelism can achieve — the reference every other function is measured
  against.

## 2. `bundle` + `threshold` — parallel accumulation with a precision dial

- **Operation:** `bundle` superposes many HVs into a wide accumulator
  (`acc[i] += in[i]`); `threshold` collapses it back to an HV (majority for binary).
- **Dependency structure:** across the *dimension*, each `acc[i]` is independent —
  `acc[0]` and `acc[1]` never interact, so the D-axis parallelizes cleanly like
  `bind`. The dependency is across *time* (many vectors into the same acc), not
  across dimension.
- **Architecture:** `DP` independent accumulator lanes, each summing its own stream;
  `threshold` is `DP` parallel comparators. The **accumulator width** is a *second*,
  orthogonal knob — wider = more range (bundle more vectors before overflow) but more
  registers/logic per lane.
- **Knob → hardware:** `DP` = parallel accumulator lanes; `accumulator_bits`
  (Novelty 2) = precision-vs-resource per lane.
- **Numbers:** threshold 258 → 35 cycles (**7.4×**). Datatype changes the collapse
  cost sharply: binary majority = 378 LUT, **fixed passthrough = 45 LUT** — precision
  can make it *cheaper*, not costlier.
- **Insight:** easy (dimension-independent) parallelism, but with a **second dial —
  precision** — that the datatype/accumulator-width controls. This is where
  Novelties 1 and 2 meet the architecture.

## 3. `similarity_search` — the reduction (the architecturally rich one)

- **Operation:** compare a query against K prototypes, return the best match. Two
  nested reductions: sum a metric over D dimensions per prototype, then argmin/argmax
  across K prototypes.
- **Dependency structure:** **this is the hard case.** Both steps are *reductions* —
  combining many values into one. A sum has a dependency chain (each add needs the
  running total); an argmin has one too (each compare needs the best-so-far).
  Reductions don't replicate cleanly.
- **Architecture:**
  - The D-sum becomes a **partial-sum tree** — split into `DP` partial sums computed
    in parallel, then combined in a small log-depth tree (that's how you parallelize
    a reduction instead of a serial adder chain).
  - `CP` prototypes are compared in parallel, each with its own D-reduction — a
    **CP × DP grid** of MACs.
  - The prototype memory is banked `CP` ways (across prototypes) *and* `DP` ways
    (across dimensions) to feed the whole grid.
  - The argmin is a comparator tree over the `CP` parallel results.
- **Knob → hardware:** `DP` widens each dot-product; `CP` compares more prototypes at
  once; together = `CP × DP` parallel MACs.
- **Numbers:** 2569 → 341 cycles (**7.5×**) at DP=8/CP=2; LUT 539 → 1376. Datatype
  adds DSPs to the metric: Hamming = **0 DSP** → dot = **12 DSP** (bipolar) / **24
  DSP** (fixed). **Scaling is sub-linear** vs `bind` because the reductions pay
  pipeline-fill and tree-combine overhead — quantified by our estimator being −51% on
  this latency (it assumed perfect overlap; reality has reduction overhead).
- **Insight:** the interesting case — you *can't* just add lanes, you must build
  trees and accept sub-linear returns. This is the function where the architecture
  genuinely matters, and the best "real engineering, not a Vitis switch" slide.

## 4. `gather` / `place` — the memory architecture (feed the beast)

- **Operation:** `gather` reads a codebook row by index; `place` is the
  banking/placement directive.
- **Dependency structure:** **memory-bound, not compute-bound.** The challenge isn't
  arithmetic — it's getting data *out of memory* fast enough to feed the parallel
  compute above.
- **Architecture:** a single-port memory serves one element/cycle — a hard bottleneck
  for parallel lanes. Cyclically **partitioning** the codebook into `DP` banks
  (`place`'s job) creates `DP` independent ports → `DP` elements/cycle. `memory_space`
  then picks the physical tier: small/fast on-chip BRAM, larger on-chip URAM, or
  large off-chip HBM/DDR.
- **Knob → hardware:** `banking_factor` = parallel memory ports; `memory_space` =
  memory tier.
- **Numbers:** 258 → 34 cycles (**7.6×**).
- **Insight:** parallelism isn't only about compute — it's about **memory
  bandwidth**. You can build 8 compute lanes, but if memory delivers 1 element/cycle
  they starve. **Banking is what lets every other function's parallelism actually pay
  off** — the unsung enabler.

---

## The spectrum (the one slide that ties it together)

| Function | Parallelism pattern | Scaling | Why |
|---|---|---|---|
| `bind` | embarrassingly parallel | ~linear | no dependencies → just replicate lanes |
| `bundle`+`threshold` | parallel accumulation | ~linear | dimension-independent; + a precision dial |
| `similarity_search` | reduction (tree) | **sub-linear** | reductions can't fully overlap |
| `gather`/`place` | memory bandwidth | enables the rest | banking feeds the compute lanes |

**Closing point for the talk:** the library turns parallelism, precision, and memory
into *knobs*, but the *contribution* is architecting each primitive so those knobs
translate into real hardware efficiency — and understanding exactly where they stop
paying off (reductions). That understanding is what the DSE needs, and what the
estimator encodes.
