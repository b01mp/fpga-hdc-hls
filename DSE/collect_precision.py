"""
collect_precision.py -- read the per-stage precision sweep and attribute the saving.

Run AFTER scripts/sweep_precision.tcl:
    cd ~/fpga-hdc-hls
    python3 DSE/collect_precision.py

Reads  proj_prec_<app>_d<D>_<config>/sol1/syn/report/<top>_csynth.rpt
Writes DSE/synth_results/precision_sweep.csv

THE FIVE CONFIGURATIONS
    wide       ACC=32,   SIM=32       one global datapath width -- the baseline
    acc_only   ACC=rule, SIM=32       accumulator right-sized only
    sim_only   ACC=32,   SIM=rule     score right-sized only
    right      ACC=rule, SIM=rule     both, independently -- the design
    short      ACC=rule, SIM=rule-1   one bit under on the score

WHAT THE ATTRIBUTION IS FOR
    `right vs wide` is a single number with two causes inside it. acc_only and
    sim_only split it, so the writeup can say which stage the saving came from
    rather than asserting that "mixed precision helps".

WHAT `short` IS FOR
    It is NOT a candidate design. tb_precision.cpp case 2 shows it mispredicts
    at Hamming distance D. Its area is collected so the writeup can state that
    the incorrect configuration is barely cheaper than the correct one -- i.e.
    there is nothing to gain below the rule, which is what makes this a cliff
    rather than a trade-off curve. If `short` ever comes out MUCH cheaper than
    `right`, that is worth knowing too, and it is better to have measured it
    than to have assumed.

CAVEAT CARRIED INTO EVERY REPORT
    These are csynth estimates with no place-and-route behind them. In the
    capacity study csynth under-reported BRAM by roughly 32x on a large array.
    Registers and LUTs -- which is where an accumulator width shows up -- are
    estimated far more reliably than block RAM, so this study is less exposed
    than that one was, but the numbers are still pre-implementation.
"""
import os
import re
import glob
import csv
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")

TOPNAME = {
    "image":  "image_classification_top",
    "genome": "genome_sequence_search_top",
    "ts":     "time_series_classification_top",
}

CONFIG_ORDER = ["wide", "acc_only", "sim_only", "right", "short"]
CONFIG_ALIAS = {"acconly": "acc_only", "simonly": "sim_only"}

BASELINE = "wide"

PROJ_PAT = re.compile(r"^proj_prec_(image|genome|ts)_d(\d+)_([a-z_]+)$")


def bits_for(v):
    b = 0
    while v > 0:
        b += 1
        v >>= 1
    return b


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None,
           "URAM": None, "latency": None}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))
    return out


def load():
    rows = []
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_prec_*"))):
        m = PROJ_PAT.match(os.path.basename(proj))
        if not m:
            continue
        app, d, cfg = m.group(1), int(m.group(2)), m.group(3)
        cfg = CONFIG_ALIAS.get(cfg, cfg)
        top = TOPNAME[app]
        rpt = os.path.join(proj, "sol1", "syn", "report", top + "_csynth.rpt")
        if not os.path.exists(rpt):
            cand = glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt"))
            rpt = cand[0] if len(cand) == 1 else None
        if not rpt:
            rows.append(dict(app=app, D=d, config=cfg, status="FAILED / no report"))
            continue
        r = parse_report(rpt)
        r.update(app=app, D=d, config=cfg, status="ok")
        rows.append(r)
    return rows


def cell(row, key):
    v = row.get(key)
    return "-" if v is None else str(v)


