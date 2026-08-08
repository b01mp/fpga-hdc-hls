# =============================================================================
# csim_precision.tcl -- correctness gate for the per-stage precision study.
#
#     source /tools/Xilinx/Vitis/2023.1/settings64.sh
#     cd ~/fpga-hdc-hls
#     vitis_hls -f scripts/csim_precision.tcl 2>&1 | tail -40
#
# RUN THIS BEFORE scripts/sweep_precision.tcl. It takes seconds; the sweep takes
# an hour. tb/tb_precision.cpp asserts three things:
#
#   1. the derived widths give predictions IDENTICAL to the old ap_int<32>
#   2. one bit narrower mispredicts at the extreme (distance == D)
#   3. the majority-vote overflow regression stays fixed
#
# A sweep of numerically wrong hardware is worth nothing, which is the lesson
# from the CP restructuring -- that went to synthesis before simulation and only
# got verified afterwards.
# =============================================================================

source scripts/target.tcl
hdc_target_banner "precision csim"

open_project -reset proj_csim_precision
set_top image_classification_top
add_files     src/top_application.cpp -cflags "-I./include"
add_files -tb tb/tb_precision.cpp     -cflags "-I./include"
open_solution -reset sol1
hdc_apply_target
csim_design
exit
