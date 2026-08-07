# =============================================================================
# confirm_capacity_cliff.tcl -- empirical confirmation of the on-chip capacity
# cliff, at the boundary point.
#
#   source /tools/Xilinx/Vitis/2023.1/settings64.sh
#   vivado -mode batch -source scripts/confirm_capacity_cliff.tcl 2>&1 | tee cliff_confirm.log
#
# WHY THIS EXISTS
#   DSE/collect_capacity.py computes the on-chip footprint arithmetically
#   (K x D x X bits packed into 18 Kbit blocks) because Vitis csynth caps memory
#   inference on large arrays -- it reports 144 BRAM18K for a 40 MB codebook,
#   short by roughly 128x. Arithmetic is the correct method for a capacity
#   question, and it is how prior work reports model footprint (Hyle gives it as
#   an equation, not a synthesis result).
#
#   But nothing in a computed table shows a TOOL refusing to build. This script
#   supplies that: it pushes the first predicted failure through Vivado
#   synthesis and placement and records what the tool says. The claim then reads
#   "computed across the sweep, confirmed empirically at the boundary", which is
#   a much shorter argument to defend.
#
# WHICH POINT AND WHY
#   onchip, X=32, K=256 -- the first configuration the arithmetic says does not
#   fit, at 112.9% of U280 BRAM. Deliberately the MARGINAL case: a wildly
#   over-committed design failing proves little, whereas a design 13% over the
#   line is exactly where a reviewer would ask whether the estimate is real.
#
#   Override with HDC_CLIFF_PROJ to confirm a different point, e.g. the last
#   FITTING one (onchip_x32_k128) to show the tool succeeds just below the line.
#
# WHAT COUNTS AS CONFIRMATION
#   Either outcome is evidence, and both are recorded:
#     - synth_design completes and reports BRAM over 100%   -> over-utilisation
#     - place_design fails with insufficient resources      -> hard refusal
#   Vivado usually synthesises an over-committed design and only refuses during
#   placement, so placement is attempted explicitly rather than stopping at
#   synthesis.
# =============================================================================

proc envdef {name default} {
    if {[info exists ::env($name)]} {
        set v $::env($name)
        if {[string length [string trim $v]] > 0} { return $v }
    }
    return $default
}

set PROJ [envdef HDC_CLIFF_PROJ proj_cap_onchip_x32_k256]
set TOP  [envdef HDC_CLIFF_TOP  onchip_search_top]
set PART [envdef HDC_PART       xcu280-fsvh2892-2L-e]
set OUT  cliff_confirm_$PROJ

file mkdir $OUT

set RTL $PROJ/sol1/syn/verilog
if {![file isdirectory $RTL]} {
    puts "ERROR: no RTL at $RTL"
    puts "Run scripts/sweep_capacity.tcl first, or set HDC_CLIFF_PROJ."
    exit 1
}

puts "============================================================="
puts " capacity cliff confirmation"
puts "   project : $PROJ"
puts "   top     : $TOP"
puts "   part    : $PART"
puts "   rtl     : $RTL"
puts "============================================================="

create_project -in_memory -part $PART

set vfiles [glob -nocomplain $RTL/*.v]
set vhfiles [glob -nocomplain $RTL/*.vhd]
if {[llength $vfiles]}  { read_verilog $vfiles }
if {[llength $vhfiles]} { read_vhdl    $vhfiles }
puts "read [llength $vfiles] Verilog and [llength $vhfiles] VHDL file(s)"

# HLS emits .dat files for memory initialisation; make them findable.
set_property include_dirs $RTL [current_fileset]
set dats [glob -nocomplain $RTL/*.dat]
if {[llength $dats]} {
    add_files -norecurse $dats
    puts "added [llength $dats] memory-init .dat file(s)"
}

set SYNTH_OK 0
set PLACE_OK 0

puts "\n--------------------- synth_design ---------------------"
if {[catch {
    synth_design -top $TOP -part $PART -mode out_of_context
} err]} {
    puts "SYNTH FAILED: $err"
} else {
    set SYNTH_OK 1
    report_utilization -file $OUT/post_synth_utilization.rpt
    puts "synthesis completed -- utilisation written to $OUT/post_synth_utilization.rpt"
    puts "\n---- resource summary ----"
    report_utilization
}

if {$SYNTH_OK} {
    puts "\n--------------------- place_design ---------------------"
    puts "(an over-committed design is expected to be REFUSED here)"
    if {[catch {
        opt_design
        place_design -directive Quick
    } err]} {
        puts "PLACE FAILED: $err"
    } else {
        set PLACE_OK 1
        report_utilization -file $OUT/post_place_utilization.rpt
        puts "placement completed -- $OUT/post_place_utilization.rpt"
    }
}

puts ""
puts "============================================================="
puts " RESULT for $PROJ"
puts "   synth_design : [expr {$SYNTH_OK ? {completed} : {FAILED}}]"
puts "   place_design : [expr {$PLACE_OK ? {completed} : {FAILED / not run}}]"
puts ""
puts " If synthesis reports BRAM above 100%, or placement refuses for"
puts " insufficient resources, the computed cliff is confirmed on this part."
puts " Quote the BRAM line from $OUT/post_synth_utilization.rpt in the paper."
puts "============================================================="
exit