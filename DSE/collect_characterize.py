"""
collect_characterize.py -- gather the per-function parallelism sweep into one CSV.

Run AFTER scripts/sweep_characterize.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_characterize.py

Reads proj_ch_<fn>_dp<N>/sol1/syn/report/<fn>_csynth.rpt and writes
DSE/synth_results/characterize.csv -- one row per (function, DP) design point.
This is the parallelism slice of the Pareto table Haoyang's DSE searches.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None, "latency": None}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))
    return out


def main():
    rows = []
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_ch_*"))):
        base = os.path.basename(proj).replace("proj_ch_", "")   # e.g. ch_bind_dp4
        m = re.match(r"(ch_[a-z_]+)_dp(\d+)", base)
        fn = m.group(1) if m else base
        dp = int(m.group(2)) if m else None
        rpts = glob.glob(os.path.join(proj, "sol1", "syn", "report", fn + "_csynth.rpt"))
        if not rpts:
            rpts = glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt"))
        if not rpts:
            rows.append(dict(function=fn, DP=dp, status="FAILED / no report"))
            continue
        d = parse_report(rpts[0])
        d.update(function=fn.replace("ch_", ""), DP=dp, status="ok")
        rows.append(d)

    rows.sort(key=lambda r: (r.get("function", ""), r.get("DP") or 0))
    out_csv = os.path.join(ROOT, "DSE", "synth_results", "characterize.csv")
    cols = ["function", "DP", "latency", "LUT", "FF", "DSP", "BRAM18K", "URAM", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = f"{'function':<16}{'DP':>4}{'latency':>9}{'LUT':>7}{'DSP':>5}{'BRAM':>6}  status"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{str(r.get('function','')):<16}{str(r.get('DP','')):>4}{str(r.get('latency','')):>9}"
              f"{str(r.get('LUT','')):>7}{str(r.get('DSP','')):>5}{str(r.get('BRAM18K','')):>6}  {r.get('status','')}")


if __name__ == "__main__":
    main()
