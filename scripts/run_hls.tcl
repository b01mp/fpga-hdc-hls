# =============================================================================
# run_hls.tcl - C-simulate the FPGA-HDC library primitives, per category.
#
# Toolchain note (this machine has Vitis 2026.1, no standalone vitis_hls.exe):
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/run_hls.tcl
#
# One project per category; each sets a concrete top wrapper (src/top_*.cpp) and
# C-sims the category testbench (tb/tb_*.cpp). Part is the license-free xc7z020
# (part does NOT affect C-sim results). csynth is included but commented -- turn
# it on once C-sim is green (real ZU7EV/ZCU104 synth needs a higher license tier).
# =============================================================================

set INC   "-I./include"
set PART  xc7z020clg484-1
set CLK   10

# proc: build a project for one category and run C-sim.
#   name  - project/category name
#   top   - top function symbol (in src/top_<name>.cpp)
proc run_category {name top INC PART CLK} {
    puts "=================== category: $name ==================="
    open_project -reset "proj_$name"
    set_top $top
    add_files "src/top_$name.cpp"        -cflags $INC
    add_files -tb "tb/tb_$name.cpp"      -cflags $INC
    open_solution -reset "sol1"
    set_part $PART
    create_clock -period $CLK -name default
    csim_design
    # csynth_design           ;# enable once C-sim is green
    # cosim_design            ;# enable after csynth (needs tb to drive the top)
    close_project
}

run_category encoding    encoding_bind_top          $INC $PART $CLK
run_category aggregation aggregation_threshold_top  $INC $PART $CLK
run_category search      search_similarity_top      $INC $PART $CLK

puts "All category C-sims dispatched. Check each proj_*/sol1/csim/report for PASS."
exit
