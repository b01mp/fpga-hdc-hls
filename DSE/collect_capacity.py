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

DIRPAT = re.compile(r"proj_cap_(onchip|offchip)_x(\d+)_k(\d+)$")


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
        "latency_cycles", "interval", "estimated_ns", "fmax_MHz",
        "LUT", "LUT_pct", "FF", "FF_pct", "DSP", "DSP_pct",
        "BRAM18K", "BRAM18K_pct", "URAM", "URAM_pct",
        "fits", "limiting_resource", "part", "tool_version", "status"]


def main():
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, "proj_cap_*"))):
        m = DIRPAT.search(os.path.basename(d))
        if not m:
            continue
        tier, x, k = m.group(1), int(m.group(2)), int(m.group(3))
        rpts = glob.glob(os.path.join(d, "sol1", "syn", "report", "*_csynth.rpt"))
        base = dict(tier=tier, X=x, K=k, D=D_DIM, QB=QB,
                    model_bits=k * D_DIM * x,
                    model_MB=round(k * D_DIM * x / 8.0 / 1024.0 / 1024.0, 3))
        if not rpts:
            base.update(status="FAILED / no report", fits="?")
            rows.append(base)
            continue

        r = parse_report(rpts[0])
        r.update(base)
        est = r.get("estimated_ns")
        r["fmax_MHz"] = round(1000.0 / est, 1) if est else None

        dev = DEVICES.get(r.get("part"))
        if dev:
            over = []
            for res in RESOURCES:
                used, avail = r.get(res), dev[res]
                r[res + "_pct"] = (round(100.0 * used / avail, 2)
                                   if (used is not None and avail) else None)
                if used is not None and avail and used > avail:
                    over.append("%s %d/%d" % (res, used, avail))
            r["fits"] = "no" if over else "yes"
            r["limiting_resource"] = "; ".join(over)
        else:
            r["fits"] = "?"
            r["limiting_resource"] = "unknown part '%s'" % r.get("part")
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

    hdr = ("%-9s%5s%7s%10s%12s%9s%9s%8s%7s  %s" %
           ("tier", "X", "K", "model_MB", "lat_cyc", "BRAM", "BRAM%", "fmax", "fits",
            "limiting resource"))
    print(hdr); print("-" * (len(hdr) + 20))
    for r in rows:
        print("%-9s%5s%7s%10s%12s%9s%9s%8s%7s  %s" % (
            r.get("tier", ""), r.get("X", ""), r.get("K", ""),
            r.get("model_MB", ""), r.get("latency_cycles", "-"),
            r.get("BRAM18K", "-"), r.get("BRAM18K_pct", "-"),
            r.get("fmax_MHz", "-"), r.get("fits", "?"),
            r.get("limiting_resource", "")))

    # the headline: where each precision's on-chip design stops fitting
    print("\nON-CHIP CAPACITY CLIFF (largest K that fits, per precision):")
    for x in sorted({r["X"] for r in rows if r.get("tier") == "onchip" and "X" in r}):
        fitting = [r["K"] for r in rows
                   if r.get("tier") == "onchip" and r.get("X") == x and r.get("fits") == "yes"]
        failing = [r["K"] for r in rows
                   if r.get("tier") == "onchip" and r.get("X") == x and r.get("fits") == "no"]
        top = max(fitting) if fitting else None
        first_fail = min(failing) if failing else None
        print("  X=%-3d  fits up to K=%-6s  first failure at K=%s"
              % (x, top if top else "none", first_fail if first_fail else "never in sweep"))

    vers = sorted({r.get("tool_version") for r in rows if r.get("tool_version")})
    parts = sorted({r.get("part") for r in rows if r.get("part")})
    print("\npart(s): %s    Vitis: %s" % (", ".join(parts) or "?", ", ".join(vers) or "?"))
    if len(vers) > 1 or len(parts) > 1:
        print("WARNING: this table mixes parts or tool versions -- not comparable.")
    print("\nCAVEAT: csynth models m_axi optimistically (II=1, no DRAM latency or")
    print("bandwidth limit). On-chip vs off-chip cycle counts compare SCHEDULES,")
    print("not achieved wall-clock. Do not quote them as a speedup without an")
    print("off-chip bandwidth term.")


if __name__ == "__main__":
    main()
