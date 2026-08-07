# U280 Validation Requirements and Run Plan

## Current status

The completed 250 MHz place-and-route measurements and timing verdicts are
reported in [`u280_pnr_results.md`](u280_pnr_results.md). The machine-readable
summary is in `DSE/synth_results/u280_pnr_results.csv`.

- The paper-defined application set is:
  - `image_classification_top`
  - `time_series_classification_top`
  - `genome_sequence_search_top`
- The three tops use a shared staged HDC composition:
  - image classification:
    `gather(feature) -> gather(value) -> bind -> bundle -> threshold -> similarity_search`
  - time-series classification:
    `gather(sample-level) -> permute(position) -> bundle -> threshold -> similarity_search`
  - genome-sequence search:
    `gather(symbol/k-mer) -> permute(position) -> bundle -> threshold -> similarity_search`
- The old non-paper examples and results have been removed:
  - `sequence_classification_top`
  - `train_infer_top`
  - `DSE/synth_results/composed_app_actual_reports.csv`
  - `DSE/synth_results/composed_app_latency_configs.*`
- The corrected paper-application candidate configurations are saved in:
  - `DSE/synth_results/paper_app_latency_configs.csv`
  - `DSE/synth_results/paper_app_latency_configs.json`
- Local HLS smoke synthesis for the three corrected paper applications passed on
  `xcu55c-fsvh2892-2L-e`; the summary is saved in:
  - `DSE/synth_results/paper_app_local_hls_reports.csv`

## Validation goal

The current goal is to verify that each paper application can be synthesized and
implemented for the U280 FPGA part. This is direct Vivado out-of-context
implementation validation for `xcu280-fsvh2892-2L-e`; it does not require
running on the physical U280 board.

Full Vitis platform linking with a U280 `.xpfm` is only needed if the goal
changes from implementation validation to deployable accelerator packaging.

## Server requirement

The licensed server should satisfy the following:

- Vivado/Vitis can recognize the U280 part:
  `xcu280-fsvh2892-2L-e`
- Vivado license checkout succeeds for synthesis:
  `Got license for feature 'Synthesis' and/or device 'xcu280'`
- Vivado license checkout succeeds for implementation:
  `Got license for feature 'Implementation' and/or device 'xcu280'`
- Recommended tool version: Vivado/Vitis 2023.1, or another server version that
  recognizes `xcu280-fsvh2892-2L-e`.

## Run commands

Clone this branch on the server:

```bash
git clone -b haoyang_DSE https://github.com/b01mp/fpga-hdc-hls.git
cd fpga-hdc-hls
```

Source the tool environment:

```bash
source /tools/Xilinx/Vitis/2023.1/settings64.sh
```

Use the same target settings for all runs:

```bash
export HDC_PART=xcu280-fsvh2892-2L-e
export HDC_CLOCK_NS=10
```

Image classification, best-latency candidate:

```bash
export HDC_APP=image
export HDC_CONFIG_NAME=best_latency
export HDC_APP_DP=256
export HDC_APP_CP=10
vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
```

Time-series classification, best-latency candidate:

```bash
export HDC_APP=time_series
export HDC_CONFIG_NAME=best_latency
export HDC_TS_DP=8
export HDC_TS_CP=2
vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
```

Genome-sequence search, best-latency candidate:

```bash
export HDC_APP=genome
export HDC_CONFIG_NAME=best_latency
export HDC_GEN_DP=8
export HDC_GEN_CP=2
vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
```

Second-best candidates are also recorded in
`DSE/synth_results/paper_app_latency_configs.*` and can be run by changing the
parallelism variables and `HDC_CONFIG_NAME=second_best_latency`.

## Reports to collect

- HLS reports:
  - `proj_app_image_best_latency/sol1/syn/report/`
  - `proj_app_time_series_best_latency/sol1/syn/report/`
  - `proj_app_genome_best_latency/sol1/syn/report/`
- P&R reports:
  - `pnr_image_best_latency/reports/`
  - `pnr_time_series_best_latency/reports/`
  - `pnr_genome_best_latency/reports/`

## Success criteria

- HLS C-simulation passes.
- HLS synthesis generates RTL for each selected composition.
- Vivado implementation completes for `xcu280-fsvh2892-2L-e`.
- Route status reports show no routing errors.
- Timing summary shows non-negative WNS at the target clock, or clearly reports
  the margin if the target needs adjustment.
- Utilization is reasonable for the U280 device and does not exceed available
  LUT, FF, BRAM, URAM, or DSP resources.
