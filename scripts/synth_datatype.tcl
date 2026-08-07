# =============================================================================
# synth_datatype.tcl - datatype-sweep C-synthesis (Novelty 1 demonstration).
#
#   Licensed server (yangzi), U280 default:
#       source /tools/Xilinx/Vitis/2023.1/settings64.sh
#       vitis_hls -f scripts/synth_datatype.tcl
#
#   Local WebPACK smoke test only (NOT for paper numbers):
#       $env:HDC_PART="xczu7ev-ffvc1156-2-e"; $env:HDC_TAG="zcu104"
#       & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/synth_datatype.tcl
#
# Synthesizes each of the 15 datatype tops in src/top_datatype.cpp as its own
# project (bind/threshold/similarity x binary/bipolar/fixed/integer/pow2), all
# at D=256, DP=8, CP=2, so the ONLY variable is the datatype. Accumulator and
# score widths follow the element type by design -- see the header comment in
# src/top_datatype.cpp for why that is correct rather than a confound.
#
# Reports: proj_dt_<top>/sol1/syn/report/<top>_csynth.rpt
#
# TARGET: taken from scripts/target.tcl (U280 @ 300 MHz by default). This sweep
# previously hardcoded xc7z020 @ 100 MHz, which is neither the paper's part nor
# its clock -- and the resulting resource numbers were not comparable with the
# system-level results. Override with HDC_PART / HDC_PERIOD / HDC_TAG.
# =============================================================================
source scripts/target.tcl
hdc_target_banner "datatype sweep"

proc synth_dt {top part period} {
    puts "=================== synth: $top ==================="
    if {[catch {
        open_project -reset "proj_dt_$top"
        set_top $top
        add_files "src/top_datatype.cpp" -cflags "-I./include"
        open_solution -reset "sol1"
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $top: $err" }
}

foreach t {bind_binary_top bind_bipolar_top bind_fixed_top bind_integer_top bind_pow2_top \
           threshold_binary_top threshold_bipolar_top threshold_fixed_top \
           threshold_integer_top threshold_pow2_top \
           sim_binary_top sim_bipolar_top sim_fixed_top sim_integer_top sim_pow2_top} {
    synth_dt $t $HDC_PART $HDC_PERIOD
}

puts ""
puts "Datatype sweep done on $HDC_PART @ $HDC_PERIOD ns."
puts "Reports: proj_dt_*/sol1/syn/report/*_csynth.rpt"
exit
