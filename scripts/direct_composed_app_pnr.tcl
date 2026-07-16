# =============================================================================
# direct_composed_app_pnr.tcl
# Direct Vivado P&R for one HLS-generated composed application RTL directory.
#
# Run HLS first:
#   $env:HDC_APP='sequence'
#   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
#
# Then P&R:
#   vivado -mode batch -source scripts/direct_composed_app_pnr.tcl
#
# Optional environment overrides:
#   HDC_APP        image | sequence | train       default image
#   HDC_PART       default xcu55c-fsvh2892-2L-e
#   HDC_CLOCK_NS   default 10
#   HDC_CONFIG_NAME optional suffix matching the HLS project suffix
# =============================================================================

set APP image
set PART xcu55c-fsvh2892-2L-e
set CLK  10

if {[info exists ::env(HDC_APP)] && $::env(HDC_APP) ne ""} {
    set APP $::env(HDC_APP)
}
if {[info exists ::env(HDC_PART)] && $::env(HDC_PART) ne ""} {
    set PART $::env(HDC_PART)
}
if {[info exists ::env(HDC_CLOCK_NS)] && $::env(HDC_CLOCK_NS) ne ""} {
    set CLK $::env(HDC_CLOCK_NS)
}
set CONFIG_NAME ""
if {[info exists ::env(HDC_CONFIG_NAME)] && $::env(HDC_CONFIG_NAME) ne ""} {
    set CONFIG_NAME $::env(HDC_CONFIG_NAME)
}

if {$APP eq "image"} {
    set PROJECT proj_app_image
    set TOP image_classification_top
} elseif {$APP eq "sequence"} {
    set PROJECT proj_app_sequence
    set TOP sequence_classification_top
} elseif {$APP eq "train"} {
    set PROJECT proj_app_train
    set TOP train_infer_top
} else {
    error "Unknown HDC_APP '$APP'. Use image, sequence, or train."
}

if {$CONFIG_NAME ne ""} {
    append PROJECT "_$CONFIG_NAME"
}

set RTL_DIR "$PROJECT/sol1/syn/verilog"
if {$CONFIG_NAME ne ""} {
    set OUT_DIR "pnr_${APP}_${CONFIG_NAME}"
} else {
    set OUT_DIR "pnr_${APP}"
}
set RPT_DIR "$OUT_DIR/reports"

file mkdir $OUT_DIR
file mkdir $RPT_DIR

puts "Direct P&R app: $APP"
puts "Config: $CONFIG_NAME"
puts "Top: $TOP"
puts "Target part: $PART"
puts "Clock: $CLK ns"
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

puts "Direct P&R complete."
puts "Reports: $RPT_DIR"
puts "Checkpoint: $OUT_DIR/${TOP}_routed.dcp"
