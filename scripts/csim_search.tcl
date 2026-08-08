# =============================================================================
# csim_search.tcl -- C-simulation correctness check for the Search primitives.
#
#     source /tools/Xilinx/Vitis/2023.1/settings64.sh
#     cd ~/fpga-hdc-hls
#     vitis_hls -f scripts/csim_search.tcl 2>&1 | tail -30
#
# WHY THIS EXISTS
#   scripts/csim_sim_dt.tcl is broken and has been for a while: it does
#
#       add_files src/top_sim_dt_test.cpp
#
#   and that file is not in the repository. The testbench compiles and then
#   fails at LINK with "undefined reference to sim_dt_hamming_top". That is a
#   stale script, not a library fault -- but it meant there was no working
#   csim entry point for the search primitives.
#
#   This script uses src/top_search.cpp (which does exist) as the design file
#   and tb/tb_search.cpp as the testbench. tb_search.cpp drives the templates
#   directly rather than going through the top, so csim exercises the actual
#   primitive code across datatypes and across CP/DP settings.
#
# WHAT IT VERIFIES
#   Beyond the original datatype checks, tb_search.cpp now asserts the
#   class-parallelism EQUIVALENCE property: the result must not depend on CP or
#   DP. That is the property the CP restructuring (loop interchange, query
#   broadcast, per-lane accumulators) could plausibly have broken, since it
#   changes the order in which partial results are combined.
#
#   The cases use K=10 with CP up to 8 and D=37 with DP up to 4, so neither
#   loop divides evenly and the ragged final group is exercised on every run.
#
# RUN THIS BEFORE ANY SYNTHESIS SWEEP. csim takes seconds; a sweep takes hours,
# and a sweep of incorrect hardware is worth nothing.
# =============================================================================

source scripts/target.tcl
hdc_target_banner "search csim"

open_project -reset proj_csim_search
set_top search_similarity_top
add_files     src/top_search.cpp -cflags "-I./include"
add_files -tb tb/tb_search.cpp   -cflags "-I./include"
open_solution -reset sol1
hdc_apply_target
csim_design
exit
