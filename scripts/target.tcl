# =============================================================================
# target.tcl -- single source of truth for the synthesis target.
#
# WHY THIS EXISTS
#   The paper targets the Alveo U280. Historically each sweep script hardcoded
#   its own part and clock, and they did not agree:
#
#     sweep_characterize.tcl        xc7z020clg484-1     100 MHz
#     synth_datatype.tcl            xc7z020clg484-1     100 MHz
#     sweep_memory.tcl              xc7z020 + xczu7ev   100 MHz
#     sweep_biohd.tcl               xczu7ev  (ZCU104)   300 MHz
#     sweep_memory_onchip_cp.tcl    xczu7ev  (ZCU104)   300 MHz
#     sweep_target.tcl              xcu280              300 MHz
#
#   Only one of six targeted the part the paper is about. Resource counts are
#   not comparable across parts, latency/interval estimates are not comparable
#   across Vitis versions, and the ZCU104 runs were only ever a stopgap taken
#   while the U280 server was unavailable.
#
#   Worse, csynth does not check whether a design fits the device, so the
#   xc7z020 characterization contains points that cannot be built on xc7z020:
#
#     gemm    DP=8  ->  256 DSP     xc7z020 has 220 DSP  -- INFEASIBLE
#     matvec  DP=8  ->  256 DSP     xc7z020 has 220 DSP  -- INFEASIBLE
#
#   Both fit comfortably on the U280 (9,024 DSP). Retargeting therefore fixes a
#   correctness problem in the candidate database, not only a consistency one.
#
# USAGE
#   Put this near the top of a sweep script, before any set_part:
#
#       source scripts/target.tcl
#
#   then either read $HDC_PART / $HDC_PERIOD directly, or call the helper
#   inside an open solution:
#
#       hdc_apply_target
#
#   Tag your output with $HDC_TAG so collectors and CSV filenames record which
#   device produced the numbers.
#
# ENVIRONMENT OVERRIDES
#   HDC_PART     full part string      default xcu280-fsvh2892-2L-e
#   HDC_PERIOD   clock period in ns    default 3.333  (300 MHz)
#   HDC_TAG      short device tag      default u280
#
#   Example, to reproduce an old ZCU104 run for comparison:
#       export HDC_PART=xczu7ev-ffvc1156-2-e HDC_PERIOD=3.333 HDC_TAG=zcu104
#
# LICENSING
#   xcu280 needs a FULL Vivado licence. It is rejected under WebPACK, so these
#   sweeps must run on the licensed server (yangzi), not on a WebPACK machine.
#   ZCU104 (xczu7ev) is WebPACK-licensed and is the fallback for local smoke
#   tests only -- never for numbers that go in the paper.
# =============================================================================

proc hdc_envdef {name default} {
    if {[info exists ::env($name)]} {
        set v $::env($name)
        if {[string length [string trim $v]] > 0} { return $v }
    }
    return $default
}

# ---- Known parts, for reference and for easy override -----------------------
set HDC_PART_U280   xcu280-fsvh2892-2L-e     ;# Alveo U280, HBM2   -- PAPER TARGET
set HDC_PART_ZCU104 xczu7ev-ffvc1156-2-e     ;# Zynq US+, WebPACK  -- legacy stopgap
set HDC_PART_Z7020  xc7z020clg484-1          ;# Zynq-7020          -- legacy, too small

# ---- The active target ------------------------------------------------------
set HDC_PART   [hdc_envdef HDC_PART   $HDC_PART_U280]
set HDC_PERIOD [hdc_envdef HDC_PERIOD 3.333]
set HDC_TAG    [hdc_envdef HDC_TAG    u280]

# ---- Apply inside an open solution ------------------------------------------
proc hdc_apply_target {} {
    global HDC_PART HDC_PERIOD
    set_part $HDC_PART
    create_clock -period $HDC_PERIOD -name default
}

proc hdc_target_banner {{what "sweep"}} {
    global HDC_PART HDC_PERIOD HDC_TAG
    set mhz [format "%.1f" [expr {1000.0 / $HDC_PERIOD}]]
    puts "============================================================="
    puts " $what target: $HDC_PART"
    puts " clock: $HDC_PERIOD ns ($mhz MHz)   tag: $HDC_TAG"
    puts " (override with HDC_PART / HDC_PERIOD / HDC_TAG)"
    puts "============================================================="
}
