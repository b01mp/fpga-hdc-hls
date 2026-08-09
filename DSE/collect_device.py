"""
collect_device.py -- join the measured device timings with the post-route
resource numbers from the same builds, and emit the Pareto.

    cd ~/fpga-hdc-hls
    python3 DSE/collect_device.py --target hw

Reads   results/<target>/<design>_cp<N>.csv     measured on the card
        build/<target>/_x_<design>_cp<N>/...    Vivado utilisation reports
Writes  DSE/synth_results/device_memory.csv     the joined table
        DSE/synth_results/device_pareto.csv     one row per (design, CP)

WHY THIS IS THE TABLE THAT MATTERS
    Every previous number in this study came from csynth, which models DRAM as
    a zero-latency SRAM. That is why CP scaling looked perfectly linear and why
    the overlap ratio was pinned at the pipeline fill/drain bound: there was no
    memory system in the experiment. These numbers come from an actual U280
    with actual HBM controllers, so latency, bandwidth and throughput mean what
    they say. Resource counts still come from the tools -- but post-route, not
    estimated.

WHAT THE COLUMNS MEAN
    latency        wall-clock kernel time, median of N runs, microseconds
    bw_GBps        bytes that crossed the HBM interface / latency
    throughput     prototypes consumed per second
    LUT / BRAM     post-route, kernel-only where the kernel report exists,
                   otherwise whole-design (shell included) -- the row says which
"""
import os
import re
import csv
import glob
import argparse
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")

# On-chip capacity of the U280, for the "could this have stayed on chip?" line.
BRAM18K_TOTAL = 4032
BRAM_BYTES = BRAM18K_TOTAL * 18432 / 8.0            # ~9.29 MB
URAM_BYTES = 960 * 288 * 1024 / 8.0                 # ~34.6 MB
ONCHIP_BYTES = BRAM_BYTES + URAM_BYTES              # ~43.9 MB


def find_util(target, design, cp):
    """Locate a Vivado utilisation report for one build.

    Prefers the kernel-only report when v++ produced one, because the
    whole-design report includes the static shell, which is identical across
    all our builds and would dilute every comparison.
    """
    tag = "{}_cp{}".format(design, cp)
    base = os.path.join(ROOT, "build", target, "_x_" + tag)
    preferred = [
        "**/reports/link/imp/kernel_util_routed.rpt",
        "**/kernel_util_routed.rpt",
        "**/reports/link/imp/impl_1_full_util_routed.rpt",
        "**/*util*routed*.rpt",
        "**/*utilization*placed*.rpt",
    ]
    for pat in preferred:
        hits = sorted(glob.glob(os.path.join(base, pat), recursive=True))
        if hits:
            scope = "kernel" if "kernel_util" in hits[0] else "full_design"
            return hits[0], scope
    return None, None


def parse_util(path):
    """Pull resource rows out of a Vivado utilisation report."""
    txt = open(path, "r", errors="ignore").read()
    out = {}

    def first(label):
        m = re.search(r"\|\s*" + label + r"\s*\|\s*(\d+)\s*\|", txt)
        return int(m.group(1)) if m else None

    out["LUT"] = first(r"CLB LUTs\*?") or first(r"Slice LUTs\*?")
    out["FF"] = first(r"CLB Registers") or first(r"Slice Registers")
    out["BRAM_tiles"] = first(r"Block RAM Tile")
    out["RAMB36"] = first(r"RAMB36/FIFO\*?")
    out["RAMB18"] = first(r"RAMB18")
    out["URAM"] = first(r"URAM") or first(r"RAMB(?:36|18)E2")
    out["DSP"] = first(r"DSPs?")
    if out["RAMB18"] is not None and out["RAMB36"] is not None:
        out["BRAM18K"] = out["RAMB18"] + 2 * out["RAMB36"]
    else:
        out["BRAM18K"] = None
    return out


