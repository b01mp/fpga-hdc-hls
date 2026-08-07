"""
collect_capacity.py -- gather the on-chip / off-chip CAPACITY CROSSOVER sweep.

Run AFTER scripts/sweep_capacity.tcl:
    cd ~/fpga-hdc-hls
    python3 DSE/collect_capacity.py

Reads:  proj_cap_<tier>_x<X>_k<K>/sol1/syn/report/*_csynth.rpt
Writes: DSE/synth_results/capacity_sweep.csv

WHY THE FIT CHECK LIVES HERE, NOT IN THE TCL
    Vitis csynth does NOT fail when a design exceeds device resources -- it
    reports 400% BRAM and exits cleanly. "Does not fit" is therefore something
    the collector has to compute, by comparing usage against the device totals.
    Without it the crossover plot is unreadable: the on-chip line would appear
    to continue past the point where the design cannot be built.

WHAT THE CROSSOVER SHOWS
    The on-chip design is what prior FPGA-HDC frameworks are (Hyle says so
    explicitly: hypervectors in BRAM, single-cycle access, so memory never
    enters the measurement). Growing the reference library eventually exceeds
    on-chip capacity and that design stops existing. The streaming design does
    not. The cliff location is set by PRECISION, not by the application.

A CAVEAT THAT MUST TRAVEL WITH ANY LATENCY NUMBER FROM THIS TABLE
    csynth models an m_axi port optimistically: it schedules a pipelined read at
    II=1 and assumes the word arrives. It does not model DRAM latency, bandwidth
    or contention. So on-chip and off-chip CYCLE counts here are comparable as
    SCHEDULES, not as achieved performance. The columns are reported because the
    schedule comparison is itself meaningful -- it shows the streaming design
    recovers the on-chip initiation interval -- but any wall-clock claim needs
    an off-chip bandwidth term this script deliberately does not invent.
"""
import os
import re
import csv
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

D_DIM = 10240        # held constant by the sweep
QB    = 4
WBITS = 512

# Device totals. Add an entry when retargeting; the fit check needs all of them.
DEVICES = {
    "xcu280-fsvh2892-2L-e": {"LUT": 1303680, "FF": 2607360, "DSP": 9024,
                             "BRAM18K": 4032, "URAM": 960},
    "xczu7ev-ffvc1156-2-e": {"LUT": 230400, "FF": 460800, "DSP": 1728,
                             "BRAM18K": 624, "URAM": 96},
    "xc7z020clg484-1":      {"LUT": 53200, "FF": 106400, "DSP": 220,
                             "BRAM18K": 280, "URAM": 0},
}
RESOURCES = ("LUT", "FF", "DSP", "BRAM18K", "URAM")

# --- Off-chip bandwidth ceiling, per m_axi port ------------------------------
# csynth schedules an m_axi read at II=1 and assumes the word arrives. It models
# no DRAM latency, no bandwidth limit and no contention, so its cycle count for
# the streaming design is a SCHEDULE, not an achievable rate. Without a ceiling
# the on-chip and off-chip designs come out within 10 cycles of each other at
# every point, which is an artefact of that assumption rather than a result.
#
# U280 carries HBM2 as 32 pseudo-channels, ~460 GB/s aggregate, i.e. ~14.4 GB/s
# each -- the PC's AXI interface is 256-bit at 450 MHz. A 512-bit user port at
# 300 MHz DEMANDS 19.2 GB/s, so SmartConnect width-converts and the sustained
# rate is bounded by the pseudo-channel, not by the port. One port per channel
# is what this sweep instantiates (CP=1).
#
# This is a MODEL, not a measurement. It assumes perfectly sequential, fully
# utilised bursts -- which the design does issue (contiguous, port-width
# aligned) -- so it is an upper bound on delivered bandwidth and therefore a
# LOWER bound on off-chip time. Board measurement would only move it down.
DEVICE_BW_GBPS_PER_PORT = {
    "xcu280-fsvh2892-2L-e": 14.4,    # one HBM2 pseudo-channel
    "xczu7ev-ffvc1156-2-e": 19.2,    # single DDR4 controller, shared by all ports
    "xc7z020clg484-1":       4.2,    # single DDR3 controller
}
TARGET_MHZ = 300.0

DIRPAT = re.compile(r"proj_cap_(onchip|offchip)_x(\d+)_k(\d+)$")

# Each project holds one report per generated sub-module PLUS the top-level one.
# A bare "*_csynth.rpt" glob picks whichever sorts first -- usually an inner
# pipeline region, whose latency and resources describe a loop body rather than
# the design. Always resolve the top by name first.
TOPNAME = {"onchip": "onchip_search_top", "offchip": "compose_biohd_top"}

# --- On-chip footprint is ARITHMETIC, not something synthesis discovers. ------
# Vitis under-reports BRAM for very large arrays: the X=32 K=1024 design holds a
# 40 MB codebook and csynth reports 144 BRAM18K (~331 KB), roughly 128x short.
# It caps memory inference rather than reporting the true requirement, so the
# reported figure cannot carry this experiment. The requirement is computed here
# instead, and the reported figure is kept alongside it so the gap is visible.
#
# A BRAM18K holds 18,432 bits, usable as 1024 x 18. A W-bit wide, N-deep memory
# therefore needs ceil(W/18) blocks per 1024 entries.
BRAM18K_BITS = 18 * 1024
URAM_BITS    = 288 * 1024


