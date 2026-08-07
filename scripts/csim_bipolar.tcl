# =============================================================================
# csim_bipolar.tcl -- C-simulation of the bipolar draw fix (tb/tb_bipolar_fix.cpp).
#
#   Local (no VPN, no U280 licence needed):
#       & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/csim_bipolar.tcl
#
#   Server:
#       source /tools/Xilinx/Vitis/2023.1/settings64.sh
#       vitis_hls -f scripts/csim_bipolar.tcl
#
# FIXED: this script previously named `src/top_sim_dt_test.cpp` and
# `sim_dt_hamming_top`, neither of which exists in the repo -- so the bipolar
# test could never actually run. It now uses the real bipolar top from
# src/top_datatype.cpp.
#
# NOTE ON THE PART: C-simulation is device-independent, so this defaults to the
# WebPACK-licensed ZCU104 part and runs anywhere. Override with HDC_PART.
# =============================================================================
source scripts/target.tcl

if {![info exists ::env(HDC_PART)]} {
    set HDC_PART $HDC_PART_ZCU104
    puts "csim: using WebPACK part $HDC_PART (C-sim is device-independent)"
}

open_project -reset proj_bipolar
set_top bind_bipolar_top
add_files     src/top_datatype.cpp    -cflags "-I./include"
add_files -tb tb/tb_bipolar_fix.cpp   -cflags "-I./include"
open_solution -reset sol1
set_part $HDC_PART
create_clock -period $HDC_PERIOD -name default
csim_design
exit
