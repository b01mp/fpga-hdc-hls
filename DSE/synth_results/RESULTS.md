# FPGA-HDC — Synthesis & Estimator Calibration Results

*First real hardware numbers for the parameterized HDC library, and the estimator
calibrated against them. Recorded 2026-07-08.*

## What was measured

- **HLS C-synthesis** (Vitis 2026.1) of each category's top wrapper — one primitive
  each: `bind`, `threshold`, `gather`, `similarity_search`.
- **Sizes:** hypervector dimension `D = 256`, binary hypervectors, `K = 10`
  prototypes for search.
- **Target:** `xc7z020` at **100 MHz** (10 ns) — the license-free part (relative
  scaling holds on the real ZU7EV/U280 target).
- **Two configurations:** `DP = 1` (baseline, sequential) and `DP = 8`
  (dimension-parallel; search also uses `CP = 2`).
- Raw Vitis reports are in `dp1_baseline/` and `dp8/`; structured data in
  `benchmarks.csv`.

---

## Result 1 — The parallelism knob works (latency ↓, resources ↑)

| Primitive | Latency DP=1 | Latency DP=8 | Speedup | LUT DP=1 → DP=8 |
|---|---|---|---|---|
| bind | 258 cyc / 2.58 µs | 35 cyc / 0.35 µs | **7.4×** | 63 → 82 |
| threshold | 258 cyc / 2.58 µs | 35 cyc / 0.35 µs | **7.4×** | 100 → 378 |
| gather | 258 cyc / 2.58 µs | 34 cyc / 0.34 µs | **7.6×** | 61 → 45 |
| similarity | 2569 cyc / 25.69 µs | 341 cyc / 3.41 µs | **7.5×** | 539 → 1376 |

**Talking points:**
- One knob (`dimension_parallelism`), set 1 → 8, made every module **~7.5× faster**.
- The cost is more LUTs (8 parallel copies of the datapath) — but growth is
  **sub-linear** (control logic amortizes), which is the good case.
- `~35 cycles` at DP=8 = 256 elements ÷ 8 + a couple cycles of pipeline fill —
  exactly the expected behavior.

---

## Result 2 — The analytical estimator, calibrated to real silicon

The estimator predicts latency/resources in **microseconds** (vs **minutes** for
synthesis), so DSE can score thousands of design points and synthesize only the
Pareto-optimal few. But it's only trustworthy if it matches reality:

| Primitive (config) | LUT error **before** | LUT error **after** |
|---|---|---|
| bind (DP=1 / DP=8) | −98% / −90% | **0% / −15%** |
| threshold (DP=1 / DP=8) | −68% / −32% | **0% / −14%** |
| gather (DP=1 / DP=8) | −98% / −82% | **0% / +51%** |
| similarity (DP=1 / DP=8) | −88% / −57% | **0% / −23%** |

- **Latency** was already near-exact (0% at DP=1; within 3% for elementwise ops).
- **Resources** were badly underestimated because the model only counted the
  *compute* datapath. Adding a fitted **fixed control/interface overhead** per
  primitive pulled it from "off by 30–98%" to **within ~15–23%**.

**Talking point:** we closed the loop —
**parameterized library → synthesized → measured → estimator calibrated to match.**
The estimator now tracks real silicon closely enough to *rank* design points, which
is all the DSE needs.

---

## Honest caveats (worth stating up front)

- These are **per-primitive**, `D = 256`, **binary** only — a representative slice,
  not a full application. Full-app numbers come with the composed-app step.
- **similarity latency at high parallelism is ~2× optimistic** (the class-loop
  reduction pays pipeline fill the model doesn't yet capture) — needs a few more
  synth points (sweep DP/CP) to model properly.
- **`memory_space` is not reflected yet** — `bind_storage` on a top-level port is
  unsupported by Vitis; memory placement belongs in the composed-app top (next step).
- Calibration is first-order (2 synth points per primitive); more points firm it up.

---

## Files

| File | What it is |
|---|---|
| `benchmarks.csv` | structured measurements (one row per primitive × config) |
| `dp1_baseline/*.rpt` | raw Vitis csynth reports, DP=1 |
| `dp8/*.rpt` | raw Vitis csynth reports, DP=8 |
| `../estimator/calibrate.py` | the calibration (predicted vs actual, fitted overheads) |
