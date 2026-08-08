# Per-Primitive Scaling Ablation — results

**Status:** measurement complete. Three interpretation items open (§7).
**Data:** `DSE/synth_results/characterize_u280.csv` (74 rows), `DSE/synth_results/cp_diag.csv` (20 rows)
**Derived:** `DSE/synth_results/scaling_analysis.csv`, `DSE/synth_results/scaling_classes.csv`
**Target:** U280 (`xcu280-fsvh2892-2L-e`) @ 300 MHz, Vitis HLS 2023.1
**Configuration:** D = 10240, K = 64, binary datatype

---

## 1. The question

A composable library's central claim is that it exposes architecture knobs the
user can turn. That claim is normally left unmeasured. AeneasHDC advertises
three parallelism knobs (element, feature, class) and reports four
single-configuration results with no scaling curve. F5-HD selects PE count from
a power budget without characterising returns. Hyle sweeps datapath width but
does not decompose the result per primitive.

None of them answers the question a user of such a library actually has:

> If I turn this knob from 1 to 8, what do I get, and what does it cost?

This experiment answers that for every synthesizable primitive in HyperWeave,
one knob at a time.

## 2. Method

**Ablation, not configuration sweep.** Each curve varies exactly one knob and
holds every other at 1. Where a primitive accepts both knobs, only the isolated
slices are collected — DP varied at CP=1, and CP varied at DP=1. The interior of
the DP×CP grid is deliberately excluded: `proto[][]` is `ARRAY_PARTITION`'d
cyclically by CP on dim 1 and by DP on dim 2, so with both above 1 they contend
for the same array and no speedup would be attributable to either knob. Knob
interaction is a separate experiment.

**Metrics.** For knob value *n* against the *n*=1 baseline:

| | definition |
|---|---|
| speedup | latency(1) / latency(n) |
| ideal | the best a perfect implementation could reach (see below) |
| efficiency | speedup / ideal |
| LUT growth | LUT(n) / LUT(1) |
| return per area | speedup / LUT growth |

**Ideal is not always the knob value**, and getting it wrong makes correct
designs look broken:

- **DP, most primitives** — ideal = DP.
- **DP on `gemm` and `matvec`** — the sweep drives `CH_DP` and `CH_FP` from one
  variable, and these two primitives unroll in *both* dimensions, so at DP=8
  they hold 8 × 8 = 64 parallel MACs and ideal = DP². **This must be stated in
  the paper.** Scored against DP it produces meaningless 47×–64× "efficiencies".
- **CP** — the class loop runs in ⌈K/CP⌉ groups and a partial final group still
  costs a whole group, so ideal = K / ⌈K/CP⌉. At K=64 with CP ≤ 8 this reduces
  to CP; at K=10 with CP=8 it is 5.00, not 8.

**Phases.** Run in three parts so that no result could invalidate another:

| phase | runs | contents | file |
|---|---:|---|---|
| 1 — CP diagnostic | 20 | `similarity` only; K ∈ {10, 64, 256, 1024} × CP ∈ {1,2,4,8}, plus a DP control arm | `cp_diag.csv` |
| 2 — DP, no-CP primitives | 60 | 15 primitives × DP ∈ {1,2,4,8} | `characterize_u280.csv` |
| 3 — CP primitives | 14 | `similarity`, `convergence`; isolated DP and CP slices | `characterize_u280.csv` |

Phases 2 and 3 share one output file. Phase-3 rows are the ones where
`function` is `similarity` or `convergence`.

## 3. Result — every knob scales

**DP**, at DP=8:

| primitive | speedup | efficiency |
|---|---:|---:|
| convergence, flatten, init_centroids, place, similarity, transpose | 8.00× | 1.00 |
| cast | 7.99× | 1.00 |
| matvec | 63.85× | 1.00 † |
| bind, bundle, gather, scale, threshold | 7.98× | 1.00 |
| update | 7.97× | 1.00 |
| gemm | 46.97× | 0.73 † |
| permute | 3.91× | 0.49 |
| normalize | 1.77× | 0.22 |

