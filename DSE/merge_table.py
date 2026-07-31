"""
merge_table.py -- stitch the three characterization sweeps into ONE master table,
run the overlap consistency check, and Pareto-filter per function.

Run AFTER the three collectors (parallelism, datatype, memory):
    cd C:/USC/fpga-hdc-hls
    python DSE/merge_table.py

Inputs (DSE/synth_results/):
    characterize.csv   -- parallelism sweep (DP), binary, on-chip BRAM
    benchmarks.csv     -- datatype sweep (config==datatype rows), DP=8, on-chip BRAM
    memory_sweep.csv   -- memory sweep (memory_space x banking), function=gather
    hbm_sweep.csv      -- off-chip streaming gather (port width), function=hbm_gather
    hbm_cp_sweep.csv   -- class-parallel streaming gather (CP), function=hbm_gather_cp
    hbm_cp_df_sweep.csv -- CP gather + FIFO/dataflow overlap, function=hbm_gather_cp_df
    memory_offchip_cp_sweep.csv -- CP gather, buffered/no overlap (BASELINE),
                                   function=offchip_baseline_cp
    biohd_sweep.csv    -- BioHD precision x prototype-count x query-batch study
                          (ZCU104), functions biohd_compose_search (overlap) and
                          biohd_buffered_base (no overlap)

Outputs (DSE/synth_results/):
    master_table.csv   -- every characterized design point, common schema
    pareto_table.csv   -- non-dominated points per (function, device)

NOTE on the schema: `device` and `latency_unit` are part of the key. Resource
counts and the `latency` column are only comparable WITHIN a (function, device)
group -- the Pareto filter enforces this. Off-chip rows are xc7z020 unless the
device column says otherwise; the BioHD rows are zcu104.

Each sweep varies ONE knob and holds the others at a baseline; this stacks the
slices, giving every row its full knob vector. The estimator fills the interior.
"""
import os
import csv

SR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth_results")

# common schema
#   device : the synthesis target. Resource counts are NOT comparable across
#            devices, so this is part of the consistency key and every consumer
#            must filter on it. Everything characterized before the BioHD study
#            is xc7z020 @100MHz; the BioHD rows are ZCU104 @300MHz.
#   QB, NP : query-batch size and references-per-scan. Only the BioHD/batched
#            rows carry them; blank elsewhere.
COLS = ["function", "device", "DP", "CP", "QB", "NP", "datatype", "memory_space",
        "banking", "port_width", "latency", "latency_unit", "LUT", "FF", "DSP",
        "BRAM18K", "URAM", "source"]
OBJ = ["latency", "LUT", "FF", "DSP", "BRAM18K", "URAM"]   # all minimized
DEFAULT_DEVICE = "xc7z020"     # every pre-BioHD sweep ran on this part @100MHz


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read_csv(name):
    path = os.path.join(SR, name)
    if not os.path.exists(path):
        print(f"  (skip: {name} not found)")
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_parallelism():
    rows = []
    for r in read_csv("characterize.csv"):
        if r.get("status") != "ok":
            continue
        rows.append(dict(function=r["function"], DP=r.get("DP"), CP=r.get("CP") or "",
                         datatype="binary", memory_space="bram", banking=1,
                         latency=r.get("latency"), LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="parallelism"))
    return rows


def load_datatype():
    rows = []
    for r in read_csv("benchmarks.csv"):
        if r.get("config") != "datatype":
            continue
        fn = r.get("primitive")
        cp = 2 if fn == "similarity" else 1
        rows.append(dict(function=fn, DP=r.get("DP"), CP=cp,
                         datatype=r.get("family"), memory_space="bram", banking=1,
                         latency=r.get("latency_cycles"), LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="datatype"))
    return rows


def load_memory():
    rows = []
    for r in read_csv("memory_sweep.csv"):
        if r.get("status") != "ok":
            continue
        bank = r.get("banking")
        rows.append(dict(function="gather", DP=(bank or ""), CP="",
                         datatype="binary", memory_space=r.get("memory_space"), banking=bank,
                         latency=r.get("read_lat"), LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="memory"))
    return rows


def load_hbm():
    # streaming wide-port hbm_gather: knob is the port width (WBITS), single port.
    rows = []
    for r in read_csv("hbm_sweep.csv"):
        if r.get("status") != "ok":
            continue
        rows.append(dict(function="hbm_gather", DP="", CP="",
                         datatype="binary", memory_space="offchip", banking=1,
                         port_width=r.get("WBITS"),
                         latency=r.get("latency"), LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="hbm"))
    return rows


