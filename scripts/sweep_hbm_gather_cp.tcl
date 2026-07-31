# =============================================================================
# sweep_hbm_gather_cp.tcl - characterize the class-parallel streaming gather over
# the channel count HBM_CP (fixed HBM_WBITS=512, D=8192). Each channel streams a
# different hypervector in parallel.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_hbm_gather_cp.tcl
#
# csynth on xc7z020 (part-agnostic estimate). Reports land in
# proj_hbmcp_c<CP>/sol1/syn/report/ ; run DSE/collect_hbm_cp.py after.
# =============================================================================

proc run_cp {cp part} {
    set tag "hbmcp_c${cp}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top hbm_gather_cp_top
        add_files src/top_hbm_gather_cp.cpp -cflags "-I./include -DHBM_CP=$cp -DHBM_WBITS=512"
        open_solution -reset sol1
        set_part $part
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set Z xc7z020clg484-1

foreach cp {1 2 4 8} {
    run_cp $cp $Z
}

puts "HBM CP SWEEP DONE. Run: python DSE/collect_hbm_cp.py"
exit
