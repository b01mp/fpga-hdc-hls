# Quick validation: synthesize two functions to confirm top_characterize.cpp
# compiles (catches signature/skeleton errors) before running the full sweep.
proc run {fn} {
    puts "===== validate $fn ====="
    if {[catch {
        open_project -reset "proj_val_$fn"
        set_top $fn
        add_files src/top_characterize.cpp -cflags "-I./include -DCH_DP=1 -DCH_FP=1 -DCH_CP=1"
        open_solution -reset sol1
        set_part xc7z020clg484-1
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "VALIDATE-FAILED $fn: $err" }
}
run ch_bind
run ch_init_centroids
puts "VALIDATION DONE"
exit
