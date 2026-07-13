"""
collect_memory.py -- gather the memory-knob sweep reports into one CSV.

Run AFTER scripts/sweep_memory.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_memory.py

Reads proj_sw_*/sol1/syn/report/*_top_csynth.rpt and writes
DSE/synth_results/memory_sweep.csv (one row per design point) -- the memory rows
of the characterization table Haoyang's DSE searches.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # fpga-hdc-hls


def classify(tag):
    """tag -> (memory_space, banking)."""
    if tag.startswith("bram_dp"):
        return "bram", int(tag.split("dp")[1])
    if tag.startswith("uram_dp"):
        return "uram", int(tag.split("dp")[1])
    if tag == "offchip":
        return "offchip", None
    return tag, None


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None,
           "total_lat": None, "read_lat": None}

    # Utilization 'Total' row: | Total | BRAM_18K | DSP | FF | LUT | URAM |
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))

    # Overall latency (max cycles) from the Latency (cycles) summary
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["total_lat"] = int(m.group(2).replace(",", ""))

    # The actual read loop (GATHER_LOOP on-chip, OUT off-chip) -- banking speeds this
    m = re.search(r"(?:GATHER_LOOP|OUT)\s*\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out["read_lat"] = int(m.group(2))
    return out


def main():
    rows = []
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_sw_*"))):
        tag = os.path.basename(proj).replace("proj_sw_", "")
        ms, bank = classify(tag)
        rpts = glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_top_csynth.rpt"))
        if not rpts:
            rows.append(dict(config=tag, memory_space=ms, banking=bank, status="FAILED / no report"))
            continue
        d = parse_report(rpts[0])
        d.update(config=tag, memory_space=ms, banking=bank, status="ok")
        rows.append(d)

    out_csv = os.path.join(ROOT, "DSE", "synth_results", "memory_sweep.csv")
    cols = ["config", "memory_space", "banking", "BRAM18K", "URAM", "DSP", "FF",
            "LUT", "total_lat", "read_lat", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = f"{'config':<10}{'mem':>8}{'bank':>5}{'BRAM':>6}{'URAM':>6}{'DSP':>5}{'LUT':>7}{'read_lat':>9}  status"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r.get('config',''):<10}{str(r.get('memory_space','')):>8}{str(r.get('banking','')):>5}"
              f"{str(r.get('BRAM18K','')):>6}{str(r.get('URAM','')):>6}{str(r.get('DSP','')):>5}"
              f"{str(r.get('LUT','')):>7}{str(r.get('read_lat','')):>9}  {r.get('status','')}")


if __name__ == "__main__":
    main()