def bram18k_required(total_words, word_bits):
    import math
    per_row = int(math.ceil(word_bits / 18.0))
    rows    = int(math.ceil(total_words / 1024.0))
    return per_row * rows


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {k: None for k in ("BRAM18K", "DSP", "FF", "LUT", "URAM",
                             "latency_cycles", "interval",
                             "target_ns", "estimated_ns", "tool_version", "part")}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|"
                  r"\s*[\d.]+\s*[num]s\|\s*[\d.]+\s*[num]s\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|",
                  t, re.S)
    if m:
        out["latency_cycles"] = int(m.group(2).replace(",", ""))
        out["interval"] = int(m.group(4).replace(",", ""))
    m = re.search(r"\|\s*ap_clk\s*\|\s*([\d.]+)\s*ns\s*\|\s*([\d.]+)\s*ns", t)
    if m:
        out["target_ns"] = float(m.group(1))
        out["estimated_ns"] = float(m.group(2))
    m = re.search(r"^\*\s*Version:\s*(\S+)", t, re.M)
    if m:
        out["tool_version"] = m.group(1)
    m = re.search(r"^\*\s*Target device:\s*(\S+)", t, re.M)
    if m:
        out["part"] = m.group(1)
    return out


COLS = ["tier", "X", "K", "D", "QB",
        "model_bits", "model_MB",
        "bram18k_required", "bram_capacity_pct", "onchip_capacity_pct",
        "fits_bram", "fits_bram_uram",
        "bytes_fetched", "bw_GBps_available", "bw_bound_cycles",
        "effective_cycles", "bw_limited",
        "latency_cycles", "interval", "estimated_ns", "fmax_MHz",
        "LUT", "LUT_pct", "FF", "FF_pct", "DSP", "DSP_pct",
        "BRAM18K_reported", "URAM_reported",
        "part", "tool_version", "status"]


