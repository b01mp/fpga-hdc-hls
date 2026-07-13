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

Outputs (DSE/synth_results/):
    master_table.csv   -- every characterized design point, common schema
    pareto_table.csv   -- non-dominated points per function (the DSE candidate set)

Each sweep varies ONE knob and holds the others at a baseline; this stacks the
slices, giving every row its full knob vector. The estimator fills the interior.
"""
import os
import csv

SR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth_results")

# common schema
COLS = ["function", "DP", "CP", "datatype", "memory_space", "banking",
        "latency", "LUT", "FF", "DSP", "BRAM18K", "URAM", "source"]
OBJ = ["latency", "LUT", "FF", "DSP", "BRAM18K", "URAM"]   # all minimized


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
        rows.append(dict(function=r["function"], DP=r.get("DP"), CP="",
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


def consistency_check(rows):
    """Overlap points (same knobs, different source) should report the same LUT."""
    key = lambda r: (r["function"], str(r["DP"]), r["datatype"], r["memory_space"], str(r["banking"]))
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
    out = []
    funcs = sorted(set(r["function"] for r in rows))
    for fn in funcs:
        pts = [r for r in rows if r["function"] == fn and _num(r.get("latency")) is not None]
        front = [r for r in pts if not any(dominates(o, r) for o in pts if o is not r)]
        out.extend(sorted(front, key=lambda r: (_num(r["latency"]) or 0)))
    return out


def write(name, rows):
    with open(os.path.join(SR, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def main():
    print("loading sweeps:")
    rows = load_parallelism() + load_datatype() + load_memory()
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
