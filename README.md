# FPGA-HDC-Library (HLS)

Reusable, composable **FPGA primitive library for Hyperdimensional Computing** —
"TorchHD with an FPGA backend." Every HDC application is composed from
datatype-parametric, independently-synthesizable **Vitis HLS** function templates.

- Target: edge FPGA (Xilinx UltraScale+, e.g. ZCU104 / ZU7EV).
- Toolchain: Vitis 2026.1 (`C:\AMDDesignTools\2026.1`).
- Function set: the ~21 functions defined in
  `C:\USC\FPGA-HDC-Library\Scoping-out\notes\function_definition.md`.
- Reference baseline (working app that composes these): `C:\USC\emg_hdc`.

## Current scope (this stage)

Wire the **application parameters** of each function as inputs — as C++ **template
parameters** (datatype `typename`s + size `int`s) and mode **function arguments** —
and verify each with a **C-sim testbench**. Same style as `emg_hdc`, but the
datatypes are lifted from config typedefs to template arguments so no primitive
carries an app-specific constant.

**Architecture parameters (HLS pragmas: PIPELINE / UNROLL / ARRAY_PARTITION /
bind_storage / dataflow) are deliberately NOT added yet** — that is the next
stage, after these app-param templates are C-sim verified.

## Layout

```
include/
  common/hdc_types.hpp        shared element aliases + mode enums (app-param modes)
  generation/                 random_hv, gen_levels, rematerialize
  encoding/                   quantize, bind, permute, scale, gemm, matvec, transpose, flatten
  aggregation/                bundle, threshold, normalize, update, cast
  search/                     similarity_search
  memory/                     gather, place
  control/                    initialize_centroids, convergence_check
src/                          concrete top wrappers (set_top / synth entry per category)
tb/                           per-category C-sim testbenches
scripts/run_hls.tcl          C-sim runner (one project per category)
```

## Function status

| Status | Functions |
|---|---|
| **Implemented + C-sim tested** | quantize, bind, bundle, threshold, similarity_search |
| Implemented, C-sim pending | random_hv, gen_levels(linear), rematerialize, permute, scale, gemm, matvec, transpose, flatten, cast, gather, place |
| Skeleton (baseline body, review) | normalize, update(ADD only), initialize_centroids, convergence_check |

The 5 tested functions are the ones already proven in the `emg_hdc` baseline,
ported here as the reference pattern for the rest.

## Run C-sim

Vitis 2026.1 has **no standalone `vitis_hls.exe`** — drive HLS via `vitis-run`:

```powershell
cd C:/USC/fpga-hdc-hls
& "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/run_hls.tcl
```

This builds one project per category (`proj_encoding`, `proj_aggregation`,
`proj_search`), runs C-simulation, and each testbench prints `ALL PASS` /
`FAILURE(S)` and returns non-zero on mismatch. `csynth_design` / `cosim_design`
are commented in the TCL — enable once C-sim is green.

## Next steps

1. C-sim the 3 category testbenches (above) and confirm `ALL PASS`.
2. Add asserted testbench cases for the "C-sim pending" functions, category by category.
3. Design-review the skeleton functions (normalize output semantics; update
   ADD_SUB/PERCEPTRON signature; gen_levels non-linear modes).
4. Only then: architecture parameters (HLS pragmas) + real-device synthesis.

## U280 target sweep

The 300 MHz U280 C-synthesis sweep for the buffered and dataflow-overlap
off-chip designs is documented in
[`docs/u280_hls_sweep_results.md`](docs/u280_hls_sweep_results.md). The raw
summary is available in `DSE/synth_results/u280_sweep.csv`.
