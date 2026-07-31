# =============================================================================
# sweep_memory_onchip_cp.tcl - ON-CHIP reference sweep (BRAM and URAM tiers).
#
# The codebook is resident in on-chip RAM and read directly -- what prior FPGA-HDC
# accelerators do. This is the tier the off-chip streaming engine must be compared
# against, since it is the alternative solution to the same problem rather than a
# hobbled version of our own design.
#
# Matched to sweep_memory_offchip_cp.tcl / sweep_target.tcl: same D=8192,
# HBM_WBITS=512, same CP grid, same compute, same device and clock target.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_memory_onchip_cp.tcl
#
# Reports land in proj_zcu104_onchip_<tier>_c<CP>/ ; run DSE/collect_onchip_cp.py.
# =============================================================================

proc run_onchip {tag cp uram part period} {
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top memory_onchip_cp_top
        add_files src/top_memory_onchip_cp.cpp -cflags "-I./include -DHBM_CP=$cp -DHBM_WBITS=512 -DMEM_URAM=$uram"
        open_solution -reset sol1
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set PART   xczu7ev-ffvc1156-2-e
set PERIOD 3.333
;# 300 MHz

foreach cp {1 2 4 8} {
    run_onchip "zcu104_onchip_bram_c${cp}" $cp 0 $PART $PERIOD
    run_onchip "zcu104_onchip_uram_c${cp}" $cp 1 $PART $PERIOD
}

puts "ON-CHIP SWEEP DONE. Run: python DSE/collect_onchip_cp.py"
exit
