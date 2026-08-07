# =============================================================================
# direct_application_pnr.tcl
# Direct Vivado P&R smoke test for HLS-generated RTL.
#
# This bypasses Vivado generated run wrappers, which are slow and can trip over
# locked-down Windows WMI/WSH permissions. Run this after HLS csynth has produced
# proj_application_fast_impl/sol1/syn/verilog/*.v.
#
# Run from the repository root:
#   vivado -mode batch -source scripts/direct_application_pnr.tcl
#
# Optional environment overrides:
#   HDC_PART       default xcu55c-fsvh2892-2L-e
#   HDC_CLOCK_NS   default 10
# =============================================================================

set PART xcu55c-fsvh2892-2L-e
set CLK  10

if {[info exists ::env(HDC_PART)] && $::env(HDC_PART) ne ""} {
    set PART $::env(HDC_PART)
}
if {[info exists ::env(HDC_CLOCK_NS)] && $::env(HDC_CLOCK_NS) ne ""} {
    set CLK $::env(HDC_CLOCK_NS)
}

set TOP image_classification_top
set RTL_DIR "proj_application_fast_impl/sol1/syn/verilog"
set OUT_DIR "pnr_fast"
set RPT_DIR "$OUT_DIR/reports"

file mkdir $OUT_DIR
file mkdir $RPT_DIR

puts "Direct P&R target part: $PART"
puts "Direct P&R target clock: $CLK ns"
puts "Reading RTL from: $RTL_DIR"

read_verilog [glob "$RTL_DIR/*.v"]
synth_design -top $TOP -part $PART -mode out_of_context

create_clock -period $CLK -name ap_clk [get_ports ap_clk]

opt_design
place_design -directive Quick
route_design -directive Quick

report_utilization -file "$RPT_DIR/${TOP}_utilization.rpt"
report_timing_summary -file "$RPT_DIR/${TOP}_timing_summary.rpt"
report_route_status -file "$RPT_DIR/${TOP}_route_status.rpt"
write_checkpoint -force "$OUT_DIR/${TOP}_routed.dcp"

puts "Direct P&R smoke test complete."
puts "Reports: $RPT_DIR"
puts "Checkpoint: $OUT_DIR/${TOP}_routed.dcp"
