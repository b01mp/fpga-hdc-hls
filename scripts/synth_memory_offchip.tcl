# =============================================================================
# synth_memory_offchip.tcl - synthesize the OFF-CHIP (AXI master) memory wrapper.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/synth_memory_offchip.tcl
#
# The codebook lives in external DDR/HBM; only a one-row buffer is on-chip. Expect
# BRAM to drop to ~1 (the row buffer) and an m_axi interface to appear. Part =
# xc7z020 (Zynq has DDR via the PS, so the AXI master synthesizes on the free tier).
# Report: proj_mem_offchip/sol1/syn/report/memory_offchip_top_csynth.rpt
# =============================================================================
set PART xc7z020clg484-1

open_project -reset proj_mem_offchip
set_top memory_offchip_top
add_files src/top_memory_offchip.cpp -cflags "-I./include"
open_solution -reset sol1
set_part $PART
create_clock -period 10 -name default
csynth_design
close_project
exit
