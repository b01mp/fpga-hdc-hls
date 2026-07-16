# U280 Validation Requirements and Run Plan

## Current status

- The repository has an application-level image classification composition:
  `gather -> gather -> bind -> bundle -> threshold -> similarity_search`.
- Two additional composed examples have been added:
  - `sequence_classification_top`: `gather -> permute -> bundle -> threshold -> similarity_search`
  - `train_infer_top`: training prototype build plus inference search
- C-simulation has passed for the new `sequence` and `train` examples.
- Local HLS synthesis has been validated against the U280 underlying FPGA part
  `xcvu37p-fsvh2892-2L-e`.
- Local Vivado P&R for the U280 underlying part is currently blocked by the
  missing `xcvu37p` synthesis/implementation license.
- The same four composed application configurations have been locally verified
  with:
  - U280-target HLS synthesis
  - local out-of-context quick P&R on `xcu55c-fsvh2892-2L-e`
- The local P&R sanity results are saved in:
  - `DSE/synth_results/composed_app_actual_reports.csv`

## Server requirement

The next required validation step is to rerun direct Vivado P&R on a server that
has a valid U280 synthesis/implementation license.

The server environment should satisfy the following:

- Vivado/Vitis can recognize the U280 part:
  `xcu280-fsvh2892-2L-e`
- Vivado license checkout succeeds for synthesis:
  `Got license for feature 'Synthesis' and/or device 'xcu280'`
- Vivado license checkout succeeds for implementation:
  `Got license for feature 'Implementation' and/or device 'xcu280'`
- Recommended tool version: Vivado/Vitis 2023.1, or another version on the
  server that can recognize `xcu280-fsvh2892-2L-e`.
- If using the U280 platform flow later, the server should also have a matching
  U280 platform installed, for example:
  `xilinx_u280_gen3x16_xdma_1_202211_1`

For the current goal, the `.xpfm` platform is not required. The goal is direct
out-of-context implementation validation for the U280 FPGA part, not packaging
a deployable Vitis accelerator.

## Saved DSE configurations

The latency-oriented DSE configurations for the composed applications are saved
in:

- `DSE/synth_results/composed_app_latency_configs.csv`
- `DSE/synth_results/composed_app_latency_configs.json`

The saved configurations are composed from existing primitive DSE measurements.
They should be treated as DSE-predicted candidates until each composed top is
confirmed by HLS synthesis and P&R.

## Immediate next steps on the licensed U280 server

1. Clone this branch:

   ```bash
   git clone -b haoyang_DSE https://github.com/b01mp/fpga-hdc-hls.git
   cd fpga-hdc-hls
   ```

2. Source the server tool environment. Example:

   ```bash
   source /tools/Xilinx/Vitis/2023.1/settings64.sh
   ```

3. Confirm that Vivado can see the U280 part:

   ```bash
   vivado -mode batch -nolog -nojournal -notrace \
     -source <(echo 'create_project -in_memory -part xcu280-fsvh2892-2L-e; close_project')
   ```

4. Run HLS synthesis and direct P&R for the four DSE-selected configurations.

   Sequence, best latency:

   ```bash
   export HDC_PART=xcu280-fsvh2892-2L-e
   export HDC_CLOCK_NS=10
   export HDC_APP=sequence
   export HDC_CONFIG_NAME=best_latency
   export HDC_SEQ_DP=8
   export HDC_SEQ_CP=2
   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
   vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
   ```

   Sequence, second-best latency:

   ```bash
   export HDC_PART=xcu280-fsvh2892-2L-e
   export HDC_CLOCK_NS=10
   export HDC_APP=sequence
   export HDC_CONFIG_NAME=second_best_latency
   export HDC_SEQ_DP=4
   export HDC_SEQ_CP=1
   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
   vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
   ```

   Train, best latency:

   ```bash
   export HDC_PART=xcu280-fsvh2892-2L-e
   export HDC_CLOCK_NS=10
   export HDC_APP=train
   export HDC_CONFIG_NAME=best_latency
   export HDC_TRAIN_DP=8
   export HDC_TRAIN_CP=2
   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
   vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
   ```

   Train, second-best latency:

   ```bash
   export HDC_PART=xcu280-fsvh2892-2L-e
   export HDC_CLOCK_NS=10
   export HDC_APP=train
   export HDC_CONFIG_NAME=second_best_latency
   export HDC_TRAIN_DP=4
   export HDC_TRAIN_CP=1
   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
   vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
   ```

5. Collect the generated reports:

   - `proj_app_sequence_best_latency/sol1/syn/report/`
   - `proj_app_sequence_second_best_latency/sol1/syn/report/`
   - `proj_app_train_best_latency/sol1/syn/report/`
   - `proj_app_train_second_best_latency/sol1/syn/report/`
   - `pnr_sequence_best_latency/reports/`
   - `pnr_sequence_second_best_latency/reports/`
   - `pnr_train_best_latency/reports/`
   - `pnr_train_second_best_latency/reports/`

## Success criteria

- HLS C-simulation passes.
- HLS synthesis generates RTL for the selected composition.
- Vivado implementation completes for `xcu280-fsvh2892-2L-e`.
- Route status reports show no routing errors.
- Timing summary shows non-negative WNS at the target clock, or clearly reports
  the margin if the target needs adjustment.
- Utilization is reasonable for the U280 device and does not exceed available
  LUT, FF, BRAM, URAM, or DSP resources.

## Notes

This plan verifies that the composed HDC kernels can be implemented for the U280
FPGA part. It does not require running on the physical U280 board.

Full Vitis platform linking with a U280 `.xpfm` is only needed if the goal
changes from implementation validation to deployable accelerator packaging.

The local Windows run already showed that the designs pass C-simulation, produce
U280-target HLS RTL, and can be placed/routed on a locally licensed Alveo-class
device. The server run is needed to replace the local P&R sanity check with the
actual U280 part implementation report.
