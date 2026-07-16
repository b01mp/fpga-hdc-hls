# U280 Validation Plan

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

## Saved DSE configurations

The latency-oriented DSE configurations for the composed applications are saved
in:

- `DSE/synth_results/composed_app_latency_configs.csv`
- `DSE/synth_results/composed_app_latency_configs.json`

The saved configurations are composed from existing primitive DSE measurements.
They should be treated as DSE-predicted candidates until each composed top is
confirmed by HLS synthesis and P&R.

## Immediate next steps on a licensed machine

1. Clone this branch on a machine with a valid Vivado license for
   `xcvu37p-fsvh2892-2L-e`.
2. Run HLS synthesis for the selected composed application candidates:

   ```powershell
   cd D:\Project\Vitis\fpga-hdc-hls

   $env:HDC_PART='xcvu37p-fsvh2892-2L-e'
   $env:HDC_CLOCK_NS='10'
   $env:HDC_APP='sequence'
   $env:HDC_SEQ_DP='8'
   $env:HDC_SEQ_CP='2'
   & 'D:\AMD\2025.2\Vitis\bin\vitis-run.bat' --mode hls --tcl scripts/run_composed_app_hls.tcl

   $env:HDC_APP='train'
   $env:HDC_TRAIN_DP='8'
   $env:HDC_TRAIN_CP='2'
   & 'D:\AMD\2025.2\Vitis\bin\vitis-run.bat' --mode hls --tcl scripts/run_composed_app_hls.tcl
   ```

3. Run direct Vivado P&R for each synthesized composed top:

   ```powershell
   $env:HDC_PART='xcvu37p-fsvh2892-2L-e'
   $env:HDC_CLOCK_NS='10'

   $env:HDC_APP='sequence'
   & 'D:\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source scripts/direct_composed_app_pnr.tcl

   $env:HDC_APP='train'
   & 'D:\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source scripts/direct_composed_app_pnr.tcl
   ```

4. Collect the generated timing, utilization, and route-status reports under
   `pnr_sequence/reports` and `pnr_train/reports`.

## Success criteria

- HLS C-simulation passes.
- HLS synthesis generates RTL for the selected composition.
- Vivado implementation completes for `xcvu37p-fsvh2892-2L-e`.
- Route status reports show no routing errors.
- Timing summary shows non-negative WNS at the target clock, or clearly reports
  the margin if the target needs adjustment.
- Utilization is reasonable for the U280 device and does not exceed available
  LUT, FF, BRAM, URAM, or DSP resources.

## Notes

This plan verifies that the composed HDC kernels can be implemented for the U280
underlying FPGA part. It does not require running on the physical U280 board.
Full Vitis platform linking with a U280 `.xpfm` is only needed if the goal
changes from implementation validation to deployable accelerator packaging.
