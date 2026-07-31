# =============================================================================
# sweep_target.tcl - retarget BOTH off-chip designs (baseline + dataflow overlap)
# to a chosen device/clock, across the same CP grid.
#
#   Linux server (Haoyang):   vitis_hls -f scripts/sweep_target.tcl
#   Windows:                  & ".../Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_target.tcl
#
#   Then collect:             HDC_TARGET_TAG=$TAG python DSE/collect_target.py
#
# This is csynth -- resource + timing ESTIMATES on the real part. It does NOT
# give measured HBM bandwidth; that needs the v++/XRT board flow.
#
# ---------------------------------------------------------------------------
# TARGET SELECTION -- edit PART/PERIOD/TAG below.
#
#   U280 (active) xcu280-fsvh2892-2L-e   Alveo, HBM. Needs a full Vivado licence.
#                                        If set_part is rejected, run `get_parts`
#                                        and pick the exact installed U280 string.
#   ZCU104        xczu7ev-ffvc1156-2-e   Zynq UltraScale+, WebPACK-licensed.
#
# NOTE ON CHANNELS: the tops instantiate up to 8 channels (HBM_CP <= 8). The CP
# grid below therefore stops at 8. To scale toward the U280's 32 HBM pseudo-
# channels, the channel fan-out in hbm_gather_cp.hpp, top_hbm_gather_cp_df.cpp
# and top_memory_offchip_cp.cpp must first be extended with HBM_CP >= 16 / 32
# branches -- do that before adding 16 32 to the loop.
# ---------------------------------------------------------------------------

set PART   xcu280-fsvh2892-2L-e
set TAG    u280
;# ZCU104 alternative: set PART xczu7ev-ffvc1156-2-e ; set TAG zcu104
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
