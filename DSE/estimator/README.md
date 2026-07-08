# FPGA-HDC Cost Estimator

A fast, white-box model that predicts a design's **latency, throughput, and
resource usage** from its parameters — *without* running Vitis synthesis.
Synthesis takes minutes per point; this takes microseconds, so the DSE can score
thousands of design points and only synthesize the Pareto-optimal handful.

The estimator and the parameterized HLS library are two views of one cost model:
the library **realizes** the hardware (via pragmas), the estimator **predicts** it.

---

## 1) How to run it

All commands run from the `DSE/` directory.

### A. Estimate a single design point (CLI)
```powershell
cd C:/USC/fpga-hdc-hls/DSE
python -m estimator.cli estimate
```
Prints latency, throughput, resource usage + utilization %, feasibility, and the
per-stage cycle breakdown for the default point (ISOLET-like, binary, DP=1).

Override any parameter with `--set key=value` (repeatable):
```powershell
python -m estimator.cli estimate --set dp=64
python -m estimator.cli estimate --set family=fixed --set elem_bits=8 --set proto_bits=8 --set dp=64
python -m estimator.cli estimate --set family=fixed --set elem_bits=8 --set dp=64 --set memory_space=uram --set target_fpga=xcu280
```

### B. Sweep the parameter space + Pareto front (CLI)
```powershell
python -m estimator.cli sweep
```
Prints the full grid (latency/throughput/resources vs DP and CP) and then the
**Pareto front** — the fast↔small shortlist worth synthesizing.

### C. Use it programmatically (how Haoyang's DSE calls it)
The CLI is just a convenience wrapper. The real interface is the `estimate()`
function — import it and call it in a loop:
```python
from estimator.estimate import estimate
from estimator.designpoint import DesignPoint

# build a validated point
pt = DesignPoint.default(dp=64, family="fixed", elem_bits=8, memory_space="uram",
                         target_fpga="xcu280")
print(pt.validate())          # {'errors': [...], 'warnings': [...]}

metrics = estimate(pt)        # accepts a DesignPoint or a plain dict
print(metrics["latency_us"], metrics["util_pct"], metrics["feasible"])
```
For a batch, use `estimator.sweep.sweep(base, grid)` + `estimator.sweep.pareto(...)`,
or write your own search loop over `estimate()`.

### D. Requirements
Pure Python 3 standard library — no third-party packages, nothing to install.

---

## 2) Contents

### `designpoint.py` — the INPUT object
- Defines `DesignPoint`, a dataclass bundling all app params (`hv_dim`,
  `num_features`, `family`, `elem_bits`, …) and arch params (`dp`, `fp`, `cp`,
  `pipeline_mode`, `memory_space`, `banking_factor`, `target_fpga`, `clock_ns`).
- `to_dict()` / `from_dict()` / `default(**overrides)` — build points easily.
- `validate()` — returns `{errors, warnings}`: **errors** = illegal (out of range,
  unknown enum, memory tier not on the device); **warnings** = legal but
  suboptimal (e.g. `dp` doesn't divide `hv_dim`).
- `is_legal()` — True if no errors.
- You never *run* this file; you import it to construct/validate points.

### `models/device.py` — the resource CEILINGS
- `Device` dataclass + `DEVICES` registry for `xc7z020`, `xczu7ev` (ZCU104),
  `xcu280` (Alveo, HBM).
- Holds LUT / FF / DSP / BRAM36 / URAM counts (+ HBM bandwidth) per part.
- `get_device(name)` — lookup used to compute utilization % and feasibility, and
  to gate which `memory_space` values are legal (Novelty 4).

### `models/datatypes.py` — per-datatype op cost (Novelty 1 tie-in)
- `Resources` bundle (LUT/FF/DSP/BRAM/URAM) with `+` and `.scale(k)`.
- Per-family op costs: `bind_lane` (XOR for binary ≈ 1 LUT, multiply for
  fixed/integer ≈ 1 DSP, add-exponents for pow2), `add_lane`, `compare_lane`,
  `mac_lane`.
- The named constants at the top (`LUT_PER_XOR`, `DSP_PER_MUL`, …) are what
  `calibrate.py` fits against real synthesis.
- This is where the estimator *quantifies* why bipolar/fixed cost more than binary.

### `models/primitives.py` — per-primitive latency + resource formulas
- One `cost_*` per library primitive: `cost_bind`, `cost_bundle`,
  `cost_threshold`, `cost_gather`, `cost_quantize`, `cost_similarity`.
- Each returns `(latency_cycles, Resources)` for one invocation; latency assumes a
  pipelined loop, so a D-length pass with DP lanes is `ceil(D/DP)` cycles.
- `mem_blocks(bits, memory_space, banking, device)` — codebook/prototype memory in
  BRAM or URAM blocks (off-chip tiers use none).
- Mirrors the HLS headers 1:1: add a primitive → add its `cost_*`.

### `compose.py` — stitch primitives into an app
- `build_classification_infer(app, arch, device)` — builds the stages of the
  classification `infer` pipeline (encode = F×[quantize→gather→bind→bundle],
  then threshold, then similarity_search, plus the memories).
- `compose_latency(stages, pipeline_mode)` — end-to-end latency: **sum** of stages
  for `separate`, **max** (+ fill) for `streamed`/`fused`.
- `bottleneck_cycles(...)` — cycles-per-sample that set throughput.
- `compose_resources(...)` — sums the hardware across stages.

### `estimate.py` — the top-level entry point
- `default_params()` — a representative design point (schema reference).
- `estimate(params)` — accepts a `DesignPoint` or a dict; returns a metrics dict:
  `latency_cycles`, `latency_us`, `throughput_infps`, `resources`, `util_pct`,
  `feasible`, and the per-stage cycle list.
- This is the single function every caller (CLI, sweep, DSE) uses.

### `sweep.py` — the DSE-facing evaluation engine
- `sweep(base, grid)` — enumerate the cartesian product of a parameter grid and
  score every point with `estimate()`.
- `pareto(results, x="latency_us", y_key="LUT")` — keep only the non-dominated
  (Pareto-optimal) feasible points.
- `print_table(results, title)` — formatted table for the terminal / demos.

### `calibrate.py` — trust the model against real synthesis
- `parse_csynth_report(path)` — best-effort parse of a Vitis `<top>_csynth.rpt`
  into actual LUT/FF/DSP/BRAM/URAM + latency.
- `compare(params, actual)` — predicted vs actual, with error % per metric.
- `fit_scale(samples)` — suggested multipliers (`actual/predicted`) for the cost
  constants so the estimator tracks reality.
- `samples_from_reports(pairs)` / `calibrate(samples)` — the driver.
- Functional now, but needs real csynth reports to act on — those come once the
  architecture parameters are implemented and synthesized.

### `cli.py` — the human command line
- `estimate` and `sweep` subcommands (see section 1). A thin wrapper over
  `estimate()`/`sweep()` for interactive use and demos. The DSE does not use this.

### `__init__.py` / `models/__init__.py`
- Package markers; the top one documents the module map.

---

## Honest caveats
- **Constants are un-calibrated estimates** — good for *ranking* points and telling
  the story, not yet ground-truth. `calibrate.py` fixes this once synthesis data exists.
- **Only the classification `infer` pipeline is modeled** (the MVP). More apps /
  primitives slot in as new `cost_*` functions + a `build_*` in `compose.py`.
- **`pipeline_mode=streamed` is approximate** (max-stage + fill), pending calibration.
