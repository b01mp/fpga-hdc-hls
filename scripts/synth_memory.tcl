# =============================================================================
# synth_memory.tcl - synthesize the memory-tier wrapper to see where the
# codebook lands (BRAM vs URAM).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/synth_memory.tcl
#
# PART: xc7z020 has NO URAM -> use it for the BRAM run. For the URAM run, set
# USE_URAM=1 in src/top_memory_tier.cpp AND change PART below to xczu7ev-ffvc1156-2-e
# (UltraScale+, has URAM; may need a higher license tier).
#
# Report: proj_mem_tier/sol1/syn/report/memory_tier_top_csynth.rpt
#         look at the Utilization 'Total' row -> BRAM_18K vs URAM count.
# =============================================================================
set PART xc7z020clg484-1
# set PART xczu7ev-ffvc1156-2-e     ;# uncomment for the URAM run

open_project -reset proj_mem_tier
set_top memory_tier_top
add_files src/top_memory_tier.cpp -cflags "-I./include"
open_solution -reset sol1
set_part $PART
create_clock -period 10 -name default
csynth_design
close_project
exit
