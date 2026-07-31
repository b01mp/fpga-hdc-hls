# =============================================================================
# sweep_hbm_gather.tcl - characterize the STREAMING wide-port hbm_gather over the
# port width HBM_WBITS (single wide m_axi port + deep FIFO + outstanding reads).
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/sweep_hbm_gather.tcl
#
# Characterizes the producer only (hbm_gather_char = memory read -> AXI-Stream),
# so numbers reflect the real off-chip access, not the demo unpack. csynth on
# xc7z020 (part-agnostic estimate); U280 final numbers come later. Reports land in
# proj_hbm_w<WBITS>/sol1/syn/report/ ; run DSE/collect_hbm.py after.
# =============================================================================

proc run_w {wbits part} {
    set tag "hbm_w${wbits}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_$tag"
        set_top hbm_gather_char
        add_files src/top_hbm_gather_char.cpp -cflags "-I./include -DHBM_WBITS=$wbits"
        open_solution -reset sol1
        set_part $part
        create_clock -period 10 -name default
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

set Z xc7z020clg484-1

foreach wbits {128 256 512} {
    run_w $wbits $Z
}

puts "HBM WBITS SWEEP DONE. Run: python DSE/collect_hbm.py"
exit
