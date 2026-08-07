# =============================================================================
# sweep_capacity.tcl -- the ON-CHIP / OFF-CHIP CAPACITY CROSSOVER sweep.
#
#   Server (U280, needs a full Vivado licence):
#       source /tools/Xilinx/Vitis/2023.1/settings64.sh
#       vitis_hls -f scripts/sweep_capacity.tcl 2>&1 | tee capacity_sweep.log
#       python3 DSE/collect_capacity.py
#
#   RUN scripts/smoke_capacity.tcl LOCALLY FIRST. It compiles the same code on a
#   WebPACK part in a couple of minutes and catches every syntax/schedule error
#   this sweep would otherwise hit an hour in.
#
# THE EXPERIMENT
#   Prior FPGA-HDC keeps the whole reference library in on-chip memory, which
#   silently bounds the problem sizes it can express. This sweep grows the
#   library across that boundary, at three precisions, for both memory tiers:
#
#       on-chip  (top_onchip_search.cpp)  -- what prior work builds
#       off-chip (top_compose_biohd.cpp)  -- the streaming design
#
#   The on-chip line ends when K x D x X exceeds device memory. The streaming
#   line does not. The cliff moves by 32x purely from the precision choice --
#   same application, same code, one parameter.
#
# AXES        D = 10240 (BioHD anchor), QB = 4, CP = 1 -- all held constant.
#   ONC_K / BIO_NP : 32 64 128 256 512 1024   (references in the library)
#   ONC_X / BIO_X  : 1 (binary) 8 (int8) 32 (int32)
#   tier           : onchip, offchip
#
#   36 runs. Ordered smallest-first, so a partial run still yields a usable
#   left-hand side of the plot if you have to stop it.
#
# NOTE ON pow2: the streaming path requires WBITS % X == 0, and 512/6 is not an
# integer, so a 6-bit pow2 element has to be padded to 8 bits to be packed into
# 512-bit words. The X=8 column therefore doubles as the pow2 slot once the pow2
# overloads land in similarity_search_stream_dt.hpp (deferred, Tier 5). Worth
# reporting on its own: the theoretical 6-bit representation costs 8 bits in a
# 512-bit-word streaming system.
# =============================================================================
source scripts/target.tcl
hdc_target_banner "capacity crossover sweep"

set KS {32 64 128 256 512 1024}
set XS {1 8 32}
set D  10240
set QB 4

set FAILED 0
set RUNS   0

proc run_point {tag top src defs part period} {
    global FAILED RUNS
    incr RUNS
    puts "=================== \[$RUNS\] $tag ==================="
    if {[catch {
        open_project -reset "proj_cap_$tag"
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

foreach x $XS {
    foreach k $KS {
        # ---- on-chip baseline: library resident in BRAM ----
        run_point "onchip_x${x}_k${k}" onchip_search_top src/top_onchip_search.cpp \
            "-DONC_D=$D -DONC_X=$x -DONC_K=$k -DONC_QB=$QB" $HDC_PART $HDC_PERIOD

        # ---- off-chip streaming design: library streamed through a FIFO ----
        run_point "offchip_x${x}_k${k}" compose_biohd_top src/top_compose_biohd.cpp \
            "-DBIO_D=$D -DBIO_X=$x -DBIO_NP=$k -DHBM_QB=$QB -DHBM_CP=1 -DBIO_OVERLAP=1" \
            $HDC_PART $HDC_PERIOD
    }
}

puts ""
puts "CAPACITY SWEEP DONE on $HDC_PART @ $HDC_PERIOD ns."
puts "  $RUNS run(s), $FAILED failure(s)."
puts "Collect with: python3 DSE/collect_capacity.py"
puts ""
puts "NOTE: an on-chip point that exceeds device memory does NOT fail here --"
puts "csynth happily reports 400% BRAM. The fit check is in the collector."
exit