† scored against DP² = 64; see §2.

**CP**, at CP=8:

| primitive | speedup | efficiency |
|---|---:|---:|
| convergence | 8.00× | 1.00 |
| similarity | 8.00× | 1.00 |

CP holds 1.00 efficiency across a 16× range of prototype counts — K = 64, 256
and 1024 all give exactly 8.00× at CP=8 (`cp_diag.csv`). A DP control arm in the
same sweep reaches 1.00 at the same problem sizes, which is what makes any CP
result attributable to CP rather than to the part, the tool, or the script.

**On its own this is validation, not a finding.** Fifteen of seventeen rows
reading "1.00, linear" tells a reader the knobs work as documented. The result
below is the one worth reporting.

## 4. Result — the cost of scaling varies by 6.8×

Identical 8× speedup, radically different price:

| primitive | LUT growth for 8× | return per area |
|---|---:|---:|
| flatten | 0.94× | 8.51 |
| transpose | 0.95× | 8.46 |
| place, init_centroids | 0.95× | 8.41 |
| gather | 0.96× | 8.30 |
| cast | 1.00× | 7.99 |
| bind | 1.31× | 6.09 |
| similarity | 1.38× | 5.78 |
| update | 2.46× | 3.24 |
| scale | 2.82× | 2.83 |
| convergence | 2.97× | 2.70 |
| threshold | 3.26× | 2.45 |
| bundle | 3.36× | 2.38 |
| normalize | 4.15× | 0.43 |
| convergence (CP) | 4.12× | 1.94 |
| **permute** | **6.38×** | **0.61** |

Five primitives get 8× while their LUT count *falls* — widening the datapath
lets the tool restructure memory access and the surrounding logic shrinks.
`permute` pays 6.38× for less than 4×.

**The claim:** every knob scales, but the cost of scaling spans nearly 7×
across primitives, and nothing in the source code or the API signature
distinguishes them. A composed design's area budget is therefore decided by
*which* primitives its knobs are spent on, not by how far they are turned.

That is also the actionable form for a DSE. Speed-only pruning finds one dead
axis (`normalize.DP`, 4× search-space reduction — thin). Cost-aware pruning —
pin any axis whose return per area is below 1.0 — catches `permute.DP` as well,
because it returns less speed than it consumes in logic.

## 5. What is measured and what is modelled

| claim | basis |
|---|---|
| latency at each knob setting | csynth estimate |
| LUT/FF/DSP/BRAM at each knob setting | csynth estimate |
| CP applies (trip count halves at CP=2) | **measured** — loop table, `cls_trip` 655,360 → 327,680 |
| CP is attributable (DP control at 1.00 in same sweep) | **measured** |
| 300 MHz | **assumed** — csynth target, not P&R verified |

**The open risk.** Every number here is a csynth estimate with no
place-and-route behind it. In the capacity-crossover study csynth reported 144
BRAM18K for a 40 MB codebook — short by roughly 32× — and that was only caught
by running Vivado. Nothing in this table has had that check. Before publication,
a representative subset (DP=1 and DP=8 for several primitives) should go through
`synth_design` + `place_design` to confirm resources and achieved Fmax. The
machinery already exists in `scripts/confirm_capacity_cliff.tcl`.

## 6. Not for the paper

The CP implementation was defective when first measured and was restructured
during this work: `UNROLL factor=CP` on an outer loop wrapping a `PIPELINE II=1`
inner loop replicated the datapath without letting the copies run concurrently,
and every lane contended for a single-ported `query`. `convergence_check`
additionally accumulated into one shared counter. The fix was a loop
interchange, a broadcast read of `query[i]`, and per-lane accumulators.

**Before/after is not a paper figure.** It presents our own bug fix as a result
and invites "why was it broken?" rather than "what did you learn?". The
pre-fix numbers stay in `git` history and in this section as internal evidence
that the fix worked; the paper reports the library as it ships.

The one sentence that *does* belong in the paper, in methodology and with no
numbers attached: per-primitive ablation is not redundant with a whole-design
sweep — it surfaced a knob in our own library that consumed 3.9× area for no
speedup, which a composed-design measurement would have averaged away.

