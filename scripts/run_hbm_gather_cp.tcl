# run_hbm_gather_cp.tcl - C-sim the class-parallel streaming gather (CP=8).
# csim is part-agnostic; csynth on the real target uses set_part xcu280-fsvh2892-2L-e.
open_project -reset proj_hbm_gather_cp
set_top hbm_gather_cp_top
add_files     src/top_hbm_gather_cp.cpp -cflags "-I./include -DHBM_CP=8 -DHBM_WBITS=512"
add_files -tb tb/tb_hbm_gather_cp.cpp   -cflags "-I./include -DHBM_CP=8 -DHBM_WBITS=512"
open_solution -reset sol1
set_part xc7z020clg484-1
create_clock -period 10 -name default
csim_design
exit