def num(x, cast=float):
    try:
        return cast(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="hw")
    args = ap.parse_args()
    target = args.target

    resdir = os.path.join(ROOT, "results", target)
    files = sorted(glob.glob(os.path.join(resdir, "*_cp*.csv")))
    if not files:
        raise SystemExit("no result CSVs in {} -- run scripts/run_device.sh first"
                         .format(resdir))

    util_cache = {}
    rows = []
    for f in files:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                design, cp = r["design"], int(r["CP"])
                key = (design, cp)
                if key not in util_cache:
                    p, scope = find_util(target, design, cp)
                    util_cache[key] = (parse_util(p) if p else {}, scope)
                u, scope = util_cache[key]
                rows.append(OrderedDict([
                    ("design", design), ("CP", cp),
                    ("bits", int(r["bits"])), ("K", int(r["K"])),
                    ("D", int(r["D"])),
                    ("MB_moved", round(int(r["bytes_moved"]) / 1048576.0, 3)),
                    ("MB_logical", round(int(r["bytes_logical"]) / 1048576.0, 3)),
                    ("latency_us", num(r["latency_us_median"])),
                    ("latency_us_min", num(r["latency_us_min"])),
                    ("cycles", num(r["cycles_median"], int)),
                    ("bw_GBps", num(r["bw_GBps"])),
                    ("throughput_Mhv_s", num(r["throughput_Mhv_per_s"])),
                    ("fits_onchip", int(int(r["bytes_logical"]) <= ONCHIP_BYTES)),
                    ("checksum_ok", int(r["checksum_ok"])),
                    ("LUT", u.get("LUT")), ("FF", u.get("FF")),
                    ("BRAM18K", u.get("BRAM18K")), ("BRAM_tiles", u.get("BRAM_tiles")),
                    ("URAM", u.get("URAM")), ("util_scope", scope),
                ]))

    bad = [r for r in rows if not r["checksum_ok"]]
    if bad:
        print("!! {} points FAILED checksum -- those transfers did not happen "
              "as expected. Fix before quoting anything.\n".format(len(bad)))

    # ---------------- speedup: design vs baseline at matched conditions -----
    base = {(r["CP"], r["bits"], r["K"]): r for r in rows if r["design"] == "buffer"}
    for r in rows:
        b = base.get((r["CP"], r["bits"], r["K"]))
        if b and r["latency_us"]:
            r["speedup_vs_buffer"] = round(b["latency_us"] / r["latency_us"], 3)
            r["bw_gain_vs_buffer"] = (round(r["bw_GBps"] / b["bw_GBps"], 3)
                                      if b["bw_GBps"] else None)

    if not os.path.isdir(SR):
        os.makedirs(SR)
    cols = list(rows[0].keys()) + ["speedup_vs_buffer", "bw_gain_vs_buffer"]
    out = os.path.join(SR, "device_memory.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["bits"], r["K"], r["CP"], r["design"])):
            w.writerow(r)

    # --------------------------------- report -------------------------------
    print("=" * 104)
    print(" MEASURED ON THE U280 -- {} target".format(target))
    print("=" * 104)
    fmt = "{:<8}{:>4}{:>6}{:>9}{:>11}{:>13}{:>11}{:>12}{:>9}"
    for bits in sorted({r["bits"] for r in rows}):
        print("\n---- {}-bit elements ----".format(bits))
        print(fmt.format("design", "CP", "K", "MB", "lat us", "BW GB/s",
                         "Mhv/s", "vs buffer", "onchip?"))
        print("-" * 104)
        for r in sorted([x for x in rows if x["bits"] == bits],
                        key=lambda r: (r["K"], r["CP"], r["design"])):
            print(fmt.format(
                r["design"], r["CP"], r["K"], r["MB_moved"],
                "{:.1f}".format(r["latency_us"]),
                "{:.2f}".format(r["bw_GBps"]),
                "{:.3f}".format(r["throughput_Mhv_s"]),
                ("{:.2f}x".format(r["speedup_vs_buffer"])
                 if r.get("speedup_vs_buffer") else "-"),
                "yes" if r["fits_onchip"] else "NO"))

    # ------------------------- Pareto: one row per build --------------------
    print("\n" + "=" * 104)
    print(" PARETO -- peak achieved throughput against post-route cost")
    print("=" * 104)
    pareto = []
    for (design, cp), (u, scope) in sorted(util_cache.items()):
        grp = [r for r in rows if r["design"] == design and r["CP"] == cp]
        if not grp:
            continue
        best = max(grp, key=lambda r: r["bw_GBps"])
        pareto.append(OrderedDict([
            ("design", design), ("CP", cp),
            ("peak_bw_GBps", round(best["bw_GBps"], 2)),
            ("at_bits", best["bits"]), ("at_K", best["K"]),
            ("peak_throughput_Mhv_s", round(best["throughput_Mhv_s"], 3)),
            ("LUT", u.get("LUT")), ("FF", u.get("FF")),
            ("BRAM18K", u.get("BRAM18K")), ("URAM", u.get("URAM")),
            ("util_scope", scope),
        ]))
    with open(os.path.join(SR, "device_pareto.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pareto[0].keys()))
        w.writeheader()
        for r in pareto:
            w.writerow(r)

    pf = "{:<8}{:>4}{:>13}{:>13}{:>10}{:>10}{:>10}  {}"
    print(pf.format("design", "CP", "peak GB/s", "peak Mhv/s", "LUT", "BRAM18K",
                    "URAM", "scope"))
    print("-" * 104)
    for r in pareto:
        print(pf.format(r["design"], r["CP"], r["peak_bw_GBps"],
                        r["peak_throughput_Mhv_s"],
                        r["LUT"] if r["LUT"] is not None else "-",
                        r["BRAM18K"] if r["BRAM18K"] is not None else "-",
                        r["URAM"] if r["URAM"] is not None else "-",
                        r["util_scope"] or "no report found"))

    missing = [k for k, (u, s) in util_cache.items() if not u]
    if missing:
        print("\nNOTE: no utilisation report found for {} -- the timing rows are"
              .format(", ".join("{}_cp{}".format(*m) for m in missing)))
        print("still valid, only the resource columns are blank. Check"
              " build/{}/_x_*/reports/".format(target))

    print("\n" + "=" * 104)
    print(" SCOPE OF THIS EXPERIMENT")
    print("=" * 104)
    print(" The consumer is a one-word-per-cycle sink standing in for the real")
    print(" downstream block. This measures the MEMORY PATH; a datatype-heavy")
    print(" consumer could become the bottleneck before memory does. Bits per")
    print(" element changes bytes moved, not the datapath, which is why all")
    print(" three widths share one build.")
    print(" On-chip ceiling used for the fits_onchip column: {:.1f} MB"
          .format(ONCHIP_BYTES / 1048576.0))
    print("=" * 104)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
