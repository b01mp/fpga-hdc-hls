# run_hbm_gather.tcl - C-sim the streaming wide-port hbm_gather.
# csim is part-agnostic; for csynth on the real target swap in:
#   set_part xcu280-fsvh2892-2L-e   ;  create_clock -period 3.33 -name default
open_project -reset proj_hbm_gather
set_top hbm_gather_top
add_files     src/top_hbm_gather.cpp -cflags "-I./include -DHBM_WBITS=256"
add_files -tb tb/tb_hbm_gather.cpp   -cflags "-I./include -DHBM_WBITS=256"
open_solution -reset sol1
set_part xc7z020clg484-1
create_clock -period 10 -name default
csim_design
exit
