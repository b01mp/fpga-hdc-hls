"""
collect_hbm.py -- gather the streaming hbm_gather port-width sweep into one CSV.

Run AFTER scripts/sweep_hbm_gather.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_hbm.py

Reads proj_hbm_w<WBITS>/sol1/syn/report/hbm_gather_char_csynth.rpt and writes
DSE/synth_results/hbm_sweep.csv -- one row per port width. This is the off-chip
streaming-access slice of the Pareto table Haoyang's DSE searches.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREQ_MHZ = 100      # matches create_clock -period 10 in the sweep tcl


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None,
           "latency": None, "interval": None}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
    # summary row: |lat_min|lat_max| abs_min | abs_max |int_min|int_max| type
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|"
                  r"\s*[\d.]+\s*[num]s\|\s*[\d.]+\s*[num]s\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|",
                  t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))
        out["interval"] = int(m.group(4).replace(",", ""))
    else:
        m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
        if m:
            out["latency"] = int(m.group(2).replace(",", ""))
    return out


def main():
    rows = []
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_hbm_w*"))):
        m = re.match(r"proj_hbm_w(\d+)", os.path.basename(proj))
        wbits = int(m.group(1)) if m else None
        rpts = (glob.glob(os.path.join(proj, "sol1", "syn", "report", "hbm_gather_char_csynth.rpt"))
                or glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt")))
        if not rpts:
            rows.append(dict(WBITS=wbits, status="FAILED / no report"))
            continue
        d = parse_report(rpts[0])
        d.update(WBITS=wbits, status="ok")
        if wbits:
            d["peak_bw_GBps"] = round(wbits / 8.0 * FREQ_MHZ * 1e6 / 1e9, 2)
        rows.append(d)

    rows.sort(key=lambda r: r.get("WBITS") or 0)
    out_csv = os.path.join(ROOT, "DSE", "synth_results", "hbm_sweep.csv")
    cols = ["WBITS", "latency", "interval", "peak_bw_GBps",
            "LUT", "FF", "DSP", "BRAM18K", "URAM", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = f"{'WBITS':>6}{'lat':>6}{'II':>6}{'GB/s*':>7}{'LUT':>7}{'FF':>7}{'DSP':>5}{'BRAM':>6}  status"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{str(r.get('WBITS','')):>6}{str(r.get('latency','')):>6}{str(r.get('interval','')):>6}"
              f"{str(r.get('peak_bw_GBps','')):>7}{str(r.get('LUT','')):>7}{str(r.get('FF','')):>7}"
              f"{str(r.get('DSP','')):>5}{str(r.get('BRAM18K','')):>6}  {r.get('status','')}")
    print("\n* GB/s = WBITS/8 * 100MHz (analytical, single wide port); ~3x on U280 @300MHz.")


if __name__ == "__main__":
    main()
