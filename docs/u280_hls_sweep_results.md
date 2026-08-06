# U280 HLS Target Sweep Results

## Summary

The U280 target sweep added in commit `8ddf251` was run successfully on all
eight configurations. The sweep compares buffered and dataflow-overlap
off-chip memory designs across `HBM_CP={1,2,4,8}`.

- Target part: `xcu280-fsvh2892-2L-e`
- Target clock: 3.333 ns (300 MHz)
- HBM interface width: 512 bits per channel
- Tool: Vitis HLS 2023.1
- Run date: 2026-08-03
- Result: 8/8 C synthesis runs completed
- Loop constraints: satisfied for all configurations

All configurations have an HLS estimated clock period of 2.433 ns, equivalent
to an estimated 411 MHz. This is a C-synthesis timing estimate, not post-route
timing closure.

## Results

| Design | CP | Latency (cycles) | Interval (cycles) | Estimated period | Estimated Fmax | Meets 300 MHz estimate? | LUT | FF | BRAM18K |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Baseline buffered | 1 | 50 | 51 | 2.433 ns | 411 MHz | Yes | 4,833 | 4,795 | 38 |
| Baseline buffered | 2 | 50 | 51 | 2.433 ns | 411 MHz | Yes | 9,369 | 9,471 | 76 |
| Baseline buffered | 4 | 50 | 51 | 2.433 ns | 411 MHz | Yes | 18,437 | 18,823 | 152 |
| Baseline buffered | 8 | 50 | 51 | 2.433 ns | 411 MHz | Yes | 36,573 | 37,527 | 304 |
| Dataflow overlap | 1 | 28 | 28 | 2.433 ns | 411 MHz | Yes | 5,331 | 5,898 | 45 |
| Dataflow overlap | 2 | 28 | 28 | 2.433 ns | 411 MHz | Yes | 10,442 | 11,629 | 90 |
| Dataflow overlap | 4 | 28 | 28 | 2.433 ns | 411 MHz | Yes | 20,656 | 23,091 | 180 |
| Dataflow overlap | 8 | 28 | 28 | 2.433 ns | 411 MHz | Yes | 41,084 | 46,015 | 360 |

The complete machine-readable table, including utilization percentages and
analytical bandwidth columns, is in
[`DSE/synth_results/u280_sweep.csv`](../DSE/synth_results/u280_sweep.csv).

## Main observations

The dataflow-overlap implementation reduces latency from 50 to 28 cycles and
the interval from 51 to 28 cycles at every tested CP value. Relative to the
buffered implementation, this costs additional LUTs, registers, and BRAM.

Resource use scales approximately linearly with CP. At CP=8, the larger
dataflow design uses 41,084 LUTs (3.15% of the U280), 46,015 registers (1.76%),
and 360 BRAM18K blocks (8.93%). The current CP range therefore fits comfortably
according to HLS estimates.

The `bw_GBps_at_300` values in the CSV are analytical interface ceilings:

```text
CP * 512 bits / 8 * 300 MHz
```

They range from 19.2 GB/s at CP=1 to 153.6 GB/s at CP=8. They are not measured
HBM bandwidth and do not account for platform, controller, arbitration, access
pattern, or protocol efficiency.

## Reproduction

```bash
source /tools/Xilinx/Vitis/2023.1/settings64.sh
vitis_hls -f scripts/sweep_target.tcl
HDC_TARGET_TAG=u280 python3 DSE/collect_target.py
```

Use `python3` on the validation server. Its default `python` executable is
Python 2.7 and cannot parse the f-strings in `DSE/collect_target.py`.

The sweep produces the following HLS projects:

```text
proj_u280_memoff_c1  proj_u280_df_c1
proj_u280_memoff_c2  proj_u280_df_c2
proj_u280_memoff_c4  proj_u280_df_c4
proj_u280_memoff_c8  proj_u280_df_c8
```

## Scope and next validation step

This run executes `csynth_design` only. It does not perform Vivado synthesis,
place and route, U280 platform linking, bitstream generation, or board-level
HBM measurement. Consequently, `meets_300MHz=yes` means that the HLS estimated
period is no greater than the 3.333 ns target; it is not a post-route timing
result.

To make a complete implementation claim, run Vivado place and route at a
3.333 ns constraint and report post-route WNS/TNS. The most useful first
candidates are the CP=8 dataflow design for maximum tested parallelism and the
CP=8 buffered design as its direct baseline. CP=1 can be included as a scaling
reference.

The current top-level interfaces stop at eight HBM channels. Testing CP=16 or
CP=32 requires extending the channel fan-out in the source before changing the
sweep grid.
