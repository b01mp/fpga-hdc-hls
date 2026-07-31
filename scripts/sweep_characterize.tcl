# =============================================================================
# sweep_characterize.tcl - parallelism characterization of every synthesizable
# library function. DP swept for all functions; CP decoupled for similarity &
# convergence (CP does not vary with DP).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_characterize.tcl
#
# Group 1 (15 functions): DP in {1,4,8}, FP=DP, CP=1 (unused).
# Group 2 (2 functions: similarity, convergence): DP in {1,4,8} × CP in {1,2,4,8}
#   (decoupled, ~24 additional runs for these two).
# Total: ~45 + 24 = 69 runs. Reports land in proj_ch_<fn>_dp<N>_cp<M>/sol1/syn/report/
# Run collect_characterize.py after.
# =============================================================================

proc run {fn dp fp cp} {
    set tag "${fn}_dp${dp}_cp${cp}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_ch_${tag}"
        set_top $fn
        add_files src/top_characterize.cpp -cflags "-I./include -DCH_DP=$dp -DCH_FP=$fp -DCH_CP=$cp"
        open_solution -reset sol1
        set_part xc7z020clg484-1
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

# Group 1: functions without CP (or CP not used)
set FUNCS_NO_CP {ch_bind ch_permute ch_scale ch_gemm ch_matvec ch_transpose ch_flatten \
                 ch_bundle ch_threshold ch_normalize ch_cast ch_update \
                 ch_gather ch_place ch_init_centroids}

foreach fn $FUNCS_NO_CP {
    foreach dp {1 4 8} {
        run $fn $dp $dp 1
    }
}

puts "Group 1 (15 functions, DP varied, CP=1) done."

# Group 2: functions with independent CP
set FUNCS_CP {ch_similarity ch_convergence}

foreach fn $FUNCS_CP {
    foreach dp {1 4 8} {
        foreach cp {1 2 4 8} {
            run $fn $dp $dp $cp
        }
    }
}

puts "CHARACTERIZATION SWEEP DONE. Run: python DSE/collect_characterize.py"
exit
