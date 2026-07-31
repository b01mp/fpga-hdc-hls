# =============================================================================
# sweep_biohd.tcl - BioHD precision x prototype-count x query-batch study,
# ZCU104 @300 MHz.
#
# Anchored to BioHD (ISCA'22): D=10,240 (10k padded to a 512-bit multiple);
# binary/Hamming/argmin vs 32-bit-integer/dot/argmax library; query always
# binary (so the dot product is conditional add/subtract -- no multiplier).
#
# Swept:  BIO_X  in {1, 32}          binary vs int32 library
#         BIO_NP in {32,64,128,256}  reference hypervectors per scan
#         HBM_QB in {1, 4}           QB=1 is the NO-BATCHING BASELINE; QB=4 is
#                                    the batched design. Same datapath, same
#                                    overlap -- the only difference is reuse, so
#                                    every cell carries its own baseline.
# Fixed:  HBM_CP=1 (channel scaling is orthogonal and characterized separately).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_biohd.tcl
#
# Reports: proj_biohd_x<X>_np<NP>_qb<QB>/ ; run DSE/collect_biohd.py after.
# =============================================================================

proc run_biohd {x np qb part period} {
    set tag "biohd_x${x}_np${np}_qb${qb}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top compose_biohd_top
        add_files src/top_compose_biohd.cpp -cflags "-I./include -DHBM_CP=1 -DHBM_WBITS=512 -DBIO_D=10240 -DBIO_X=$x -DBIO_NP=$np -DHBM_QB=$qb"
        open_solution -reset sol1
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set ZCU  xczu7ev-ffvc1156-2-e

foreach x {1 32} {
    foreach np {32 64 128 256} {
        foreach qb {1 4} {
            run_biohd $x $np $qb $ZCU 3.333
        }
    }
}

puts "BIOHD SWEEP DONE. Run: python DSE/collect_biohd.py"
exit