def load_hbm_cp():
    # class-parallel streaming gather: CP channels, each streaming a DIFFERENT
    # hypervector; knobs = CP (channel count) and port width (fixed 512 here).
    # One call delivers CP hypervectors in `latency` cycles, so we normalize to
    # PER-HYPERVECTOR latency (measured/CP) -- the unit every other memory row
    # in this table uses. Without this, all CP points tie on per-call latency
    # and the Pareto filter wrongly drops CP>1. Raw per-call cycles stay in
    # hbm_cp_sweep.csv.
    rows = []
    for r in read_csv("hbm_cp_sweep.csv"):
        if r.get("status") != "ok":
            continue
        cp = r.get("CP")
        lat = _num(r.get("latency"))
        eff = round(lat / float(cp), 1) if (lat is not None and _num(cp)) else r.get("latency")
        rows.append(dict(function="hbm_gather_cp", DP="", CP=cp,
                         datatype="binary", memory_space="offchip", banking=cp,
                         port_width=r.get("WBITS"),
                         latency=eff, LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="hbm_cp"))
    return rows


def load_hbm_cp_df():
    # CP gather WITH fetch/compute overlap: same producer as hbm_gather_cp, but
    # inside a DATAFLOW region -- each channel drains through a deep FIFO into a
    # concurrent consumer, so the measured cycles now include a consumer running
    # OVERLAPPED with the read (the NysX-style FIFO decoupling). Same per-
    # hypervector normalization as load_hbm_cp so the two variants compare
    # row-for-row.
    rows = []
    for r in read_csv("hbm_cp_df_sweep.csv"):
        if r.get("status") != "ok":
            continue
        cp = r.get("CP")
        lat = _num(r.get("latency"))
        eff = round(lat / float(cp), 1) if (lat is not None and _num(cp)) else r.get("latency")
        rows.append(dict(function="hbm_gather_cp_df", DP="", CP=cp,
                         datatype="binary", memory_space="offchip", banking=cp,
                         port_width=r.get("WBITS"),
                         latency=eff, LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="hbm_cp_df"))
    return rows


def load_memory_offchip_cp():
    # BASELINE off-chip reader: identical to hbm_gather_cp_df in width, channel
    # count, AXI tuning, D and compute -- but it buffers a whole hypervector on
    # chip before consuming it (barrier) instead of streaming through a FIFO in a
    # DATAFLOW region. So the delta against hbm_gather_cp_df isolates the
    # fetch/compute overlap. Same per-hypervector normalization as the others.
    rows = []
    for r in read_csv("memory_offchip_cp_sweep.csv"):
        if r.get("status") != "ok":
            continue
        cp = r.get("CP")
        lat = _num(r.get("latency"))
        eff = round(lat / float(cp), 1) if (lat is not None and _num(cp)) else r.get("latency")
        rows.append(dict(function="offchip_baseline_cp", DP="", CP=cp,
                         datatype="binary", memory_space="offchip", banking=cp,
                         port_width=r.get("WBITS"),
                         latency=eff, LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source="offchip_base"))
    return rows


def load_biohd():
    # BioHD precision x prototype-count x query-batch study (ZCU104 @300MHz).
    # Distinct device, so these rows are tagged and kept on their own Pareto
    # front -- resource counts do not compare against the xc7z020 rows.
    # Latency is normalized to cycles per (reference, query) COMPARISON,
    # interval/(NP*QB), matching the other batched/composed loaders.
    rows = []
    for r in read_csv("biohd_sweep.csv"):
        if r.get("status") != "ok":
            continue
        np_ = _num(r.get("NP")) or 1
        qb = _num(r.get("QB")) or 1
        ii = _num(r.get("interval"))
        eff = round(ii / (np_ * qb), 3) if ii is not None else r.get("interval")
        x = r.get("X")
        # OVL=1 streaming (design) vs OVL=0 buffered (baseline) -- distinct
        # function names so each gets its own Pareto front and no key collision.
        ovl = r.get("OVL", "1")
        fn = "biohd_compose_search" if str(ovl) == "1" else "biohd_buffered_base"
        rows.append(dict(function=fn, device="zcu104",
                         DP="", CP=1, QB=r.get("QB"), NP=r.get("NP"),
                         datatype=("binary" if x == "1" else f"int{x}"),
                         memory_space="offchip", banking=1,
                         port_width=512,
                         latency=eff, LUT=r.get("LUT"), FF=r.get("FF"),
                         DSP=r.get("DSP"), BRAM18K=r.get("BRAM18K"), URAM=r.get("URAM"),
                         source=("biohd" if str(ovl) == "1" else "biohd_base")))
    return rows


