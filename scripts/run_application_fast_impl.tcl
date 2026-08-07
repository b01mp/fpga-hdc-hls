# =============================================================================
# run_application_fast_impl.tcl
# Fast implementation smoke test for the composed image-classification HLS top.
#
# This script is intentionally separate from run_application_hls.tcl:
# - skips C simulation by default because correctness was already checked there;
# - uses a relaxed clock by default to avoid spending time chasing timing;
# - runs HLS C synthesis and then asks HLS/Vivado to run implementation.
#
# Run from the repository root:
#   vitis-run --mode hls --tcl scripts/run_application_fast_impl.tcl
#
# CMD override example:
#   set HDC_PART=xcu55c-fsvh2892-2L-e
#   set HDC_CLOCK_NS=10
#   vitis-run --mode hls --tcl scripts\run_application_fast_impl.tcl
# =============================================================================

set PART xcu55c-fsvh2892-2L-e
set CLK  10

if {[info exists ::env(HDC_PART)] && $::env(HDC_PART) ne ""} {
    set PART $::env(HDC_PART)
}
if {[info exists ::env(HDC_CLOCK_NS)] && $::env(HDC_CLOCK_NS) ne ""} {
    set CLK $::env(HDC_CLOCK_NS)
}

set CFLAGS "-I./include"
if {[info exists ::env(HDC_APP_DP)] && $::env(HDC_APP_DP) ne ""} {
    append CFLAGS " -DAPP_DP=$::env(HDC_APP_DP)"
}
if {[info exists ::env(HDC_APP_CP)] && $::env(HDC_APP_CP) ne ""} {
    append CFLAGS " -DAPP_CP=$::env(HDC_APP_CP)"
}

set SKIP_EXPORT 0
if {[info exists ::env(HDC_SKIP_EXPORT)] && $::env(HDC_SKIP_EXPORT) ne ""} {
    set SKIP_EXPORT $::env(HDC_SKIP_EXPORT)
}

puts "Fast implementation target part: $PART"
puts "Fast implementation target clock: $CLK ns"
puts "Fast implementation CFLAGS: $CFLAGS"

open_project -reset proj_application_fast_impl
set_top image_classification_top

add_files "src/top_application.cpp" -cflags $CFLAGS
add_files -tb "tb/tb_application.cpp" -cflags $CFLAGS

open_solution -reset sol1
set_part $PART
create_clock -period $CLK -name default

puts "==================== application C synthesis ====================="
csynth_design

if {$SKIP_EXPORT} {
    puts "Skipping HLS export because HDC_SKIP_EXPORT=$SKIP_EXPORT"
} else {
    puts "==================== export + implementation smoke test ===================="
    export_design -rtl verilog -format ip_catalog -flow impl
}

puts "Fast implementation validation complete."
puts "HLS report: proj_application_fast_impl/sol1/syn/report/image_classification_top_csynth.rpt"
puts "Export directory: proj_application_fast_impl/sol1/impl"

close_project
exit
