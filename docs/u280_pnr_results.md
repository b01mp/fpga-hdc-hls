# U280 Place-and-Route Validation Report

## Executive summary

The three paper applications completed the full direct Vivado implementation
workflow on the AMD/Xilinx Alveo U280 part:

```text
HLS-generated RTL -> synthesis -> optimization -> placement -> routing
                  -> post-route timing/utilization/route reports -> routed DCP
```

The implementation target was **250 MHz (4.000 ns)**, which is within the
requested 250--300 MHz range. Time-series classification and genome-sequence
search meet this target. Image classification is fully placed and routed, but
does **not** meet 250 MHz and must not be reported as timing-clean at that
frequency.

| Application | Parallelism | Target | Post-route WNS | TNS | Hold WHS | Timing met? | Fully routed? |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Image classification | DP=256, CP=10 | 250 MHz (4.000 ns) | **-2.823 ns** | -58.886 ns | +0.037 ns | **No** | Yes, 6107/6107 nets |
| Time-series classification | DP=8, CP=2 | 250 MHz (4.000 ns) | **+1.155 ns** | 0.000 ns | +0.041 ns | **Yes** | Yes, 729/729 nets |
| Genome-sequence search | DP=8, CP=2 | 250 MHz (4.000 ns) | **+1.332 ns** | 0.000 ns | +0.039 ns | **Yes** | Yes, 730/730 nets |

For context, the routed critical-path delay can be estimated as
`target period - WNS`. This gives approximately 6.823 ns (146.6 MHz) for
image, 2.845 ns (351.5 MHz) for time series, and 2.668 ns (374.8 MHz) for
genome. These values describe the current out-of-context implementation and
are not substitutes for running implementation at a new clock constraint.

## Test environment

- Git branch: `haoyang_DSE`
- Source commit before this report: `4a78b69`
- Tools: Vitis HLS and Vivado 2023.1
- FPGA part: `xcu280-fsvh2892-2L-e`
- Flow: direct Vivado out-of-context (OOC) implementation
- Implementation directives: `place_design -directive Quick` and
  `route_design -directive Quick`
- Report date: 2026-07-16

The U280 synthesis and implementation licenses were successfully checked out.
All three designs passed implementation DRC with no errors and produced routed
checkpoints.

## Results

### Image classification

- Configuration: best latency, `APP_DP=256`, `APP_CP=10`
- HLS latency: 23 cycles (0.230 us at the original 10 ns HLS schedule)
- 250 MHz post-route WNS: **-2.823 ns**
- 250 MHz post-route TNS: **-58.886 ns**, 57 failing endpoints
- Hold WHS: +0.037 ns
- Routing: 6107 of 6107 routable nets fully routed; 0 routing errors
- Resources: 4647 LUTs, 1378 registers, 0 BRAM tiles, 0 URAM, 0 DSPs
- Verdict: placement and routing succeed, but **250 MHz timing fails**.

The image design is dominated by a long combinational path in the aggressively
parallel DP=256 mapping. A timing-clean 250--300 MHz result requires additional
pipeline stages, a less aggressive parallel mapping, or HLS resynthesis with a
high-frequency schedule followed by another P&R run.

### Time-series classification

- Configuration: best latency, `TS_DP=8`, `TS_CP=2`
- HLS latency: 992--994 cycles (9.920--9.940 us at the original 10 ns schedule)
- 250 MHz post-route WNS: **+1.155 ns**
- 250 MHz post-route TNS: 0.000 ns, 0 failing endpoints
- Hold WHS: +0.041 ns
- Routing: 729 of 729 routable nets fully routed; 0 routing errors
- Resources: 491 LUTs, 286 registers, 0 BRAM tiles, 0 URAM, 0 DSPs
- Verdict: **250 MHz timing met after complete place and route**.

### Genome-sequence search

- Configuration: best latency, `GEN_DP=8`, `GEN_CP=2`
- HLS latency: 811--813 cycles (8.110--8.130 us at the original 10 ns schedule)
- 250 MHz post-route WNS: **+1.332 ns**
- 250 MHz post-route TNS: 0.000 ns, 0 failing endpoints
- Hold WHS: +0.039 ns
- Routing: 730 of 730 routable nets fully routed; 0 routing errors
- Resources: 479 LUTs, 262 registers, 4 BRAM tiles, 0 URAM, 0 DSPs
- Verdict: **250 MHz timing met after complete place and route**.

## Reproducible implementation workflow

First generate the RTL with the application-specific HLS command documented in
[`u280_validation_plan.md`](u280_validation_plan.md). Then run the complete
250 MHz implementation for each application:

```bash
source /tools/Xilinx/Vitis/2023.1/settings64.sh
export HDC_PART=xcu280-fsvh2892-2L-e
export HDC_CLOCK_NS=4.0
export HDC_CONFIG_NAME=best_latency
export HDC_PNR_LABEL=250mhz

export HDC_APP=image
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl

export HDC_APP=time_series
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl

export HDC_APP=genome
vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
```

`HDC_PNR_LABEL` keeps results from different clock targets in separate output
directories. Each run executes `synth_design`, `opt_design`, `place_design`, and
`route_design`, then emits utilization, timing summary, route status, and a
routed checkpoint.

## Interpretation and limitations

- A routed design is not automatically timing-clean. The image design proves
  this distinction: it has zero routing errors but negative setup WNS.
- The positive WNS values for time series and genome formally establish the
  250 MHz target for this OOC flow. They do not formally establish 300 MHz;
  a separate 3.333 ns run is required to claim 300 MHz.
- The current HLS RTL was scheduled with a 10 ns HLS clock. The 4 ns Vivado run
  validates physical implementation of that generated RTL at 250 MHz; future
  optimization should use the same high-frequency constraint in both HLS and
  Vivado so HLS can introduce an appropriate schedule/pipeline structure.
- Vivado warns that `HD.CLK_SRC` is not set for the OOC `ap_clk` port. The
  reported timing is therefore kernel-level OOC timing, not final timing after
  integration with the U280 platform shell.
- A deployable accelerator requires Vitis platform linking and final system
  timing closure. That step is outside this mapping-focused OOC validation.

## Baseline comparison

The earlier 100 MHz (10 ns) implementation met timing for all three mappings:

| Application | 100 MHz WNS | Timing met? |
| --- | ---: | --- |
| Image classification | +3.177 ns | Yes |
| Time-series classification | +7.155 ns | Yes |
| Genome-sequence search | +7.332 ns | Yes |

The unchanged critical-path margins between the 10 ns and 4 ns runs are
consistent with the 250 MHz results above. The 250 MHz runs, rather than this
baseline, are the evidence used for the requested frequency claim.