def consistency_check(rows):
    """Overlap points (same knobs, different source) should report the same LUT."""
    key = lambda r: (r["function"], r.get("device", DEFAULT_DEVICE), str(r["DP"]),
                     str(r["CP"]), str(r.get("QB", "")), str(r.get("NP", "")),
                     r["datatype"], r["memory_space"], str(r["banking"]),
                     str(r.get("port_width", "")))
    seen = {}
    warned = 0
    for r in rows:
        k = key(r)
        if k in seen and _num(seen[k]["LUT"]) != _num(r["LUT"]):
            print(f"  MISMATCH {k}: {seen[k]['source']} LUT={seen[k]['LUT']} vs "
                  f"{r['source']} LUT={r['LUT']}")
            warned += 1
        else:
            seen.setdefault(k, r)
    print(f"  consistency: {warned} mismatch(es) at overlap points")


def dominates(a, b):
    """a dominates b if a <= b on every objective and < on at least one."""
    le = True
    lt = False
    for o in OBJ:
        av, bv = _num(a.get(o)), _num(b.get(o))
        if av is None or bv is None:
            return False
        if av > bv:
            le = False
            break
        if av < bv:
            lt = True
    return le and lt


def pareto_per_function(rows):
    """Pareto per (function, device). Resources are device-specific, so a point
    on one part can never dominate a point on another."""
    out = []
    groups = sorted(set((r["function"], r.get("device", DEFAULT_DEVICE)) for r in rows))
    for fn, dev in groups:
        pts = [r for r in rows
               if r["function"] == fn and r.get("device", DEFAULT_DEVICE) == dev
               and _num(r.get("latency")) is not None]
        front = [r for r in pts if not any(dominates(o, r) for o in pts if o is not r)]
        out.extend(sorted(front, key=lambda r: (_num(r["latency"]) or 0)))
    return out


def write(name, rows):
    with open(os.path.join(SR, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            row = {c: r.get(c, "") for c in COLS}
            if not row.get("device"):
                row["device"] = DEFAULT_DEVICE     # stamp the pre-BioHD sweeps
            w.writerow(row)


def main():
    print("loading sweeps:")
    rows = (load_parallelism() + load_datatype() + load_memory() + load_hbm()
            + load_hbm_cp() + load_hbm_cp_df() + load_memory_offchip_cp()
            + load_biohd())
    # latency_unit: the latency column is NOT one unit across functions. Off-chip
    # memory rows are normalized per hypervector fetched; the BioHD rows are per
    # (prototype, query) comparison; the rest are cycles for one primitive call.
    # The per-function Pareto keeps each internally consistent, but any consumer
    # comparing latency ACROSS functions must read this column first.
    UNIT = {
        "hbm_gather": "cyc/hv", "hbm_gather_cp": "cyc/hv",
        "hbm_gather_cp_df": "cyc/hv", "offchip_baseline_cp": "cyc/hv",
        "biohd_compose_search": "cyc/cmp", "biohd_buffered_base": "cyc/cmp",
    }
    for r in rows:
        r.setdefault("device", DEFAULT_DEVICE)
        r["latency_unit"] = UNIT.get(r["function"], "cyc/call")
    print(f"  merged {len(rows)} design points")
    consistency_check(rows)
    write("master_table.csv", rows)

    front = pareto_per_function(rows)
    write("pareto_table.csv", front)
    print(f"\nwrote master_table.csv ({len(rows)} rows) and pareto_table.csv ({len(front)} rows)\n")

    hdr = f"{'function':<14}{'DP':>4}{'datatype':>9}{'mem':>8}{'lat':>8}{'LUT':>7}{'DSP':>5}{'BRAM':>6}{'src':>12}"
    print(hdr); print("-" * len(hdr))
    for r in front:
        print(f"{r['function']:<14}{str(r['DP']):>4}{str(r['datatype']):>9}{str(r['memory_space']):>8}"
              f"{str(r['latency']):>8}{str(r['LUT']):>7}{str(r['DSP']):>5}{str(r['BRAM18K']):>6}{r['source']:>12}")


if __name__ == "__main__":
    main()
