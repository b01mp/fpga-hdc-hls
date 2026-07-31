# csim_sim_dt.tcl - C-sim correctness check for the datatype-parametric search.
open_project -reset proj_sim_dt
set_top sim_dt_hamming_top
add_files     src/top_sim_dt_test.cpp -cflags "-I./include"
add_files -tb tb/tb_sim_dt.cpp        -cflags "-I./include"
open_solution -reset sol1
set_part xc7z020clg484-1
create_clock -period 10 -name default
csim_design
exit
