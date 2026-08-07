# =============================================================================
# run_composed_app_hls.tcl
# C-simulate and C-synthesize one composed application top.
#
# Examples:
#   $env:HDC_APP='time_series'
#   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
#
#   $env:HDC_APP='genome'
#   $env:HDC_CSIM_ONLY='1'
#   vitis-run --mode hls --tcl scripts/run_composed_app_hls.tcl
#
# Optional environment overrides:
#   HDC_APP        image | time_series | genome   default image
#   HDC_PART       default xcu55c-fsvh2892-2L-e
#   HDC_CLOCK_NS   default 10
#   HDC_CSIM_ONLY  if 1, run csim only
#   HDC_SKIP_CSIM  if 1, skip csim and run csynth only
#   HDC_CONFIG_NAME optional suffix for keeping per-config projects separate
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
set CONFIG_NAME ""
if {[info exists ::env(HDC_CONFIG_NAME)] && $::env(HDC_CONFIG_NAME) ne ""} {
    set CONFIG_NAME $::env(HDC_CONFIG_NAME)
}

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
    error "HDC_APP='sequence' has been renamed to 'time_series'."
} elseif {$APP eq "time_series"} {
    set PROJECT proj_app_time_series
    set TOP time_series_classification_top
    set SRC src/top_time_series.cpp
    set TB tb/tb_time_series.cpp
    if {[info exists ::env(HDC_TS_DP)] && $::env(HDC_TS_DP) ne ""} {
        append CFLAGS " -DTS_DP=$::env(HDC_TS_DP)"
    }
    if {[info exists ::env(HDC_TS_CP)] && $::env(HDC_TS_CP) ne ""} {
        append CFLAGS " -DTS_CP=$::env(HDC_TS_CP)"
    }
} elseif {$APP eq "train"} {
    error "HDC_APP='train' is not one of the paper applications."
} elseif {$APP eq "genome"} {
    set PROJECT proj_app_genome
    set TOP genome_sequence_search_top
    set SRC src/top_genome.cpp
    set TB tb/tb_genome.cpp
    if {[info exists ::env(HDC_GEN_DP)] && $::env(HDC_GEN_DP) ne ""} {
        append CFLAGS " -DGEN_DP=$::env(HDC_GEN_DP)"
    }
    if {[info exists ::env(HDC_GEN_CP)] && $::env(HDC_GEN_CP) ne ""} {
        append CFLAGS " -DGEN_CP=$::env(HDC_GEN_CP)"
    }
} else {
    error "Unknown HDC_APP '$APP'. Use image, time_series, or genome."
}

if {$CONFIG_NAME ne ""} {
    append PROJECT "_$CONFIG_NAME"
}

puts "Composed app: $APP"
puts "Config: $CONFIG_NAME"
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
