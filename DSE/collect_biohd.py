"""
collect_biohd.py -- BioHD precision x prototype-count study (ZCU104 @300 MHz).

Run AFTER scripts/sweep_biohd.tcl:
    cd C:/USC/fpga-hdc-hls
    python DSE/collect_biohd.py

Reads proj_biohd_x<X>_np<NP>/ and writes DSE/synth_results/biohd_sweep.csv,
then prints the binary-vs-int32 comparison across prototype counts.

Metrics per (precision, NP), all at D=10240, CP=1, QB=4:
    ns/scan          : time to search NP references once (all QB queries)
    ns/comparison    : ns/scan / (NP*QB) -- the unit similarity search pays
    traffic/query    : NP * D * X bits fetched off-chip per query
    codebook footprint per reference : D * X bits (the capacity axis)

This is a STANDALONE ZCU104/U280 study, not merged into the xc7z020 master
table (different device and clock -- mixing would be inconsistent).
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = 10240
QB = 4
ZCU_BRAM = 624
ZCU_LUT = 230400
ZCU_FF = 460800


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


def main():
    rows = []
    projs = ([(p, 1) for p in glob.glob(os.path.join(ROOT, "proj_biohd_x*_np*_qb*"))]
             + [(p, 0) for p in glob.glob(os.path.join(ROOT, "proj_biohdnl_x*_np*_qb*"))])
    for proj, ovl in sorted(projs, key=lambda t: (t[1], t[0])):
        m = re.match(r"proj_biohd(?:nl)?_x(\d+)_np(\d+)_qb(\d+)", os.path.basename(proj))
        if not m:
            continue
        x, np_, qb = int(m.group(1)), int(m.group(2)), int(m.group(3))
        rpts = (glob.glob(os.path.join(proj, "sol1", "syn", "report", "compose_biohd_top_csynth.rpt"))
                or glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt")))
        if not rpts:
            rows.append(dict(X=x, NP=np_, QB=qb, OVL=ovl, status="FAILED / no report"))
            continue
        d = parse_report(rpts[0])
        d.update(X=x, NP=np_, QB=qb, OVL=ovl, status="ok")
        est = d.get("estimated_ns")
        d["fmax_MHz"] = round(1000.0 / est, 1) if est else None
        d["meets_300"] = ("yes" if (est and est <= 3.334) else "NO")
        if est and d.get("interval"):
            d["ns_scan"] = round(d["interval"] * est, 1)
            # one scan serves QB queries -> per (reference, query) comparison
            d["ns_per_cmp"] = round(d["ns_scan"] / (np_ * qb), 2)
            d["ns_per_query"] = round(d["ns_scan"] / qb, 1)
        # off-chip traffic per query: one scan amortized over QB queries
        d["traffic_per_query_bits"] = (np_ * D * x) // qb
        d["ref_footprint_bits"] = D * x
        d["metric"] = "Hamming/argmin" if x == 1 else "dot/argmax"
        d["BRAM_pct"] = round(100.0 * d["BRAM18K"] / ZCU_BRAM, 1) if d.get("BRAM18K") else None
        rows.append(d)

    rows.sort(key=lambda r: (r.get("X") or 0, r.get("NP") or 0, r.get("QB") or 0,
                             r.get("OVL") or 0))
    out_csv = os.path.join(ROOT, "DSE", "synth_results", "biohd_sweep.csv")
    cols = ["X", "metric", "NP", "QB", "OVL", "latency", "interval", "ns_scan",
            "ns_per_query", "ns_per_cmp",
            "traffic_per_query_bits", "ref_footprint_bits",
            "estimated_ns", "fmax_MHz", "meets_300",
            "LUT", "FF", "DSP", "BRAM18K", "BRAM_pct", "status"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "\n")
    print(f"BioHD 2x2 ablation -- ZCU104 @300MHz, D={D}, CP=1")
    print("overlap: 0 = buffered baseline (load, barrier, compute) | 1 = FIFO dataflow")
    print("batch:   QB=1 = one query per scan | QB=4 = four resident queries\n")
    hdr = (f"{'prec':<8}{'NP':>5}{'ovl':>4}{'QB':>4}{'ns/scan':>11}{'ns/query':>11}"
           f"{'ns/cmp':>9}{'traffic/q':>11}{'fMHz':>7}{'LUT':>8}{'BRAM':>6}")
    print(hdr); print("-" * len(hdr))
    idx = {(r.get("X"), r.get("NP"), r.get("OVL"), r.get("QB")): r
           for r in rows if r.get("status") == "ok"}
    for r in rows:
        prec = "binary" if r.get("X") == 1 else f"int{r.get('X')}"
        tq = r.get("traffic_per_query_bits")
        tq_s = f"{tq/8/1024:.0f}KB" if tq else ""
        print(f"{prec:<8}{str(r.get('NP','')):>5}{str(r.get('OVL','')):>4}"
              f"{str(r.get('QB','')):>4}{str(r.get('ns_scan','')):>11}"
              f"{str(r.get('ns_per_query','')):>11}{str(r.get('ns_per_cmp','')):>9}{tq_s:>11}"
              f"{str(r.get('fmax_MHz','')):>7}{str(r.get('LUT','')):>8}"
              f"{str(r.get('BRAM18K','')):>6}")

    # ---- ablation summary: isolate overlap, batching, and the two combined ----
    print("\n" + "=" * 78)
    print("CONTRIBUTION ABLATION (ns per query, lower is better)")
    print("=" * 78)
    hdr2 = (f"{'prec':<8}{'NP':>5}{'base':>11}{'+overlap':>11}{'+batch':>11}"
            f"{'+both':>11}{'ovl x':>7}{'bat x':>7}{'both x':>8}")
    print(hdr2); print("-" * len(hdr2))
    for x in (1, 32):
        for np_ in (32, 64, 128, 256):
            g = lambda o, q: idx.get((x, np_, o, q), {}).get("ns_per_query")
            base, ovl, bat, both = g(0, 1), g(1, 1), g(0, 4), g(1, 4)
            if not all([base, ovl, bat, both]):
                continue
            prec = "binary" if x == 1 else f"int{x}"
            print(f"{prec:<8}{np_:>5}{base:>11.1f}{ovl:>11.1f}{bat:>11.1f}{both:>11.1f}"
                  f"{base/ovl:>7.2f}{base/bat:>7.2f}{base/both:>8.2f}")
    print("\novl x = overlap alone | bat x = batching alone | both x = combined vs baseline")
    print(f"\nref footprint: binary = {D} bits ({D/8/1024:.1f}KB); "
          f"int32 = {D*32} bits ({D*32/8/1024:.0f}KB) per reference.")


if __name__ == "__main__":
    main()
