# =============================================================================
# csim_pow2.tcl -- C-simulation of the pow2 datatype family (tb/tb_pow2.cpp).
#
#   Local (no VPN, no U280 licence needed):
#       & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/csim_pow2.tcl
#
#   Server:
#       source /tools/Xilinx/Vitis/2023.1/settings64.sh
#       vitis_hls -f scripts/csim_pow2.tcl
#
# NOTE ON THE PART: C-simulation compiles and runs plain C++ -- the result is
# identical on every device. This script therefore defaults to the WebPACK-
# licensed ZCU104 part so the tests run anywhere, including a laptop with no
# U280 licence. Synthesis numbers come from scripts/synth_datatype.tcl, which
# targets the U280. Override here with HDC_PART if you ever need to.
#
# The testbench exercises the library templates directly; `set_top` only needs
# to name a real synthesizable function so the project is well-formed.
# =============================================================================
source scripts/target.tcl

if {![info exists ::env(HDC_PART)]} {
    set HDC_PART $HDC_PART_ZCU104
    puts "csim: using WebPACK part $HDC_PART (C-sim is device-independent)"
}

open_project -reset proj_pow2
set_top bind_pow2_top
add_files     src/top_datatype.cpp -cflags "-I./include"
add_files -tb tb/tb_pow2.cpp       -cflags "-I./include"
open_solution -reset sol1
set_part $HDC_PART
create_clock -period $HDC_PERIOD -name default
csim_design
exit
