# =============================================================================
# sweep_characterize.tcl -- per-primitive parallelism characterization.
#
#     source /tools/Xilinx/Vitis/2023.1/settings64.sh
#     cd ~/fpga-hdc-hls
#
#     # Phase 2 -- the 15 primitives with no CP axis. Safe to run at any time.
#     HDC_CH_PHASE=nocp nohup vitis_hls -f scripts/sweep_characterize.tcl \
#         > ch_nocp.log 2>&1 &
#
#     # Phase 3 -- similarity and convergence. Run AFTER the CP diagnostic.
#     HDC_CH_PHASE=cp   nohup vitis_hls -f scripts/sweep_characterize.tcl \
#         > ch_cp.log 2>&1 &
#
#     python3 DSE/collect_characterize.py
#
# -----------------------------------------------------------------------------
# WHAT CHANGED FROM THE ORIGINAL SWEEP, AND WHY
#
#   1. TARGET.  Was xc7z020 at 100 MHz, hardcoded. Now U280 at 300 MHz via
#      scripts/target.tcl. This is a CORRECTNESS fix, not a cosmetic one: the
#      old sweep produced points that cannot be built on the part they were
#      measured on --
#
#          gemm   DP=8  -> 256 DSP      xc7z020 has 220 DSP   INFEASIBLE
#          matvec DP=8  -> 256 DSP      xc7z020 has 220 DSP   INFEASIBLE
#
#      Both fit comfortably on the U280 (9,024 DSP). Retargeting removes
#      invalid rows from the candidate database the DSE searches.
#
#   2. DIMENSION.  Was D=256. Now D=10240, the same anchor the capacity
#      crossover uses, so the scaling results and the capacity results describe
#      one machine instead of two unrelated configurations.
#
#      Honest note on what this buys: for MAP-shaped primitives (bind, permute,
#      threshold, gather, cast, flatten) both latency and ideal latency scale
#      linearly with D, so the EFFICIENCY ratios will barely move -- bind will
#      still land near 7.4x. The reason to run at 10240 is coherence and
#      credibility, not new efficiency values. Where D genuinely may change the
#      answer is the reduction-tailed primitives (normalize, convergence),
#      whose fixed serial tail a 40x longer loop can amortize.
#
#   3. PROTOTYPE COUNT.  Was KP=10. Now KP=64. KP=10 is what made the CP result
#      ambiguous -- CP=8 on a 10-iteration loop has almost nothing to divide.
#      At KP=64, CP=8 gets 8 classes per lane. KP touches update,
#      init_centroids, convergence and similarity only.
#
#   4. DP GRID.  Was {1,4,8}. Now {1,2,4,8}. Three points is two endpoints and
#      a dot; four points is a curve you can plot and fit.
#
#   5. PHASES.  The sweep is now splittable, because the CP verdict must not be
#      allowed to invalidate work that does not depend on it:
#
#          nocp  15 primitives with no CP axis          60 runs   ALWAYS SAFE
#          cp    similarity + convergence               14 runs   run last
#          all   both                                   74 runs
#
#      Nothing about restructuring CP would change bind's DP curve, so the
#      `nocp` phase can run immediately and in parallel with the CP diagnostic.
#      The `cp` phase is the only work that would need redoing if the
#      diagnostic finds CP broken -- so it goes last.
#
#   6. PROJECT NAMES now carry D and KP:
#          proj_ch_<fn>_d<D>_k<KP>_dp<N>_cp<M>
#      The legacy proj_ch_<fn>_dp<N>_cp<M> directories are a different shape
#      and will not be overwritten or confused with these.
#
# -----------------------------------------------------------------------------
# WHY GROUP 2 IS NOT A FULL GRID
#   similarity and convergence take both knobs, but this sweep runs only the
#   ISOLATED SLICES: DP varied with CP=1, and CP varied with DP=1. `proto` is
#   ARRAY_PARTITION'd cyclic by CP on dim=1 and by DP on dim=2, so with both
#   above 1 they contend for the same array and no speedup is attributable to
#   either knob. One knob at a time is what makes this an ablation.
#
#   The interior of the grid -- where the knobs interact -- is a separate
#   experiment (the knob-interaction task) and is deliberately not collected
#   here, where it would be mistaken for ablation data.
#
# ENVIRONMENT
#   HDC_CH_PHASE   nocp | cp | all      default all
#   HDC_CH_D       hv dimension         default 10240
#   HDC_CH_KP      prototype count      default 64
#   HDC_PART / HDC_PERIOD / HDC_TAG     see scripts/target.tcl
# =============================================================================

source scripts/target.tcl

set CH_PHASE [hdc_envdef HDC_CH_PHASE all]
set CH_D     [hdc_envdef HDC_CH_D     10240]
set CH_KP    [hdc_envdef HDC_CH_KP    64]

set DP_GRID {1 2 4 8}
set CP_GRID {2 4 8}          ;# CP=1 comes free from the DP grid's first point

hdc_target_banner "characterization"
puts " phase: $CH_PHASE     D: $CH_D     KP: $CH_KP"
puts " DP grid: $DP_GRID    CP grid: 1 $CP_GRID"
puts "============================================================="

proc run_pt {fn d kp dp cp} {
    set tag "${fn}_d${d}_k${kp}_dp${dp}_cp${cp}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_ch_${tag}"
        set_top $fn
        add_files src/top_characterize.cpp \
            -cflags "-I./include -DCH_D=$d -DCH_KP=$kp -DCH_DP=$dp -DCH_FP=$dp -DCH_CP=$cp"
        open_solution -reset sol1
        hdc_apply_target
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

# The 15 primitives with no class-parallelism axis. CP is passed as 1 and is
# unused by every one of them.
set FUNCS_NO_CP {ch_bind ch_permute ch_scale ch_gemm ch_matvec ch_transpose \
                 ch_flatten ch_bundle ch_threshold ch_normalize ch_cast \
                 ch_update ch_gather ch_place ch_init_centroids}

# The two primitives that take CP.
set FUNCS_CP {ch_similarity ch_convergence}

# ---- Phase: nocp ------------------------------------------------------------
if {$CH_PHASE eq "nocp" || $CH_PHASE eq "all"} {
    puts "\n########## PHASE nocp -- 15 primitives x [llength $DP_GRID] DP ##########"
    foreach fn $FUNCS_NO_CP {
        foreach dp $DP_GRID {
            run_pt $fn $CH_D $CH_KP $dp 1
        }
    }
    puts "\nPHASE nocp DONE."
}

# ---- Phase: cp --------------------------------------------------------------
if {$CH_PHASE eq "cp" || $CH_PHASE eq "all"} {
    puts "\n########## PHASE cp -- similarity + convergence, isolated slices ##########"
    foreach fn $FUNCS_CP {
        # DP curve, CP pinned at 1
        foreach dp $DP_GRID {
            run_pt $fn $CH_D $CH_KP $dp 1
        }
        # CP curve, DP pinned at 1 (CP=1 already covered above)
        foreach cp $CP_GRID {
            run_pt $fn $CH_D $CH_KP 1 $cp
        }
    }
    puts "\nPHASE cp DONE."
}

puts ""
puts "============================================================="
puts " CHARACTERIZATION SWEEP DONE   (phase: $CH_PHASE)"
puts " next: python3 DSE/collect_characterize.py"
puts "============================================================="
exit
