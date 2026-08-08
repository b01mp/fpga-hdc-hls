"""
collect_characterize.py -- gather the per-primitive parallelism sweep into one CSV.

Run AFTER scripts/sweep_characterize.tcl (either phase, or both):
    cd ~/fpga-hdc-hls
    python3 DSE/collect_characterize.py

Reads  proj_ch_<fn>_d<D>_k<KP>_dp<N>_cp<M>/sol1/syn/report/<fn>_csynth.rpt
Writes DSE/synth_results/characterize_<tag>.csv        (tag from HDC_TAG, default u280)

WHY A TAGGED OUTPUT FILE
    The original sweep ran on xc7z020 at D=256, KP=10 and wrote characterize.csv.
    Resource counts are not comparable across parts and latency estimates are
    not comparable across tool versions, so the new U280 numbers get their own
    file rather than overwriting the old one. Both stay on disk, provenance
    stays obvious, and merge_table.py can keep an honest `device` column.

    The legacy proj_ch_<fn>_dp<N>_cp<M> directories (no _d/_k fields) are still
    read, and are tagged with their real configuration so that a row can never
    be mistaken for a new one. If any are found, the summary says so.

PROVENANCE COLUMNS
    Every row records D, KP, device and clock period alongside the measurement.
    A characterization table whose rows do not say what machine and what problem
    size produced them is how the D=256 / xc7z020 numbers ended up being quoted
    long after they stopped being the target.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")

TAG = os.environ.get("HDC_TAG", "u280").strip() or "u280"
PART = os.environ.get("HDC_PART", "xcu280-fsvh2892-2L-e").strip()
PERIOD = os.environ.get("HDC_PERIOD", "3.333").strip()

# The legacy sweep's configuration, for rows whose directory name predates the
# _d/_k fields. Recorded explicitly rather than left blank so nothing downstream
# has to guess.
LEGACY = {"D": 256, "KP": 10, "device": "xc7z020clg484-1", "period_ns": "10.0"}

NEW_PAT = re.compile(r"^proj_ch_(ch_[a-z_]+)_d(\d+)_k(\d+)_dp(\d+)_cp(\d+)$")
OLD_PAT = re.compile(r"^proj_ch_(ch_[a-z_]+)_dp(\d+)(?:_cp(\d+))?$")


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None,
           "URAM": None, "latency": None, "interval": None}

    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))

    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))
    return out


def scan():
    rows, legacy_seen = [], 0
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_ch_*"))):
        base = os.path.basename(proj)

        m = NEW_PAT.match(base)
        if m:
            fn = m.group(1)
            meta = {"D": int(m.group(2)), "KP": int(m.group(3)),
                    "DP": int(m.group(4)), "CP": int(m.group(5)),
                    "device": PART, "period_ns": PERIOD, "config": TAG}
        else:
            m = OLD_PAT.match(base)
            if not m:
                continue
            legacy_seen += 1
            fn = m.group(1)
            meta = {"D": LEGACY["D"], "KP": LEGACY["KP"],
                    "DP": int(m.group(2)),
                    "CP": int(m.group(3)) if m.group(3) else 1,
                    "device": LEGACY["device"], "period_ns": LEGACY["period_ns"],
                    "config": "legacy"}

        rpt = os.path.join(proj, "sol1", "syn", "report", fn + "_csynth.rpt")
        if not os.path.exists(rpt):
            cand = glob.glob(os.path.join(proj, "sol1", "syn", "report", "*_csynth.rpt"))
            # Only fall back to a bare glob if there is exactly one report -- a
            # loose glob is how sub-module reports got picked up before, which
            # produced latencies of 6 and 82 cycles and BRAM counts of 0.
            rpt = cand[0] if len(cand) == 1 else None

        if not rpt:
            r = dict(meta)
            r.update(function=fn.replace("ch_", ""), status="FAILED / no report")
            rows.append(r)
            continue

        r = parse_report(rpt)
        r.update(meta)
        r.update(function=fn.replace("ch_", ""), status="ok")
        rows.append(r)

    return rows, legacy_seen


def main():
    rows, legacy_seen = scan()
    if not rows:
        raise SystemExit("No proj_ch_* projects found. Run scripts/sweep_characterize.tcl first.")

    rows.sort(key=lambda r: (r.get("config", ""), r.get("function", ""),
                             r.get("DP") or 0, r.get("CP") or 0))

    cols = ["function", "config", "device", "period_ns", "D", "KP", "DP", "CP",
            "latency", "LUT", "FF", "DSP", "BRAM18K", "URAM", "status"]

    if not os.path.isdir(SR):
        os.makedirs(SR)

    # New rows go to the tagged file. Legacy rows are kept separate so a stale
    # xc7z020 measurement can never silently join a U280 table.
    new_rows = [r for r in rows if r.get("config") != "legacy"]
    old_rows = [r for r in rows if r.get("config") == "legacy"]

    out_csv = os.path.join(SR, "characterize_{}.csv".format(TAG))
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in new_rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("wrote", out_csv, "({} rows)".format(len(new_rows)))
    if old_rows:
        print("note: {} legacy proj_ch_*_dp*_cp* directories found "
              "(xc7z020, D=256, KP=10).".format(len(old_rows)))
        print("      They are NOT written to the tagged file. The original")
        print("      characterize.csv still holds them.")

    hdr = "{:<16}{:>7}{:>6}{:>4}{:>4}{:>12}{:>9}{:>6}{:>7}  status".format(
        "function", "D", "KP", "DP", "CP", "latency", "LUT", "DSP", "BRAM")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in new_rows:
        print("{:<16}{:>7}{:>6}{:>4}{:>4}{:>12}{:>9}{:>6}{:>7}  {}".format(
            str(r.get("function", "")), str(r.get("D", "")), str(r.get("KP", "")),
            str(r.get("DP", "")), str(r.get("CP", "")), str(r.get("latency", "")),
            str(r.get("LUT", "")), str(r.get("DSP", "")), str(r.get("BRAM18K", "")),
            r.get("status", "")))

    bad = [r for r in new_rows if r.get("status") != "ok"]
    if bad:
        print("\n!! {} run(s) produced no usable report:".format(len(bad)))
        for r in bad:
            print("   {} DP={} CP={}".format(r.get("function"), r.get("DP"), r.get("CP")))

    print("\nnext: python3 DSE/analyze_scaling.py")


if __name__ == "__main__":
    main()
