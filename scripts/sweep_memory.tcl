# =============================================================================
# sweep_memory.tcl - characterize the MEMORY knob across (memory_space x banking).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_memory.tcl
#
# On-chip configs override MEM_DP / USE_URAM via -D (needs the #ifndef guards in
# top_memory_tier.cpp). Off-chip is a separate top. Each run is wrapped in catch,
# so a failing config (e.g. URAM needs a licensed part) won't abort the sweep.
# Reports land in proj_sw_<tag>/sol1/syn/report/ ; run collect_memory.py after.
# =============================================================================

proc run_onchip {tag dp uram part} {
    puts "================= onchip: $tag (dp=$dp uram=$uram part=$part) ================="
    if {[catch {
        open_project -reset "proj_sw_$tag"
        set_top memory_tier_top
        add_files src/top_memory_tier.cpp -cflags "-I./include -DMEM_DP=$dp -DUSE_URAM=$uram"
        open_solution -reset sol1
        set_part $part
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

proc run_offchip {tag part} {
    puts "================= offchip: $tag (part=$part) ================="
    if {[catch {
        open_project -reset "proj_sw_$tag"
        set_top memory_offchip_top
        add_files src/top_memory_offchip.cpp -cflags "-I./include"
        open_solution -reset sol1
        set_part $part
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set Z xc7z020clg484-1
set U xczu7ev-ffvc1156-2-e

run_onchip bram_dp1 1 0 $Z
run_onchip bram_dp2 2 0 $Z
run_onchip bram_dp4 4 0 $Z
run_onchip bram_dp8 8 0 $Z
run_onchip uram_dp1 1 1 $U
run_onchip uram_dp4 4 1 $U
run_offchip offchip $Z

puts "SWEEP DONE. Reports in proj_sw_*/sol1/syn/report/  ->  run: python DSE/collect_memory.py"
exit
