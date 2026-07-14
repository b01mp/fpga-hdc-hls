# =============================================================================
# run_application_hls.tcl
# C-simulate and C-synthesize the composed image-classification application top.
#
# Run from the repository root after sourcing the Vitis 2024.2 environment:
#   vitis-run --mode hls --tcl scripts/run_application_hls.tcl
#
# Optional overrides:
#   HDC_PART=xcu280-fsvh2892-2L-e HDC_CLOCK_NS=5 \
#     vitis-run --mode hls --tcl scripts/run_application_hls.tcl
# =============================================================================

set PART xcu280-fsvh2892-2L-e
set CLK  5

if {[info exists ::env(HDC_PART)] && $::env(HDC_PART) ne ""} {
    set PART $::env(HDC_PART)
}
if {[info exists ::env(HDC_CLOCK_NS)] && $::env(HDC_CLOCK_NS) ne ""} {
    set CLK $::env(HDC_CLOCK_NS)
}

puts "Application HLS target part: $PART"
puts "Application HLS target clock: $CLK ns"

open_project -reset proj_application
set_top image_classification_top

add_files "src/top_application.cpp" -cflags "-I./include"
add_files -tb "tb/tb_application.cpp" -cflags "-I./include"

open_solution -reset sol1
set_part $PART
create_clock -period $CLK -name default

puts "==================== application C simulation ===================="
csim_design

puts "==================== application C synthesis ====================="
csynth_design

puts "Application validation complete."
puts "Report: proj_application/sol1/syn/report/image_classification_top_csynth.rpt"

close_project
exit
