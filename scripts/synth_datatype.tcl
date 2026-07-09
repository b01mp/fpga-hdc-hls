# =============================================================================
# synth_datatype.tcl - datatype-sweep C-synthesis (Novelty 1 demonstration).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/synth_datatype.tcl
#
# Synthesizes each of the 9 datatype tops in src/top_datatype.cpp as its own
# project (bind/threshold/similarity x binary/bipolar/fixed), all at DP=8 so the
# only variable is the datatype. Part = xc7z020. Reports:
#   proj_dt_<top>/sol1/syn/report/<top>_csynth.rpt
# =============================================================================
set PART xc7z020clg484-1
set CLK  10

proc synth_dt {top PART CLK} {
    puts "=================== synth: $top ==================="
    open_project -reset "proj_dt_$top"
    set_top $top
    add_files "src/top_datatype.cpp" -cflags "-I./include"
    open_solution -reset "sol1"
    set_part $PART
    create_clock -period $CLK -name default
    csynth_design
    close_project
}

foreach t {bind_binary_top bind_bipolar_top bind_fixed_top \
           threshold_binary_top threshold_bipolar_top threshold_fixed_top \
           sim_binary_top sim_bipolar_top sim_fixed_top} {
    synth_dt $t $PART $CLK
}

puts "Datatype sweep done. Reports: proj_dt_*/sol1/syn/report/*_csynth.rpt"
exit
