"""
collect_datatype.py -- gather the datatype sweep (Novelty 1) into one CSV.

Run AFTER scripts/synth_datatype.tcl:
    cd ~/fpga-hdc-hls
    python3 DSE/collect_datatype.py

Reads:
    proj_dt_<top>/sol1/syn/report/<top>_csynth.rpt

Writes:
    DSE/synth_results/datatype_sweep.csv

There was previously no collector for this sweep -- the datatype rows in
benchmarks.csv were assembled by hand, which is why they carried no device or
tool provenance. Every row here records `part` and `tool_version` straight from
the report header, because resource counts are not comparable across devices and
latency/timing estimates are not comparable across Vitis versions.

WHAT THE SWEEP HOLDS CONSTANT: D=256, DP=8, CP=2 (search only), part, clock.
The ONLY variable is the datatype family, so any difference between two rows of
the same primitive is the datatype's doing.

WHAT IT DELIBERATELY DOES NOT HOLD CONSTANT: accumulator and score widths. The
width required is *determined by* the element type -- a binary score needs
~log2(D) bits, an int32 dot product needs 32+32+log2(D). Forcing one width on
every family would make binary wasteful and int32 numerically wrong. The width
is part of the datatype's cost. See the header of src/top_datatype.cpp.
"""
import os
import re
import csv
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# top name -> (primitive, family). CP is 2 for search, 1 elsewhere (see the tcl).
PRIMITIVE = {"bind": "bind", "threshold": "threshold", "sim": "similarity"}
FAMILIES = ("binary", "bipolar", "fixed", "integer", "pow2")

# Per-family notes carried into the CSV so a reader knows what the row measures.
OP_NOTE = {
    ("bind", "binary"):       "XOR",
    ("bind", "bipolar"):      "sign multiply",
    ("bind", "fixed"):        "real multiply",
    ("bind", "integer"):      "integer multiply",
    ("bind", "pow2"):         "sign XOR + exponent add",
    ("threshold", "binary"):  "majority vote",
    ("threshold", "bipolar"): "sign",
    ("threshold", "fixed"):   "passthrough",
    ("threshold", "integer"): "passthrough",
    ("threshold", "pow2"):    "round to nearest 2^k",
    ("similarity", "binary"): "Hamming / argmin",
    ("similarity", "bipolar"):"dot / argmax",
    ("similarity", "fixed"):  "dot / argmax",
    ("similarity", "integer"):"dot / argmax (full multiply)",
    ("similarity", "pow2"):   "dot / argmax (shift, no multiply)",
}


def split_top(top):
    """bind_binary_top -> ('bind', 'binary');  sim_pow2_top -> ('similarity', 'pow2')."""
    name = top[:-4] if top.endswith("_top") else top
    for fam in FAMILIES:
        suffix = "_" + fam
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            return PRIMITIVE.get(stem, stem), fam
    return name, ""


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {k: None for k in ("BRAM18K", "DSP", "FF", "LUT", "URAM", "latency_cycles",
                             "interval", "target_ns", "estimated_ns",
                             "tool_version", "part")}
    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|"
                  r"\s*[\d.]+\s*[num]s\|\s*[\d.]+\s*[num]s\|\s*(\d[\d,]*)\|\s*(\d[\d,]*)\|",
                  t, re.S)
    if m:
        out["latency_cycles"] = int(m.group(2).replace(",", ""))
        out["interval"] = int(m.group(4).replace(",", ""))
    m = re.search(r"\|\s*ap_clk\s*\|\s*([\d.]+)\s*ns\s*\|\s*([\d.]+)\s*ns", t)
    if m:
        out["target_ns"] = float(m.group(1))
        out["estimated_ns"] = float(m.group(2))
    m = re.search(r"^\*\s*Version:\s*(\S+)", t, re.M)
    if m:
        out["tool_version"] = m.group(1)
    m = re.search(r"^\*\s*Target device:\s*(\S+)", t, re.M)
    if m:
        out["part"] = m.group(1)
    return out


COLS = ["config", "primitive", "family", "op", "D", "DP", "CP",
        "latency_cycles", "interval", "target_ns", "estimated_ns", "fmax_MHz",
        "LUT", "FF", "DSP", "BRAM18K", "URAM", "part", "tool_version", "status"]


def main():
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, "proj_dt_*"))):
        top = os.path.basename(d)[len("proj_dt_"):]
        prim, fam = split_top(top)
        rpts = (glob.glob(os.path.join(d, "sol1", "syn", "report", top + "_csynth.rpt"))
                or glob.glob(os.path.join(d, "sol1", "syn", "report", "*_csynth.rpt")))
        if not rpts:
            rows.append(dict(config="datatype", primitive=prim, family=fam,
                             status="FAILED / no report"))
            continue
        r = parse_report(rpts[0])
        est = r.get("estimated_ns")
        r.update(config="datatype", primitive=prim, family=fam,
                 op=OP_NOTE.get((prim, fam), ""),
                 D=256, DP=8, CP=(2 if prim == "similarity" else 1),
                 fmax_MHz=(round(1000.0 / est, 1) if est else None),
                 status="ok")
        rows.append(r)

    order = {"bind": 0, "threshold": 1, "similarity": 2}
    fam_order = {f: i for i, f in enumerate(FAMILIES)}
    rows.sort(key=lambda r: (order.get(r.get("primitive"), 9),
                             fam_order.get(r.get("family"), 9)))

    out_csv = os.path.join(ROOT, "DSE", "synth_results", "datatype_sweep.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    print("wrote", out_csv, "\n")

    hdr = ("%-11s%-9s%-34s%8s%8s%6s%7s%8s" %
           ("primitive", "family", "op", "LUT", "FF", "DSP", "BRAM", "fMHz"))
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print("%-11s%-9s%-34s%8s%8s%6s%7s%8s" % (
            r.get("primitive", ""), r.get("family", ""), r.get("op", ""),
            r.get("LUT", "-"), r.get("FF", "-"), r.get("DSP", "-"),
            r.get("BRAM18K", "-"), r.get("fmax_MHz", "-")))

    vers = sorted({r.get("tool_version") for r in rows if r.get("tool_version")})
    parts = sorted({r.get("part") for r in rows if r.get("part")})
    print("\npart(s): %s    Vitis: %s" % (", ".join(parts) or "?", ", ".join(vers) or "?"))
    if len(vers) > 1 or len(parts) > 1:
        print("WARNING: this table mixes parts or tool versions -- not comparable.")


if __name__ == "__main__":
    main()
