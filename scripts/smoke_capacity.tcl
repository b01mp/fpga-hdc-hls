# =============================================================================
# smoke_capacity.tcl -- LOCAL pre-flight for the capacity-crossover sweep.
#
# Run this on your laptop BEFORE touching the server. It csynths the smallest
# point of each design (K=32, binary) on the WebPACK-licensed ZCU104 part, which
# takes a couple of minutes and catches every compile error the full sweep would
# hit an hour into a U280 run.
#
#     & "C:/AMDDesignTools/2026.1/Vitis/bin/vitis-run.bat" --mode hls --tcl scripts/smoke_capacity.tcl
#
# It proves the code COMPILES and SCHEDULES. It does not produce paper numbers --
# wrong part, wrong tool version. Only scripts/sweep_capacity.tcl on the U280
# does that.
#
# Expect: two "csynth_design" completions and no FAILED lines.
# =============================================================================
source scripts/target.tcl

# Force the WebPACK part unless the caller overrode it -- U280 needs a full
# licence and this is meant to run anywhere.
if {![info exists ::env(HDC_PART)]} {
    set HDC_PART $HDC_PART_ZCU104
}
puts "============================================================="
puts " capacity smoke test on $HDC_PART @ $HDC_PERIOD ns"
puts " (compile/schedule check only -- NOT paper numbers)"
puts "============================================================="

set FAILED 0

proc smoke {tag top src defs part period} {
    global FAILED
    puts "=================== smoke: $tag ==================="
    if {[catch {
        open_project -reset "proj_smoke_$tag"
        set_top $top
        add_files $src -cflags "-I./include $defs"
        open_solution -reset sol1
        set_part $part
        create_clock -period $period -name default
        csynth_design
        close_project
    } err]} {
        puts "FAILED $tag: $err"
        incr FAILED
    }
}

# on-chip baseline, smallest point
smoke "onchip_k32_x1" onchip_search_top src/top_onchip_search.cpp \
      "-DONC_D=10240 -DONC_X=1 -DONC_K=32 -DONC_QB=4" $HDC_PART $HDC_PERIOD

# off-chip streaming design, matching point
smoke "offchip_k32_x1" compose_biohd_top src/top_compose_biohd.cpp \
      "-DBIO_D=10240 -DBIO_X=1 -DBIO_NP=32 -DHBM_QB=4 -DHBM_CP=1 -DBIO_OVERLAP=1" \
      $HDC_PART $HDC_PERIOD

# int32 on-chip, to exercise the dot-product path and a large codebook
smoke "onchip_k32_x32" onchip_search_top src/top_onchip_search.cpp \
      "-DONC_D=10240 -DONC_X=32 -DONC_K=32 -DONC_QB=4" $HDC_PART $HDC_PERIOD

puts ""
if {$FAILED} {
    puts "SMOKE TEST FAILED: $FAILED design(s) did not synthesize."
    puts "Fix these before running scripts/sweep_capacity.tcl on the U280."
} else {
    puts "SMOKE TEST PASSED. Safe to run scripts/sweep_capacity.tcl on the server."
}
exit
