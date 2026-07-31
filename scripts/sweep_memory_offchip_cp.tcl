# =============================================================================
# sweep_memory_offchip_cp.tcl - characterize the BASELINE off-chip reader: wide
# ports, CP independent channels, burst-tuned, but NO fetch/compute overlap
# (on-chip row buffer + barrier instead of FIFO + DATAFLOW).
#
# Pairs 1:1 with sweep_hbm_gather_cp_df.tcl -- same D=8192, same HBM_WBITS=512,
# same CP grid, same compute -- so the ONLY independent variable between the two
# sweeps is the fetch/compute overlap.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_memory_offchip_cp.tcl
#
# csynth on xc7z020 (part-agnostic estimate). Reports land in
# proj_memoff_cp<CP>/sol1/syn/report/ ; run DSE/collect_memory_offchip_cp.py after.
# =============================================================================

proc run_base_cp {cp part} {
    set tag "memoff_cp${cp}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top memory_offchip_cp_top
        add_files src/top_memory_offchip_cp.cpp -cflags "-I./include -DHBM_CP=$cp -DHBM_WBITS=512"
        open_solution -reset sol1
        set_part $part
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set Z xc7z020clg484-1

foreach cp {1 2 4 8} {
    run_base_cp $cp $Z
}

puts "OFFCHIP BASELINE CP SWEEP DONE. Run: python DSE/collect_memory_offchip_cp.py"
exit
