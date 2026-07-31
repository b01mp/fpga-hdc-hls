"""
collect_target.py -- gather the retargeted (device @300MHz) sweep for BOTH
off-chip designs: the buffered baseline and the dataflow-overlap version.

Run AFTER scripts/sweep_target.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_target.py

Reads:
    proj_<TAG>_memoff_c<CP>/  -- baseline: buffered, no fetch/compute overlap
    proj_<TAG>_df_c<CP>/      -- dataflow: per-channel FIFO, overlapped

Writes DSE/synth_results/<TAG>_sweep.csv with a `design` column, plus the
achieved timing estimate (target vs estimated clock period), which is the point
of retargeting -- at 300 MHz the question is whether the design closes timing.
Resource percentages are against the selected device's totals.

TAG defaults to "zcu104" and must match the TAG in scripts/sweep_target.tcl.
Override per-run with the HDC_TARGET_TAG environment variable.

NOTE: U280 (xcu280) requires a FULL Vivado licence. Under the WebPACK licence on
this machine the part is rejected outright ("Part is not supported ... does not
have an appropriate licence"), even though its device data is installed. ZCU104
(xczu7ev) is licensed, is UltraScale+ like the U280, and is the platform NysX
reports on -- so it is the closest available stand-in.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_MHZ = 300.0
WBITS = 512


# TAG must match the TAG set in scripts/sweep_target.tcl ("zcu104", "u280", ...).
TAG = os.environ.get("HDC_TARGET_TAG", "zcu104")

# Device totals for utilisation %. Add an entry when retargeting.
DEVICES = {
    "zcu104": {"LUT": 230400, "FF": 460800, "DSP": 1728, "BRAM18K": 624, "URAM": 96},
    "u280":   {"LUT": 1303680, "FF": 2607360, "DSP": 9024, "BRAM18K": 4032, "URAM": 960},
}

DESIGNS = [
    (f"proj_{TAG}_memoff_c*", rf"proj_{TAG}_memoff_c(\d+)", "memory_offchip_cp_top", "baseline_buffered"),
    (f"proj_{TAG}_df_c*",     rf"proj_{TAG}_df_c(\d+)",     "hbm_gather_cp_df_top",  "dataflow_overlap"),
]


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {k: None for k in ("BRAM18K", "DSP", "FF", "LUT", "URAM",
                             "latency", "interval", "target_ns", "estimated_ns")}
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
    # timing: |ap_clk | 3.33 ns| 2.433 ns| 0.90 ns|
    m = re.search(r"\|\s*ap_clk\s*\|\s*([\d.]+)\s*ns\s*\|\s*([\d.]+)\s*ns", t)
    if m:
        out["target_ns"] = float(m.group(1))
        out["estimated_ns"] = float(m.group(2))
    return out


DEV = DEVICES.get(TAG, DEVICES['zcu104'])

def main():
    rows = []
    for pattern, rx, top, label in DESIGNS:
        for proj in sorted(glob.glob(os.path.join(ROOT, pattern))):
            m = re.match(rx, os.path.basename(proj))
            cp = int(m.group(1)) if m else None
            rpts = (glob.glob(os.path.join(proj, "sol1", "syn", "report", top + "_csynth.rpt"))
                    or glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt")))
            if not rpts:
                rows.append(dict(design=label, CP=cp, WBITS=WBITS, status="FAILED / no report"))
                continue
            d = parse_report(rpts[0])
            d.update(design=label, CP=cp, WBITS=WBITS, status="ok")
            est = d.get("estimated_ns")
            d["fmax_MHz"] = round(1000.0 / est, 1) if est else None
            d["meets_300MHz"] = ("yes" if (est and est <= d.get("target_ns", 3.333)) else "NO")
            if cp:
                # bandwidth at the ACHIEVED clock, not the nominal 100 MHz
                f = d["fmax_MHz"] or TARGET_MHZ
                eff = min(f, TARGET_MHZ)
                d["bw_GBps_at_300"] = round(cp * WBITS / 8.0 * eff * 1e6 / 1e9, 1)
            for k in ("LUT", "FF", "DSP", "BRAM18K", "URAM"):
                v = d.get(k)
                d[k + "_pct"] = round(100.0 * v / DEV[k], 2) if v is not None else None
            rows.append(d)

    rows.sort(key=lambda r: (r.get("design") or "", r.get("CP") or 0))
    out_csv = os.path.join(ROOT, "DSE", "synth_results", TAG + "_sweep.csv")
    cols = ["design", "CP", "WBITS", "latency", "interval",
            "target_ns", "estimated_ns", "fmax_MHz", "meets_300MHz", "bw_GBps_at_300",
            "LUT", "LUT_pct", "FF", "FF_pct", "DSP", "DSP_pct",
            "BRAM18K", "BRAM18K_pct", "URAM", "URAM_pct", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = (f"{'design':<18}{'CP':>3}{'lat':>6}{'II':>5}{'est_ns':>8}{'fMHz':>7}{'300?':>6}"
           f"{'LUT':>8}{'LUT%':>7}{'BRAM':>6}{'BRAM%':>7}  status")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{str(r.get('design','')):<18}{str(r.get('CP','')):>3}{str(r.get('latency','')):>6}"
              f"{str(r.get('interval','')):>5}{str(r.get('estimated_ns','')):>8}"
              f"{str(r.get('fmax_MHz','')):>7}{str(r.get('meets_300MHz','')):>6}"
              f"{str(r.get('LUT','')):>8}{str(r.get('LUT_pct','')):>7}"
              f"{str(r.get('BRAM18K','')):>6}{str(r.get('BRAM18K_pct','')):>7}  {r.get('status','')}")
    print(f"\nNote: csynth estimates on target '{TAG}' @ {TARGET_MHZ:.0f} MHz -- not post-P&R.")
    print("For U280/HBM figures, re-run scripts/sweep_target.tcl with PART/TAG switched")
    print("to xcu280 on a machine with a full Vivado licence.")


if __name__ == "__main__":
    main()
