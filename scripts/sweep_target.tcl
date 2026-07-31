# =============================================================================
# sweep_target.tcl - retarget BOTH off-chip designs (baseline + dataflow overlap)
# to a chosen device/clock, across the same CP grid.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_target.tcl
#
# ---------------------------------------------------------------------------
# TARGET SELECTION -- edit PART/PERIOD/TAG below.
#
#   ZCU104  xczu7ev-ffvc1156-2-e   Zynq UltraScale+, URAM, DDR4.
#                                  Licensed under WebPACK. Same platform NysX
#                                  reports on, so numbers are directly comparable.
#
#   U280    xcu280-fsvh2892-2L-e   Alveo, HBM. REQUIRES A FULL VIVADO LICENSE --
#                                  device data is installed but WebPACK rejects it
#                                  ("Part is not supported ... appropriate license").
#                                  Switch PART/TAG below once running on a licensed
#                                  machine; nothing else needs to change.
# ---------------------------------------------------------------------------

set PART   xczu7ev-ffvc1156-2-e
set TAG    zcu104
set PERIOD 3.333
;# 300 MHz

proc run_design {tag top src cp part period} {
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top $top
        add_files $src -cflags "-I./include -DHBM_CP=$cp -DHBM_WBITS=512"
        open_solution -reset sol1
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

foreach cp {1 2 4 8} {
    run_design "${TAG}_memoff_c${cp}" memory_offchip_cp_top src/top_memory_offchip_cp.cpp $cp $PART $PERIOD
    run_design "${TAG}_df_c${cp}"     hbm_gather_cp_df_top  src/top_hbm_gather_cp_df.cpp  $cp $PART $PERIOD
}

puts "TARGET SWEEP DONE ($TAG @ $PERIOD ns). Run: python DSE/collect_target.py"
exit
