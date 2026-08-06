# =============================================================================
# toolcheck_target.tcl -- A/B the Vitis VERSION, holding the device fixed.
#
# WHY THIS EXISTS
#   Two sweeps of the SAME source disagree on initiation interval:
#
#     DSE/synth_results/zcu104_sweep.csv   Vitis 2026.1, Windows, xczu7ev
#       dataflow_overlap CP=1 -> latency 28, interval 16, 3.605 ns (277.4 MHz)
#
#     DSE/synth_results/u280_sweep.csv     Vitis HLS 2023.1, yangzi, xcu280
#       dataflow_overlap CP=1 -> latency 28, interval 28, 2.433 ns (411.0 MHz)
#
#   Same design, same CP, same 512-bit port. Latency agrees; the INTERVAL does
#   not. Measured against the buffered baseline's interval of 51, that is a
#   3.19x throughput gain in one case and 1.82x in the other. That is a
#   headline-sized difference, and TWO variables changed at once (device AND
#   tool version), so neither sweep can be quoted as a comparison until they
#   are separated.
#
# WHAT THIS DOES
#   Runs the same two off-chip designs on ONE part at ONE CP, so the only
#   remaining variable is the Vitis version. Run it under 2023.1 on the
#   licensed server with the part left at its ZCU104 default, then compare
#   against the existing 2026.1 ZCU104 rows.
#
#     interval comes out 16  -> the gap is the DEVICE; both sweeps stand.
#     interval comes out 28  -> the gap is the COMPILER, and every table that
#                               mixes the two versions must be regenerated
#                               under a single one before it is published.
#
#   Deliberately small: CP=1 only by default, so this is two csynth runs, not
#   eight. The server is remote; widen HDC_TC_CPS once the question is settled.
#
# USAGE
#   Linux server (yangzi), under the version you want to test:
#       source /tools/Xilinx/Vitis/2023.1/settings64.sh
#       export HDC_TC_TAG=zcu104tc23
#       vitis_hls -f scripts/toolcheck_target.tcl
#       HDC_TARGET_TAG=zcu104tc23 HDC_TARGET_DEVICE=zcu104 python3 DSE/collect_target.py
#
#   Windows, under 2026.1 (control run -- should reproduce zcu104_sweep.csv):
#       $env:HDC_TC_TAG="zcu104tc26"
#       & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/toolcheck_target.tcl
#       $env:HDC_TARGET_TAG="zcu104tc26"; $env:HDC_TARGET_DEVICE="zcu104"
#       python DSE/collect_target.py
#
# ENVIRONMENT
#   HDC_TC_PART    part string          default xczu7ev-ffvc1156-2-e (ZCU104)
#   HDC_TC_PERIOD  clock period in ns   default 3.333 (300 MHz)
#   HDC_TC_TAG     project name tag     default toolcheck
#   HDC_TC_CPS     CP values to run     default 1
#
#   Project dirs are named proj_<TAG>_memoff_c<CP> and proj_<TAG>_df_c<CP> so
#   DSE/collect_target.py picks them up unchanged via HDC_TARGET_TAG.
#
#   NOTE: xcu280 needs a full Vivado licence and is rejected under WebPACK, so
#   the ZCU104 default is the part to use for this A/B. It is UltraScale+ like
#   the U280 and is the platform NysX reports on.
# =============================================================================

proc envdef {name default} {
    if {[info exists ::env($name)]} {
        set v $::env($name)
        if {[string length [string trim $v]] > 0} { return $v }
    }
    return $default
}

set PART   [envdef HDC_TC_PART   xczu7ev-ffvc1156-2-e]
set PERIOD [envdef HDC_TC_PERIOD 3.333]
set TAG    [envdef HDC_TC_TAG    toolcheck]
set CPS    [envdef HDC_TC_CPS    1]

puts "============================================================="
puts " toolcheck: part=$PART  period=$PERIOD ns  tag=$TAG  cps=$CPS"
puts " Record the Vitis version printed in the log and in each"
puts " report's '* Version:' line -- that is the variable under test."
puts "============================================================="

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

foreach cp $CPS {
    run_design "${TAG}_memoff_c${cp}" memory_offchip_cp_top src/top_memory_offchip_cp.cpp $cp $PART $PERIOD
    run_design "${TAG}_df_c${cp}"     hbm_gather_cp_df_top  src/top_hbm_gather_cp_df.cpp  $cp $PART $PERIOD
}

puts ""
puts "TOOLCHECK DONE ($TAG, part $PART @ $PERIOD ns)."
puts "Collect with:  HDC_TARGET_TAG=$TAG HDC_TARGET_DEVICE=zcu104 python3 DSE/collect_target.py"
puts "Then compare the dataflow_overlap CP=1 interval against zcu104_sweep.csv (=16, Vitis 2026.1)."
exit
