"""
collect_memory_offchip_cp.py -- gather the BASELINE off-chip CP sweep into one CSV.

Run AFTER scripts/sweep_memory_offchip_cp.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_memory_offchip_cp.py

Reads proj_memoff_cp<CP>/sol1/syn/report/memory_offchip_cp_top_csynth.rpt and
writes DSE/synth_results/memory_offchip_cp_sweep.csv -- one row per channel count.

This is the NO-OVERLAP baseline for hbm_cp_df_sweep.csv: same D=8192, same
WBITS=512, same CP grid, same compute, same AXI tuning. The only difference is
that this design buffers a whole hypervector on chip before consuming it
(barrier), instead of streaming it through a FIFO inside a DATAFLOW region.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREQ_MHZ = 100      # matches create_clock -period 10 in the sweep tcl
WBITS = 512         # fixed in this sweep


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None,
           "latency": None, "interval": None}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
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
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_memoff_cp*"))):
        m = re.match(r"proj_memoff_cp(\d+)", os.path.basename(proj))
        cp = int(m.group(1)) if m else None
        rpts = (glob.glob(os.path.join(proj, "sol1", "syn", "report", "memory_offchip_cp_top_csynth.rpt"))
                or glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt")))
        if not rpts:
            rows.append(dict(CP=cp, WBITS=WBITS, status="FAILED / no report"))
            continue
        d = parse_report(rpts[0])
        d.update(CP=cp, WBITS=WBITS, status="ok")
        if cp:
            d["peak_bw_GBps"] = round(cp * WBITS / 8.0 * FREQ_MHZ * 1e6 / 1e9, 2)
        rows.append(d)

    rows.sort(key=lambda r: r.get("CP") or 0)
    out_csv = os.path.join(ROOT, "DSE", "synth_results", "memory_offchip_cp_sweep.csv")
    cols = ["CP", "WBITS", "latency", "interval", "peak_bw_GBps",
            "LUT", "FF", "DSP", "BRAM18K", "URAM", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = f"{'CP':>4}{'WBITS':>7}{'lat':>6}{'II':>6}{'GB/s*':>7}{'LUT':>7}{'FF':>7}{'DSP':>5}{'BRAM':>6}  status"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{str(r.get('CP','')):>4}{str(r.get('WBITS','')):>7}{str(r.get('latency','')):>6}"
              f"{str(r.get('interval','')):>6}{str(r.get('peak_bw_GBps','')):>7}"
              f"{str(r.get('LUT','')):>7}{str(r.get('FF','')):>7}{str(r.get('DSP','')):>5}"
              f"{str(r.get('BRAM18K','')):>6}  {r.get('status','')}")
    print("\n* GB/s = CP * WBITS/8 * 100MHz (analytical, CP parallel ports); ~3x on U280 @300MHz.")


if __name__ == "__main__":
    main()
