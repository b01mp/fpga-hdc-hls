# =============================================================================
# sweep_precision.tcl -- per-stage precision study, Tier A (lossless).
#
#     source /tools/Xilinx/Vitis/2023.1/settings64.sh
#     cd ~/fpga-hdc-hls
#     vitis_hls -f scripts/csim_precision.tcl          # correctness gate FIRST
#     nohup vitis_hls -f scripts/sweep_precision.tcl > precision.log 2>&1 &
#     python3 DSE/collect_precision.py
#
# THE QUESTION
#   An HDC pipeline carries two integer intermediates whose correct widths are
#   set by DIFFERENT quantities:
#
#     bundle accumulator   0..N   where N = features/symbols bundled
#     similarity score     0..D   where D = hypervector dimension
#
#   N and D are unrelated. A framework with one global datapath width has to
#   pick a single number for both. This sweep measures what that costs.
#
# THE FIVE CONFIGURATIONS, and why each is here
#
#   wide        ACC=32, SIM=32     what a single-global-width framework builds
#   acc_only    ACC=rule, SIM=32   isolates the accumulator saving
#   sim_only    ACC=32, SIM=rule   isolates the score saving
#   right       ACC=rule, SIM=rule both stages sized independently -- the design
#   short       ACC=rule, SIM=rule-1   one bit under on the score
#
#   acc_only and sim_only exist so the total saving can be ATTRIBUTED. Without
#   them "right vs wide" is one number with two causes mixed together.
#
#   `short` is not a proposal, it is the control that shows there is no cheaper
#   correct point below `right`. Its area should be barely under `right` while
#   its output is wrong (tb_precision case 2 proves the wrongness; this sweep
#   supplies the area). Together they say: the boundary is a cliff, not a knee.
#
# WHY BOTH D VALUES
#   The score rule scales with D and the accumulator rule does not. Sweeping D
#   shows the two stages diverging -- at D=1024 the score needs 12 bits, at
#   D=10240 it needs 15, while the accumulator stays at 3..5 throughout. One
#   global width cannot track that.
#
# ENVIRONMENT
#   HDC_PREC_D    space-separated D list    default "1024 10240"
#   HDC_PART / HDC_PERIOD / HDC_TAG         see scripts/target.tcl
# =============================================================================

source scripts/target.tcl

set D_LIST [hdc_envdef HDC_PREC_D "1024 10240"]

hdc_target_banner "per-stage precision"
puts " D list: $D_LIST"
puts "============================================================="

# name  top                              source                  macro-prefix  N(bundled)
set APPS {
    {image  image_classification_top     src/top_application.cpp  APP  16}
    {genome genome_sequence_search_top   src/top_genome.cpp       GEN   8}
    {ts     time_series_classification_top src/top_time_series.cpp TS    6}
}

# bits needed to represent 0..v
proc bits_for {v} {
    set b 0
    while {$v > 0} { incr b; set v [expr {$v >> 1}] }
    return $b
}

proc run_pt {tag top src pfx d k accb simb} {
    puts "===================== $tag ====================="
    if {[catch {
        open_project -reset "proj_prec_${tag}"
        set_top $top
        add_files $src -cflags \
            "-I./include -D${pfx}_D=$d -D${pfx}_ACC_BITS=$accb -D${pfx}_SIM_BITS=$simb"
        open_solution -reset sol1
        hdc_apply_target
        csynth_design
        close_project
    } err]} { puts "FAILED $tag: $err" }
}

foreach app $APPS {
    lassign $app name top src pfx nbund

    set acc_rule [bits_for $nbund]

    foreach d $D_LIST {
        # score rule: bits_for(D) magnitude + 1 sign
        set sim_rule [expr {[bits_for $d] + 1}]

        puts ""
        puts "########## $name  D=$d   acc_rule=$acc_rule  sim_rule=$sim_rule ##########"

        run_pt "${name}_d${d}_wide"     $top $src $pfx $d 0 32        32
        run_pt "${name}_d${d}_acconly"  $top $src $pfx $d 0 $acc_rule 32
        run_pt "${name}_d${d}_simonly"  $top $src $pfx $d 0 32        $sim_rule
        run_pt "${name}_d${d}_right"    $top $src $pfx $d 0 $acc_rule $sim_rule
        run_pt "${name}_d${d}_short"    $top $src $pfx $d 0 $acc_rule [expr {$sim_rule - 1}]
    }
}

puts ""
puts "============================================================="
puts " PRECISION SWEEP DONE"
puts " next: python3 DSE/collect_precision.py"
puts "============================================================="
exit
