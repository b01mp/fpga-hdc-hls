# =============================================================================
# sweep_biohd_nolap.tcl - BASELINE arm of the BioHD study: BIO_OVERLAP=0.
# Per reference, burst-load into an on-chip buffer, barrier, then compute.
# Same D / NP / QB / precision / bursts / AXI tuning as sweep_biohd.tcl, so the
# delta against it isolates the fetch/compute overlap alone.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_biohd_nolap.tcl
#
# Reports: proj_biohdnl_x<X>_np<NP>_qb<QB>/ ; run DSE/collect_biohd.py after.
# =============================================================================

proc run_nolap {x np qb part period} {
    set tag "biohdnl_x${x}_np${np}_qb${qb}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top compose_biohd_top
        add_files src/top_compose_biohd.cpp -cflags "-I./include -DHBM_CP=1 -DHBM_WBITS=512 -DBIO_D=10240 -DBIO_X=$x -DBIO_NP=$np -DHBM_QB=$qb -DBIO_OVERLAP=0"
        open_solution -reset sol1
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set ZCU  xczu7ev-ffvc1156-2-e
foreach x {1 32} { foreach np {32 64 128 256} { foreach qb {1 4} { run_nolap $x $np $qb $ZCU 3.333 } } }
puts "BIOHD NOLAP SWEEP DONE."
exit