For the record, at D=10240, K=64, CP=8: latency 665,894 → **81,925** cycles and
LUT 2,591 → **1,351**. The corrected design is 8.1× faster on half the logic.
`convergence` CP went from 0.61× (slower than serial) to 8.00×.

## 7. Open items — required before writing §4 of the paper

**`permute` is unexplained.** DP=2 gives 5,195 cycles; DP=4 gives 5,196 — zero
improvement for double the LUTs — then DP=8 halves it to 2,636. That is the same
shape as the CP defect: a knob setting that costs area and returns nothing.
Given what CP turned out to be, this should not be assumed benign. Settling it
costs 4 runs at DP ∈ {2, 3, 4, 6}.

**`normalize` needs a written explanation.** At 0.22 efficiency it is the only
primitive that genuinely exhibits reduction-tail saturation — a sqrt-then-divide
tail that no number of lanes shortens. It is the primitive that demonstrates the
phenomenon the ablation was designed to detect, and deserves a paragraph rather
than a table row.

**`gemm` 0.73 vs `matvec` 1.00.** Same two-dimensional unroll, same DSP count at
every step, different efficiency. One sentence of explanation, or a reviewer
asks.

## 8. Figures and tables to produce

**Figure A — cost of scaling (the headline).**
Scatter: x = LUT growth at DP=8, y = speedup at DP=8, one point per primitive,
labelled. Draw a diagonal `y = x` (break-even: speedup equals area spent).
Points above the line scale profitably; `permute` and `normalize` fall below.
Source: `scaling_classes.csv`, columns `function`, `speedup`, `LUT_growth`.
This is the figure that carries §4.

**Figure B — scaling curves.**
Line chart: x = knob value {1,2,4,8} on a log₂ axis, y = speedup, one line per
primitive, dashed diagonal for ideal. Most lines sit on the diagonal; `permute`
and `normalize` visibly depart. Source: `scaling_analysis.csv`, filtered to
`knob == "DP"`, columns `knob_value`, `speedup`, `function`.
Consider two panels — DP and CP — sharing a y-axis.

**Figure C — CP holds across prototype count.**
Line chart: x = CP {1,2,4,8}, y = speedup, one line per K ∈ {64, 256, 1024},
ideal diagonal. Three overlapping lines on the diagonal is the point: CP does
not degrade as the class count grows. Source: `cp_diag.csv`, arm 2 rows.
Small figure, or fold into Figure B's CP panel.

**Table 1 — per-primitive characterization.**
Columns: primitive, knob, speedup at 8, efficiency, LUT growth, return per area,
class. Source: `scaling_classes.csv` directly.
Footnote the `gemm`/`matvec` DP² convention.

**Do not plot the efficiency column on its own.** Fifteen bars at 1.00 is a
figure that says nothing.

## 9. Reproduction

```bash
source /tools/Xilinx/Vitis/2023.1/settings64.sh
cd ~/fpga-hdc-hls

# correctness first -- csim takes seconds, a sweep takes an hour
vitis_hls -f scripts/csim_search.tcl

# phase 1 -- CP diagnostic, 20 runs
vitis_hls -f scripts/sweep_cp_diag.tcl
python3 DSE/collect_cp_diag.py

# phase 2 -- 15 primitives, DP only, 60 runs
HDC_CH_PHASE=nocp vitis_hls -f scripts/sweep_characterize.tcl

# phase 3 -- similarity + convergence, 14 runs
HDC_CH_PHASE=cp   vitis_hls -f scripts/sweep_characterize.tcl

python3 DSE/collect_characterize.py     # -> characterize_u280.csv (74 rows)
python3 DSE/analyze_scaling.py          # -> scaling_analysis.csv, scaling_classes.csv
```

Problem size is overridable: `HDC_CH_D`, `HDC_CH_KP`. Target is overridable:
`HDC_PART`, `HDC_PERIOD`, `HDC_TAG` (see `scripts/target.tcl`).
