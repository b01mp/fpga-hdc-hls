#!/usr/bin/env bash
# =============================================================================
# run_device.sh -- run the host across every built xclbin and collect timings.
#
#   source /tools/Xilinx/Vitis/2022.2/settings64.sh
#   source /opt/xilinx/xrt/setup.sh
#   cd ~/fpga-hdc-hls
#
#   TARGET=sw_emu bash scripts/run_device.sh      # correctness gate, seconds
#   TARGET=hw_emu bash scripts/run_device.sh      # correctness gate, minutes
#   TARGET=hw     bash scripts/run_device.sh      # the real numbers
#
# One CSV per (design, CP) in results/. Each sweeps bits x K at runtime, so a
# single hardware build yields 15 measured points in a few seconds.
#
# The machine has two Alveo cards. BDF is pinned to the U280 by default --
# selecting by index would be a coin flip between it and the U200.
# =============================================================================
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TARGET=${TARGET:-hw}
CPS=${CPS:-"1 2 4 8"}
DESIGNS=${DESIGNS:-"buffer stream"}
BDF=${BDF:-0000:3b:00.1}
ITERS=${ITERS:-10}

BUILD="$ROOT/build/$TARGET"
RES="$ROOT/results/$TARGET"
mkdir -p "$RES"

[ -x "$ROOT/build/hdc_mem_host" ] || { echo "host not built: bash scripts/build_device.sh host"; exit 1; }

if [ "$TARGET" = sw_emu ] || [ "$TARGET" = hw_emu ]; then
    export XCL_EMULATION_MODE=$TARGET
    export EMCONFIG_PATH="$ROOT/build"
    echo "emulation mode: $TARGET"
else
    unset XCL_EMULATION_MODE || true
    echo "hardware mode on $BDF"
fi

kernel_of() { if [ "$1" = stream ]; then echo krnl_hdc_stream; else echo krnl_hdc_buffer; fi; }

for d in $DESIGNS; do
    for cp in $CPS; do
        xcl="$BUILD/${d}_cp${cp}.xclbin"
        if [ ! -f "$xcl" ]; then echo "skip ${d}_cp${cp}: no xclbin"; continue; fi
        echo
        echo "================ ${d} CP=${cp} ================"
        "$ROOT/build/hdc_mem_host" \
            --xclbin "$xcl" \
            --kernel "$(kernel_of "$d")" \
            --cp "$cp" \
            --design "$d" \
            --bdf "$BDF" \
            --iters "$ITERS" \
            --out "$RES/${d}_cp${cp}.csv"
    done
done

echo
echo "CSVs in $RES"
echo "next: python3 DSE/collect_device.py --target $TARGET"
