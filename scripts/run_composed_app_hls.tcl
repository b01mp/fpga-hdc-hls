# =============================================================================
# run_composed_app_hls.tcl
# C-simulate and C-synthesize one composed application top.
#
# Examples:
#   $env:HDC_APP='sequence'
#   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
#
#   $env:HDC_APP='train'
#   $env:HDC_CSIM_ONLY='1'
#   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
#
# Optional environment overrides:
#   HDC_APP        image | sequence | train       default image
#   HDC_PART       default xcu55c-fsvh2892-2L-e
#   HDC_CLOCK_NS   default 10
#   HDC_CSIM_ONLY  if 1, run csim only
#   HDC_SKIP_CSIM  if 1, skip csim and run csynth only
#   HDC_*_DP/CP    app-specific parallelism overrides, see CFLAGS below
# =============================================================================

set APP image
set PART xcu55c-fsvh2892-2L-e
set CLK  10

if {[info exists ::env(HDC_APP)] && $::env(HDC_APP) ne ""} {
    set APP $::env(HDC_APP)
}
if {[info exists ::env(HDC_PART)] && $::env(HDC_PART) ne ""} {
    set PART $::env(HDC_PART)
}
if {[info exists ::env(HDC_CLOCK_NS)] && $::env(HDC_CLOCK_NS) ne ""} {
    set CLK $::env(HDC_CLOCK_NS)
}

set CSIM_ONLY 0
set SKIP_CSIM 0
if {[info exists ::env(HDC_CSIM_ONLY)] && $::env(HDC_CSIM_ONLY) ne ""} {
    set CSIM_ONLY $::env(HDC_CSIM_ONLY)
}
if {[info exists ::env(HDC_SKIP_CSIM)] && $::env(HDC_SKIP_CSIM) ne ""} {
    set SKIP_CSIM $::env(HDC_SKIP_CSIM)
}

set CFLAGS "-I./include"

if {$APP eq "image"} {
    set PROJECT proj_app_image
    set TOP image_classification_top
    set SRC src/top_application.cpp
    set TB tb/tb_application.cpp
    if {[info exists ::env(HDC_APP_DP)] && $::env(HDC_APP_DP) ne ""} {
        append CFLAGS " -DAPP_DP=$::env(HDC_APP_DP)"
    }
    if {[info exists ::env(HDC_APP_CP)] && $::env(HDC_APP_CP) ne ""} {
        append CFLAGS " -DAPP_CP=$::env(HDC_APP_CP)"
    }
} elseif {$APP eq "sequence"} {
    set PROJECT proj_app_sequence
    set TOP sequence_classification_top
    set SRC src/top_sequence.cpp
    set TB tb/tb_sequence.cpp
    if {[info exists ::env(HDC_SEQ_DP)] && $::env(HDC_SEQ_DP) ne ""} {
        append CFLAGS " -DSEQ_DP=$::env(HDC_SEQ_DP)"
    }
    if {[info exists ::env(HDC_SEQ_CP)] && $::env(HDC_SEQ_CP) ne ""} {
        append CFLAGS " -DSEQ_CP=$::env(HDC_SEQ_CP)"
    }
} elseif {$APP eq "train"} {
    set PROJECT proj_app_train
    set TOP train_infer_top
    set SRC src/top_train.cpp
    set TB tb/tb_train.cpp
    if {[info exists ::env(HDC_TRAIN_DP)] && $::env(HDC_TRAIN_DP) ne ""} {
        append CFLAGS " -DTRAIN_DP=$::env(HDC_TRAIN_DP)"
    }
    if {[info exists ::env(HDC_TRAIN_CP)] && $::env(HDC_TRAIN_CP) ne ""} {
        append CFLAGS " -DTRAIN_CP=$::env(HDC_TRAIN_CP)"
    }
} else {
    error "Unknown HDC_APP '$APP'. Use image, sequence, or train."
}

puts "Composed app: $APP"
puts "Project: $PROJECT"
puts "Top: $TOP"
puts "Target part: $PART"
puts "Clock: $CLK ns"
puts "CFLAGS: $CFLAGS"

open_project -reset $PROJECT
set_top $TOP

add_files $SRC -cflags $CFLAGS
add_files -tb $TB -cflags $CFLAGS

open_solution -reset sol1
set_part $PART
create_clock -period $CLK -name default

if {!$SKIP_CSIM} {
    puts "==================== composed app C simulation ===================="
    csim_design
}

if {!$CSIM_ONLY} {
    puts "==================== composed app C synthesis ====================="
    csynth_design
    puts "Report: $PROJECT/sol1/syn/report/${TOP}_csynth.rpt"
}

puts "Composed app validation complete."

close_project
exit