def main():
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, "proj_cap_*"))):
        m = DIRPAT.search(os.path.basename(d))
        if not m:
            continue
        tier, x, k = m.group(1), int(m.group(2)), int(m.group(3))

        model_bits = k * D_DIM * x
        base = dict(tier=tier, X=x, K=k, D=D_DIM, QB=QB,
                    model_bits=model_bits,
                    model_MB=round(model_bits / 8.0 / 1024.0 / 1024.0, 3))

        # The on-chip design must hold the whole codebook; the streaming design
        # holds only a FIFO's worth, so the footprint constraint is on-chip only.
        if tier == "onchip":
            total_words = k * ((D_DIM * x) // WBITS)
            base["bram18k_required"] = bram18k_required(total_words, WBITS)
        else:
            base["bram18k_required"] = 0

        rpts = (glob.glob(os.path.join(d, "sol1", "syn", "report",
                                       TOPNAME[tier] + "_csynth.rpt"))
                or glob.glob(os.path.join(d, "sol1", "syn", "report", "*_csynth.rpt")))
        if not rpts:
            base.update(status="FAILED / no report", fits_bram="?", fits_bram_uram="?")
            rows.append(base)
            continue

        r = parse_report(rpts[0])
        r.update(base)
        r["BRAM18K_reported"] = r.get("BRAM18K")
        r["URAM_reported"]    = r.get("URAM")
        est = r.get("estimated_ns")
        r["fmax_MHz"] = round(1000.0 / est, 1) if est else None

        dev = DEVICES.get(r.get("part"))
        if dev:
            for res in ("LUT", "FF", "DSP"):
                used, avail = r.get(res), dev[res]
                r[res + "_pct"] = (round(100.0 * used / avail, 2)
                                   if (used is not None and avail) else None)
            bram_cap = dev["BRAM18K"] * BRAM18K_BITS
            onchip_cap = bram_cap + dev["URAM"] * URAM_BITS
            r["bram_capacity_pct"]   = round(100.0 * model_bits / bram_cap, 1)
            r["onchip_capacity_pct"] = round(100.0 * model_bits / onchip_cap, 1)
            if tier == "onchip":
                r["fits_bram"]      = "yes" if model_bits <= bram_cap else "no"
                r["fits_bram_uram"] = "yes" if model_bits <= onchip_cap else "no"
            else:
                r["fits_bram"] = r["fits_bram_uram"] = "n/a"
        else:
            r["fits_bram"] = r["fits_bram_uram"] = "?"

        # --- off-chip bandwidth ceiling ---------------------------------------
        # The on-chip design reads BRAM at the rate its schedule assumes, so its
        # csynth cycles stand. The streaming design must actually pull the whole
        # library across a memory port, so its time is bounded below by
        # bytes / delivered_bandwidth.
        cyc = r.get("latency_cycles")
        if tier == "offchip":
            bw = DEVICE_BW_GBPS_PER_PORT.get(r.get("part"))
            nbytes = model_bits // 8
            r["bytes_fetched"] = nbytes
            r["bw_GBps_available"] = bw
            if bw:
                bw_cycles = int(round(nbytes / (bw * 1e9) * TARGET_MHZ * 1e6))
                r["bw_bound_cycles"] = bw_cycles
                r["effective_cycles"] = max(cyc, bw_cycles) if cyc else bw_cycles
                r["bw_limited"] = "yes" if (cyc and bw_cycles > cyc) else "no"
        else:
            r["bytes_fetched"] = 0
            r["effective_cycles"] = cyc
            r["bw_limited"] = "n/a"

        r["status"] = "ok"
        rows.append(r)

    rows.sort(key=lambda r: (r.get("X", 0), r.get("tier", ""), r.get("K", 0)))

    out_csv = os.path.join(ROOT, "DSE", "synth_results", "capacity_sweep.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    print("wrote", out_csv, "\n")

    hdr = ("%-9s%4s%7s%10s%11s%10s%7s%12s%12s%8s%9s" %
           ("tier", "X", "K", "model_MB", "BRAM_req", "BRAM_cap%", "fits",
            "sched_cyc", "eff_cyc", "bw_lim", "BRAM_rpt"))
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print("%-9s%4s%7s%10s%11s%10s%7s%12s%12s%8s%9s" % (
            r.get("tier", ""), r.get("X", ""), r.get("K", ""),
            r.get("model_MB", ""), r.get("bram18k_required", "-"),
            r.get("bram_capacity_pct", "-"), r.get("fits_bram", "?"),
            r.get("latency_cycles", "-"), r.get("effective_cycles", "-"),
            r.get("bw_limited", "-"), r.get("BRAM18K_reported", "-")))

    # side-by-side at each point where BOTH tiers are buildable
    print("\nON-CHIP vs STREAMING, where both exist (effective cycles):")
    print("  %-4s%7s%14s%14s%9s" % ("X", "K", "on-chip", "streaming", "ratio"))
    for x in sorted({r["X"] for r in rows if "X" in r}):
        for k in sorted({r["K"] for r in rows if r.get("X") == x and "K" in r}):
            on = next((r for r in rows if r.get("tier") == "onchip"
                       and r.get("X") == x and r.get("K") == k), None)
            off = next((r for r in rows if r.get("tier") == "offchip"
                        and r.get("X") == x and r.get("K") == k), None)
            if not on or not off or on.get("fits_bram") != "yes":
                continue
            a, b = on.get("effective_cycles"), off.get("effective_cycles")
            if a and b:
                print("  %-4s%7s%14s%14s%9s" % (x, k, a, b, round(float(b) / a, 2)))

    # the headline: where each precision's on-chip design stops fitting
    print("\nON-CHIP CAPACITY CLIFF (BRAM only), per precision:")
    for x in sorted({r["X"] for r in rows if r.get("tier") == "onchip" and "X" in r}):
        fit = [r["K"] for r in rows if r.get("tier") == "onchip"
               and r.get("X") == x and r.get("fits_bram") == "yes"]
        bad = [r["K"] for r in rows if r.get("tier") == "onchip"
               and r.get("X") == x and r.get("fits_bram") == "no"]
        print("  X=%-3d  fits up to K=%-6s  first failure at K=%s"
              % (x, max(fit) if fit else "none",
                 min(bad) if bad else "never in this sweep"))
    print("\n(The off-chip streaming design holds only a FIFO's worth of the")
    print(" library on chip, so it has no capacity limit at any K.)")
    print("\nBRAM_rpt is what csynth INFERRED. It under-reports badly for large")
    print("arrays -- Vitis caps memory inference rather than reporting the true")
    print("requirement -- so BRAM_req (K x D x X packed into 18Kb blocks) is the")
    print("number the cliff is drawn from. The two are shown side by side so the")
    print("discrepancy is visible rather than hidden.")

    vers = sorted({r.get("tool_version") for r in rows if r.get("tool_version")})
    parts = sorted({r.get("part") for r in rows if r.get("part")})
    print("\npart(s): %s    Vitis: %s" % (", ".join(parts) or "?", ", ".join(vers) or "?"))
    if len(vers) > 1 or len(parts) > 1:
        print("WARNING: this table mixes parts or tool versions -- not comparable.")
    print("\nsched_cyc is the raw csynth schedule, which assumes an m_axi read")
    print("always returns in one cycle. eff_cyc applies the memory ceiling:")
    print("for the streaming design, max(schedule, bytes / delivered bandwidth)")
    print("at %g GB/s per port on the U280 (one HBM2 pseudo-channel). The on-chip"
          % DEVICE_BW_GBPS_PER_PORT.get("xcu280-fsvh2892-2L-e", 0))
    print("design reads BRAM at its scheduled rate, so its schedule stands.")
    print("The ceiling is a MODEL assuming perfectly sequential, fully utilised")
    print("bursts -- an upper bound on bandwidth, so a LOWER bound on off-chip")
    print("time. A board measurement could only move it the other way.")


if __name__ == "__main__":
    main()