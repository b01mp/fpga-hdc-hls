"""
collect_onchip_cp.py -- the memory-tier comparison that positions the off-chip work.

Run AFTER scripts/sweep_memory_onchip_cp.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_onchip_cp.py

Gathers four ways of delivering CP prototypes to a consumer, all at D=8192,
WBITS=512, ZCU104 @300MHz, with identical compute:

    on-chip BRAM        codebook resident in block RAM   (what prior work does)
    on-chip URAM        codebook resident in ultra RAM   (larger, less flexible)
    off-chip buffered   streamed, load-then-compute      (no overlap)
    off-chip overlapped streamed through per-channel FIFO (our configuration)

Writes DSE/synth_results/memory_tier_comparison.csv.

The point of the table is NOT that off-chip is faster -- it will not be. It is
that off-chip removes the capacity ceiling, and the overlap keeps the price of
doing so small. The capacity column is therefore as important as the timing ones:
a resident codebook is bounded by on-chip RAM, an off-chip one is not.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZCU104 = {"LUT": 230400, "FF": 460800, "DSP": 1728, "BRAM18K": 624, "URAM": 96}
D_BITS = 8192          # hypervector dimension
TN = 64                # codebook rows per channel in these runs


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {k: None for k in ("BRAM18K", "DSP", "FF", "LUT", "URAM",
                             "latency", "interval", "estimated_ns")}
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
    m = re.search(r"\|\s*ap_clk\s*\|\s*[\d.]+\s*ns\s*\|\s*([\d.]+)\s*ns", t)
    if m:
        out["estimated_ns"] = float(m.group(1))
    return out


def collect(proj, top, tier, capacity, cp, rows):
    rpts = (glob.glob(os.path.join(proj, "sol1", "syn", "report", top + "_csynth.rpt"))
            or glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt")))
    if not rpts:
        rows.append(dict(tier=tier, CP=cp, capacity=capacity, status="FAILED / no report"))
        return
    d = parse_report(rpts[0])
    d.update(tier=tier, CP=cp, capacity=capacity, status="ok")
    est = d.get("estimated_ns")
    d["fmax_MHz"] = round(1000.0 / est, 1) if est else None
    if est and d.get("interval"):
        d["II_ns"] = round(d["interval"] * est, 1)
        d["ns_per_HV"] = round(d["II_ns"] / cp, 1) if cp else None
        d["BW_GBps"] = round(cp * D_BITS / 8.0 / (d["II_ns"] * 1e-9) / 1e9, 1)
    if est and d.get("latency"):
        d["lat_ns"] = round(d["latency"] * est, 1)
    rows.append(d)


def main():
    rows = []
    specs = [
        ("proj_zcu104_onchip_bram_c*", "memory_onchip_cp_top",   "on-chip BRAM",        "bounded"),
        ("proj_zcu104_onchip_uram_c*", "memory_onchip_cp_top",   "on-chip URAM",        "bounded"),
        ("proj_zcu104_memoff_c*",      "memory_offchip_cp_top",  "off-chip buffered",   "unbounded"),
        ("proj_zcu104_df_c*",          "hbm_gather_cp_df_top",   "off-chip overlapped", "unbounded"),
    ]
    for pattern, top, tier, cap in specs:
        for proj in sorted(glob.glob(os.path.join(ROOT, pattern))):
            b = os.path.basename(proj)
            if "_w256_" in b or "_d16_" in b or "_d32_" in b:
                continue
            m = re.search(r"_c(\d+)$", b)
            if not m:
                continue
            collect(proj, top, tier, cap, int(m.group(1)), rows)

    order = {"on-chip BRAM": 0, "on-chip URAM": 1, "off-chip buffered": 2, "off-chip overlapped": 3}
    rows.sort(key=lambda r: (r.get("CP") or 0, order.get(r.get("tier"), 9)))
    out_csv = os.path.join(ROOT, "DSE", "synth_results", "memory_tier_comparison.csv")
    cols = ["CP", "tier", "capacity", "latency", "interval", "lat_ns", "II_ns",
            "ns_per_HV", "BW_GBps", "estimated_ns", "fmax_MHz",
            "LUT", "FF", "BRAM18K", "URAM", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    hdr = (f"{'CP':>3}{'tier':<21}{'cap':<11}{'II_ns':>8}{'ns/HV':>8}{'GB/s':>7}"
           f"{'fMHz':>7}{'LUT':>8}{'BRAM':>6}{'URAM':>6}  status")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{str(r.get('CP','')):>3}{str(r.get('tier','')):<21}{str(r.get('capacity','')):<11}"
              f"{str(r.get('II_ns','')):>8}{str(r.get('ns_per_HV','')):>8}{str(r.get('BW_GBps','')):>7}"
              f"{str(r.get('fmax_MHz','')):>7}{str(r.get('LUT','')):>8}"
              f"{str(r.get('BRAM18K','')):>6}{str(r.get('URAM','')):>6}  {r.get('status','')}")

    # capacity ceiling: how many hypervectors fit on chip vs what off-chip allows
    print(f"\nCapacity: at D={D_BITS} bits, ZCU104 holds ~{ZCU104['BRAM18K']*18432//D_BITS} HVs in BRAM "
          f"and ~{ZCU104['URAM']*294912//D_BITS} in URAM (whole device, before any compute).")
    print(f"These runs use TN={TN} rows/channel. A realistic item memory (N >> {TN}) exceeds both,")
    print("which is the reason the off-chip path exists at all.")


if __name__ == "__main__":
    main()
