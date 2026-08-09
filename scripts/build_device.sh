#!/usr/bin/env bash
# =============================================================================
# build_device.sh -- build the off-chip memory study for the U280 card.
#
#   Both designs, all CP points, one target:
#       source /tools/Xilinx/Vitis/2022.2/settings64.sh
#       source /opt/xilinx/xrt/setup.sh
#       cd ~/fpga-hdc-hls
#       TARGET=sw_emu bash scripts/build_device.sh all      # seconds
#       TARGET=hw_emu bash scripts/build_device.sh all      # ~30 min
#       TARGET=hw     PAR=3 bash scripts/build_device.sh all  # hours
#
#   Just the host:            bash scripts/build_device.sh host
#   One point:                TARGET=hw DESIGNS=stream CPS=8 bash scripts/build_device.sh kernels
#
# Vitis 2022.2 is used deliberately, not 2023.1: the installed U280 platform is
# 202211_1 and XRT is 2.14.354, both 2022.2-era. Matching all three avoids
# link-stage version errors. The HLS csynth studies stay on 2023.1; the two
# never share artifacts.
#
# CP is the only structural knob -- it sets the number of m_axi ports, so each
# CP needs its own xclbin. Class count and bits-per-element are swept at
# runtime by the host, because the gather datapath never interprets an element.
# =============================================================================
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TARGET=${TARGET:-hw}                 # sw_emu | hw_emu | hw
CPS=${CPS:-"1 2 4 8"}
DESIGNS=${DESIGNS:-"buffer stream"}
PAR=${PAR:-1}                        # concurrent v++ builds
JOBS=${JOBS:-8}                      # cores per v++ build
PLATFORM=${PLATFORM:-/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm}

BUILD="$ROOT/build/$TARGET"
CFGDIR="$ROOT/build/cfg"
LOGDIR="$ROOT/build/logs"
mkdir -p "$BUILD" "$CFGDIR" "$LOGDIR" "$ROOT/results"

command -v v++ >/dev/null || { echo "v++ not on PATH -- source settings64.sh"; exit 1; }
[ -n "${XILINX_XRT:-}" ] || { echo "XILINX_XRT unset -- source /opt/xilinx/xrt/setup.sh"; exit 1; }
[ -f "$PLATFORM" ] || { echo "platform not found: $PLATFORM"; exit 1; }

kernel_of() { if [ "$1" = stream ]; then echo krnl_hdc_stream; else echo krnl_hdc_buffer; fi; }
src_of()    { if [ "$1" = stream ]; then echo src/krnl_hdc_stream.cpp; else echo src/krnl_hdc_buffer.cpp; fi; }

# ---------------------------------------------------------------- connectivity
# Each bank gets its OWN HBM pseudo-channel, and master i is placed on PC i so
# it talks to the controller nearest it across the segmented AXI switch.
# Without this every port defaults onto HBM[0] and all channel parallelism
# collapses into a single controller -- which would silently destroy the
# entire experiment.
gen_cfg() {
    local kname=$1 cp=$2 out=$3 i
    {
        echo "[connectivity]"
        echo "nk=${kname}:1:${kname}_1"
        for ((i = 0; i < cp; i++)); do
            echo "sp=${kname}_1.bank${i}:HBM[${i}]"
        done
        echo "sp=${kname}_1.out:HBM[31]"
        echo
        echo "[clock]"
        echo "freqHz=300000000:${kname}_1"
        echo
        echo "[vivado]"
        echo "synth.jobs=${JOBS}"
        echo "impl.jobs=${JOBS}"
        echo "prop=run.impl_1.STEPS.PHYS_OPT_DESIGN.IS_ENABLED=true"
    } > "$out"
}

# v++ deprecated --jobs on the command line; it now wants it in a config file.
gen_compile_cfg() {
    printf '[hls]\njobs=%s\n' "$JOBS" > "$1"
}

build_host() {
    echo "=== host ==="
    g++ -std=c++17 -O2 -Wall \
        -I"$XILINX_XRT/include" \
        "$ROOT/host/hdc_mem_host.cpp" \
        -L"$XILINX_XRT/lib" -lxrt_coreutil -lpthread \
        -o "$ROOT/build/hdc_mem_host"
    echo "built build/hdc_mem_host"
}

build_one() {
    local d=$1 cp=$2
    local kname; kname=$(kernel_of "$d")
    local src;   src=$(src_of "$d")
    local tag="${d}_cp${cp}"
    local cfg="$CFGDIR/${TARGET}_${tag}.cfg"
    local ccfg="$CFGDIR/${TARGET}_${tag}_compile.cfg"
    local log="$LOGDIR/${TARGET}_${tag}.log"
    gen_cfg "$kname" "$cp" "$cfg"
    gen_compile_cfg "$ccfg"

    {
        echo "### compile $tag ($TARGET) $(date)"
        v++ -c -t "$TARGET" --platform "$PLATFORM" -k "$kname" \
            -D HBM_CP="$cp" -D HBM_WBITS=512 \
            -I "$ROOT/include" \
            --config "$ccfg" \
            --temp_dir "$BUILD/_x_${tag}" \
            -o "$BUILD/${tag}.xo" "$ROOT/$src"

        echo "### link $tag ($TARGET) $(date)"
        v++ -l -t "$TARGET" --platform "$PLATFORM" \
            --config "$cfg" \
            --report_level 2 \
            --temp_dir "$BUILD/_x_${tag}" \
            -o "$BUILD/${tag}.xclbin" "$BUILD/${tag}.xo"
        echo "### done $tag $(date)"
    } > "$log" 2>&1

    echo "  finished $tag -> $BUILD/${tag}.xclbin"
}

build_kernels() {
    if [ "$TARGET" = sw_emu ] || [ "$TARGET" = hw_emu ]; then
        emconfigutil --platform "$PLATFORM" --nd 1 --od "$ROOT/build" >/dev/null
        echo "wrote build/emconfig.json"
    fi
    local running=0
    for d in $DESIGNS; do
        for cp in $CPS; do
            echo "starting ${d}_cp${cp} ($TARGET), log build/logs/${TARGET}_${d}_cp${cp}.log"
            build_one "$d" "$cp" &
            running=$((running + 1))
            if [ "$running" -ge "$PAR" ]; then wait -n || true; running=$((running - 1)); fi
        done
    done
    wait
    echo "all builds complete"
    ls -la "$BUILD"/*.xclbin 2>/dev/null || echo "NO XCLBINS -- check build/logs/"
}

case "${1:-all}" in
    host)    build_host ;;
    kernels) build_kernels ;;
    all)     build_host; build_kernels ;;
    *)       echo "usage: $0 [host|kernels|all]"; exit 2 ;;
esac
