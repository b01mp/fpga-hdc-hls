# =============================================================================
# sweep_cp_diag.tcl -- CP diagnostic. 20 runs. Answers ONE question, with a
# control arm so the answer is attributable.
#
#     source /tools/Xilinx/Vitis/2023.1/settings64.sh
#     cd ~/fpga-hdc-hls
#     nohup vitis_hls -f scripts/sweep_cp_diag.tcl > cp_diag.log 2>&1 &
#     tail -f cp_diag.log
#
#     python3 DSE/collect_cp_diag.py
#
# THE QUESTION
#   In master_table.csv, class_parallelism (CP) buys almost nothing:
#   similarity CP 1->8 is 1.10x for 3.96x the LUTs, and convergence CP 1->8 is
#   0.61x -- actively SLOWER -- for 5.12x the LUTs. Dimension parallelism (DP)
#   on the very same primitives is near-ideal (0.97 and 0.99 efficiency).
#
#   Two explanations fit that data, and they demand opposite responses:
#
#     (A) TOO FEW CLASSES.  Every one of those rows was measured at KP=10.
#         CP=8 on a 10-iteration loop has almost nothing left to divide, and
#         the un-parallelised SEED_DIM prologue is a large fraction of the
#         total. If this is the cause, CP is fine and we simply characterised
#         it outside its useful range.
#
#     (B) THE UNROLL DOES NOT BUILD PARALLEL HARDWARE.  CP sits on the OUTER
#         loop of similarity_search, whose body contains a PIPELINE II=1 inner
#         loop. An outer UNROLL around a pipelined inner loop replicates the
#         datapath -- which is why LUTs go up 4x -- without necessarily letting
#         the copies run concurrently. If this is the cause, CP is a knob the
#         library advertises and does not deliver, and it needs restructuring
#         (loop flattening, explicit banking, or DATAFLOW) before any CP number
#         is worth publishing.
#
#   Sweeping KP tells them apart:
#
#     CP speedup improves as KP grows  ->  (A). Report CP's useful range.
#     CP speedup stays flat at every KP ->  (B). Fix CP, then re-characterise.
#
# WHY THIS RUNS BEFORE THE FULL U280 RE-CHARACTERISATION
#   If (B) holds, the full 69-run sweep would have to be thrown away and redone
#   after the fix. 20 small runs now is cheaper than 69 runs twice.
#
# -----------------------------------------------------------------------------
# THE THREE ARMS
#
#   1. REPRODUCTION  D=256, KP=10, DP=1, CP in {1,2,4,8}                 4 runs
#      The only arm at the legacy problem size, and it is here for exactly one
#      reason: these four points must reproduce the xc7z020 trend (speedup ~1.1x
#      at CP=8). D and KP are held at the old values because a reproduction
#      check that changes the workload is not a reproduction check. If this arm
#      does NOT reproduce, the retarget or the tool version changed something
#      and every other number below is suspect -- stop and investigate.
#
#   2. MAIN  D=10240, KP in {64,256,1024}, DP=1, CP in {1,2,4,8}        12 runs
#      The actual experiment, at a realistic HDC dimension. D=10240 is the same
#      anchor the capacity-crossover study uses, so the scaling results and the
#      capacity results describe the same machine rather than two unrelated toy
#      configurations. KP spans 64 to 1024 so that at CP=8 there are 8 to 128
#      classes per lane -- comfortably enough work to divide, which is the whole
#      thing KP=10 could not offer.
#
#   3. CONTROL  D=10240, KP in {64,1024}, DP in {4,8}, CP=1              4 runs
#      DP is the knob we already believe works (0.92-1.00 efficiency across 17
#      primitives). Measuring it again here is NOT redundant -- it is the
#      control group. Without it, a flat CP curve is ambiguous between "CP is
#      broken" and "something about this device, this tool version or this
#      script is broken". With it:
#
#         DP ~8x and CP ~1x  ->  the fault is CP. Attributable.
#         DP ~1x and CP ~1x  ->  the fault is the setup. Fix that first.
#
#      Four runs to convert an ambiguous result into an attributable one.
#
# WHY THE TWO KNOBS ARE NEVER LIVE AT ONCE
#   Every arm pins one knob at 1. `proto` is ARRAY_PARTITION'd cyclic by CP on
#   dim=1 and by DP on dim=2; with both above 1 they compete for the same array
#   and no speedup could be attributed to either. One knob at a time is what
#   makes this an ablation rather than a configuration sweep.
# =============================================================================

source scripts/target.tcl
hdc_target_banner "CP diagnostic"

set FN ch_similarity

proc run_pt {fn d kp dp cp} {
    set tag "${fn}_d${d}_k${kp}_dp${dp}_cp${cp}"
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_cpd_${tag}"
        set_top $fn
        add_files src/top_characterize.cpp \
            -cflags "-I./include -DCH_D=$d -DCH_KP=$kp -DCH_DP=$dp -DCH_FP=$dp -DCH_CP=$cp"
        open_solution -reset sol1
        hdc_apply_target
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

# ---- Arm 1: reproduction at the legacy problem size -------------------------
puts "\n########## ARM 1/3  reproduction  (D=256, KP=10) ##########"
foreach cp {1 2 4 8} {
    run_pt $FN 256 10 1 $cp
}

# ---- Arm 2: the real CP question at a realistic dimension -------------------
puts "\n########## ARM 2/3  main  (D=10240, CP swept) ##########"
foreach kp {64 256 1024} {
    foreach cp {1 2 4 8} {
        run_pt $FN 10240 $kp 1 $cp
    }
}

# ---- Arm 3: DP control ------------------------------------------------------
puts "\n########## ARM 3/3  control  (D=10240, DP swept, CP=1) ##########"
foreach kp {64 1024} {
    foreach dp {4 8} {
        run_pt $FN 10240 $kp $dp 1
    }
}
# NOTE: the DP=1,CP=1 baselines this arm divides by are already produced by
# arm 2 at the same D and KP -- no extra runs needed for them.

puts ""
puts "============================================================="
puts " CP DIAGNOSTIC DONE -- 20 points"
puts " next: python3 DSE/collect_cp_diag.py"
puts "============================================================="
exit
