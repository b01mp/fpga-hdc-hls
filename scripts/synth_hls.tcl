# =============================================================================
# synth_hls.tcl - C-SYNTHESIS (resource + latency reports) for the synthesizable
# category tops. Run AFTER C-sim, to see the actual hardware cost of each top.
#
#     cd C:/USC/fpga-hdc-hls
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/synth_hls.tcl
#
# NOTES:
#   - generation is intentionally EXCLUDED: its host-side std::random codebook
#     generators are not synthesizable (they C-sim fine, they won't csynth).
#   - Part = the license-free xc7z020 (synthesis is allowed on this tier).
#   - The top wrappers currently pass the DEFAULT arch params (DP=1, etc.), so
#     these are BASELINE numbers. Parallelism scaling shows up once the top
#     wrappers pass DP>1 (the top-wrapper step).
#   - Reports land in: proj_synth_<cat>/sol1/syn/report/<top>_csynth.rpt
# =============================================================================
set PART xc7z020clg484-1
set CLK  10

proc synth_top {name top PART CLK} {
    puts "=================== synth: $name ==================="
    open_project -reset "proj_synth_$name"
    set_top $top
    add_files "src/top_$name.cpp" -cflags "-I./include"
    open_solution -reset "sol1"
    set_part $PART
    create_clock -period $CLK -name default
    csynth_design
    close_project
}

synth_top encoding    encoding_bind_top          $PART $CLK
synth_top aggregation aggregation_threshold_top  $PART $CLK
synth_top search      search_similarity_top      $PART $CLK
synth_top memory      memory_gather_top          $PART $CLK

puts "Synthesis done. Reports: proj_synth_*/sol1/syn/report/*_csynth.rpt"
exit