def main():
    rows = load()
    if not rows:
        raise SystemExit("No proj_prec_* projects found. Run scripts/sweep_precision.tcl first.")

    # ---- derive savings against the `wide` baseline at the same (app, D) ----
    base = {}
    for r in rows:
        if r.get("config") == BASELINE and r.get("LUT") is not None:
            base[(r["app"], r["D"])] = r

    for r in rows:
        b = base.get((r["app"], r["D"]))
        if not b:
            continue
        for res in ("LUT", "FF"):
            if r.get(res) is not None and b.get(res):
                r[res + "_vs_wide"] = round(100.0 * (b[res] - r[res]) / float(b[res]), 2)
        if r.get("latency") and b.get("latency"):
            r["latency_ratio"] = round(r["latency"] / float(b["latency"]), 4)

    rows.sort(key=lambda r: (r["app"], r["D"],
                             CONFIG_ORDER.index(r["config"])
                             if r["config"] in CONFIG_ORDER else 99))

    cols = ["app", "D", "config", "latency", "latency_ratio", "LUT", "LUT_vs_wide",
            "FF", "FF_vs_wide", "DSP", "BRAM18K", "URAM", "status"]
    if not os.path.isdir(SR):
        os.makedirs(SR)
    out_csv = os.path.join(SR, "precision_sweep.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    # ------------------------------ report ------------------------------
    print("=" * 84)
    print(" PER-STAGE PRECISION -- what independent stage widths bought")
    print("=" * 84)

    fmt = "{:<10}{:>4}{:>7}{:>11}{:>9}{:>9}{:>9}{:>9}"
    for app in ("image", "genome", "ts"):
        for d in sorted({r["D"] for r in rows if r["app"] == app}):
            grp = [r for r in rows if r["app"] == app and r["D"] == d]
            if not grp:
                continue
            print("\n---- {}  D={}  (score rule = {} bits) ----".format(
                app, d, bits_for(d) + 1))
            print(fmt.format("config", "D", "lat", "LUT", "LUT-%", "FF", "FF-%", "BRAM"))
            print("-" * 68)
            for r in grp:
                print(fmt.format(
                    r["config"], r["D"], cell(r, "latency"), cell(r, "LUT"),
                    cell(r, "LUT_vs_wide"), cell(r, "FF"), cell(r, "FF_vs_wide"),
                    cell(r, "BRAM18K")))

    # ---- attribution: does acc_only + sim_only account for right? ----
    print("\n" + "=" * 84)
    print(" ATTRIBUTION -- where the saving came from")
    print("=" * 84)
    for app in ("image", "genome", "ts"):
        for d in sorted({r["D"] for r in rows if r["app"] == app}):
            g = {r["config"]: r for r in rows if r["app"] == app and r["D"] == d}
            if not all(k in g for k in ("wide", "acc_only", "sim_only", "right")):
                continue
            a = g["acc_only"].get("LUT_vs_wide")
            s = g["sim_only"].get("LUT_vs_wide")
            t = g["right"].get("LUT_vs_wide")
            if a is None or s is None or t is None:
                continue
            print(" {:<8} D={:<6} accumulator {:>6}%   score {:>6}%   both {:>6}%   "
                  "(sum {:>6}%)".format(app, d, a, s, t, round(a + s, 2)))
    print("\n A large gap between `both` and the sum means the two stages share")
    print(" logic, so the savings are not additive. That is a real effect and")
    print(" belongs in the writeup rather than being rounded away.")

    # ---- the cliff ----
    print("\n" + "=" * 84)
    print(" THE CLIFF -- `short` is one bit under the rule and NUMERICALLY WRONG")
    print("=" * 84)
    print(" (tb_precision case 2 shows it mispredicts at Hamming distance D.)")
    for app in ("image", "genome", "ts"):
        for d in sorted({r["D"] for r in rows if r["app"] == app}):
            g = {r["config"]: r for r in rows if r["app"] == app and r["D"] == d}
            if "right" not in g or "short" not in g:
                continue
            rl, sl = g["right"].get("LUT"), g["short"].get("LUT")
            if not rl or not sl:
                continue
            print(" {:<8} D={:<6} right {:>6} LUT   short {:>6} LUT   "
                  "extra saving from being wrong: {:>5.2f}%".format(
                      app, d, rl, sl, 100.0 * (rl - sl) / float(rl)))
    print("\n If that last column is small, there is nothing to gain below the")
    print(" rule -- the boundary is a cliff, not a knee, and the rule is simply")
    print(" the cheapest correct point.")

    bad = [r for r in rows if r.get("status") != "ok"]
    if bad:
        print("\n!! {} run(s) produced no report:".format(len(bad)))
        for r in bad:
            print("   {} D={} {}".format(r["app"], r["D"], r["config"]))

    print("\n" + "=" * 84)
    print(" CAVEAT: csynth estimates, no place-and-route. LUT/FF estimates are")
    print(" far more reliable than BRAM, and accumulator width shows up in")
    print(" LUT/FF, so this study is less exposed than the capacity one -- but")
    print(" these are still pre-implementation numbers.")
    print("=" * 84)
    print("\nwrote", out_csv)


if __name__ == "__main__":
    main()
