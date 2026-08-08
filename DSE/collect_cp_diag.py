"""
collect_cp_diag.py -- read the CP diagnostic sweep and answer its one question.

Run AFTER scripts/sweep_cp_diag.tcl:
    cd ~/fpga-hdc-hls
    python3 DSE/collect_cp_diag.py

Reads  proj_cpd_ch_similarity_d<D>_k<KP>_dp<DP>_cp<CP>/sol1/syn/report/ch_similarity_csynth.rpt
Writes DSE/synth_results/cp_diag.csv, and prints a verdict.

WHAT IT LOOKS AT, AND WHY THE LOOP TABLE MATTERS MORE THAN THE LATENCY
    Latency alone cannot distinguish "CP had too little work to divide" from
    "the CP unroll never produced parallel hardware". The csynth LOOP table
    can, because it reports the TRIP COUNT of SEARCH_CLASSES after unrolling:

        CP=8 genuinely applied  ->  trip count falls to about KP/8
        CP=8 replicated but not ->  trip count stays near KP while LUTs still
        scheduled concurrently      rise, which is the signature of paying for
                                    hardware that then runs in sequence

    So this collector pulls the loop table as well as the totals, and the
    verdict is cross-checked against both.

THE THREE ARMS (see scripts/sweep_cp_diag.tcl for the full statement)
    reproduction  D=256,   KP=10               must match the old xc7z020 trend
    main          D=10240, KP 64/256/1024      the CP question, realistic D
    control       D=10240, DP 4/8, CP=1        DP is known-good; proves the
                                               setup is sound, so a flat CP is
                                               attributable to CP

BASELINES
    Each curve is divided by the point with the SAME D and KP and BOTH knobs at
    1. Since no arm ever has DP>1 and CP>1 together, that single point is the
    correct baseline for both the CP curve and the DP curve at that (D, KP).
"""
import os
import re
import glob
import csv
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")
TOP = "ch_similarity"

# Above this, a knob is doing real work. Deliberately loose -- the question is
# direction and magnitude, not a precise threshold.
GOOD_EFF = 0.50

# The legacy configuration. Its CP=8 speedup on xc7z020 was 1.096x; the
# reproduction arm should land near that. Wide tolerance on purpose: a
# different part and a different Vitis version will not match to 3 decimals,
# but they should not disagree about whether CP does anything.
LEGACY = (256, 10)
LEGACY_CP8_SPEEDUP = 1.096
LEGACY_TOL = 0.35          # fractional


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None,
           "latency": None, "cls_trip": None, "dim_trip": None}

    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))

    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))

    # Loop-table rows look like:
    #   |- SEARCH_CLASSES | min | max | iter_lat | ach | tgt | trip | pipelined |
    # Column count varies slightly between Vitis versions, so take the row and
    # pull the numeric fields positionally. Trip count is the last plain
    # integer before the yes/no "Pipelined" cell.
    for name, key in (("SEARCH_CLASSES", "cls_trip"), ("SEARCH_DIM", "dim_trip")):
        m = re.search(r"\|\s*[-+ ]*" + name + r"\s*\|([^\n]*)\|", t)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        nums = [c for c in cells if re.match(r"^\d[\d,]*$", c)]
        if nums:
            out[key] = int(nums[-1].replace(",", ""))
    return out


def load():
    rows = []
    pat = re.compile(r"_d(\d+)_k(\d+)_dp(\d+)_cp(\d+)$")
    for proj in sorted(glob.glob(os.path.join(ROOT, "proj_cpd_*"))):
        m = pat.search(os.path.basename(proj))
        if not m:
            continue
        d, kp, dp, cp = (int(m.group(i)) for i in (1, 2, 3, 4))
        rpts = glob.glob(os.path.join(proj, "sol1", "syn", "report", TOP + "_csynth.rpt"))
        if not rpts:
            rows.append(dict(D=d, KP=kp, DP=dp, CP=cp, status="FAILED / no report"))
            continue
        r = parse_report(rpts[0])
        r.update(D=d, KP=kp, DP=dp, CP=cp, status="ok", report=rpts[0])
        rows.append(r)
    return rows


def derive(rows):
    """Divide every point by the DP=1, CP=1 point at the same (D, KP)."""
    base = {}
    for r in rows:
        if r["DP"] == 1 and r["CP"] == 1 and r.get("latency"):
            base[(r["D"], r["KP"])] = r

    for r in rows:
        b = base.get((r["D"], r["KP"]))
        if not (b and r.get("latency")):
            continue
        knob = "CP" if r["CP"] > 1 else ("DP" if r["DP"] > 1 else "-")
        val = r["CP"] if knob == "CP" else (r["DP"] if knob == "DP" else 1)
        r["knob"] = knob
        r["knob_value"] = val
        r["speedup"] = round(b["latency"] / float(r["latency"]), 3)
        r["efficiency"] = round(r["speedup"] / val, 3)
        if b.get("LUT"):
            r["LUT_growth"] = round(r["LUT"] / float(b["LUT"]), 3)
    return rows


def cell(row, key):
    """Format one table cell.

    dict.get(key, default) returns the DEFAULT only when the key is ABSENT.
    parse_report always creates every key and sets it to None when its regex
    found nothing, so .get("LUT", "-") returns None, not "-" -- and None has no
    __format__ for a width spec. Every cell goes through here instead.
    """
    v = row.get(key)
    return "-" if v is None else str(v)


ROW_FMT = "{:>7}{:>6}{:>4}{:>4}{:>12}{:>9}{:>7}{:>9}{:>7}{:>10}"
ROW_KEYS = ["D", "KP", "DP", "CP", "latency", "speedup", "efficiency",
            "LUT", "LUT_growth", "cls_trip"]


def table(rows, title):
    print("\n---- {} ----".format(title))
    print(ROW_FMT.format("D", "KP", "DP", "CP", "latency", "speedup", "eff",
                         "LUT", "LUTx", "cls_trip"))
    print("-" * 75)
    for r in rows:
        print(ROW_FMT.format(*[cell(r, k) for k in ROW_KEYS]))


def main():
    rows = load()
    if not rows:
        raise SystemExit("No proj_cpd_* projects found. Run scripts/sweep_cp_diag.tcl first.")
    rows.sort(key=lambda r: (r["D"], r["KP"], r["DP"], r["CP"]))
    derive(rows)

    cols = ["D", "KP", "DP", "CP", "knob", "knob_value", "latency", "speedup",
            "efficiency", "LUT", "LUT_growth", "FF", "DSP", "BRAM18K",
            "cls_trip", "dim_trip", "status"]
    if not os.path.isdir(SR):
        os.makedirs(SR)
    out_csv = os.path.join(SR, "cp_diag.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("=" * 75)
    print(" CP DIAGNOSTIC -- does class parallelism do anything?")
    print("=" * 75)

    repro = [r for r in rows if (r["D"], r["KP"]) == LEGACY]
    main_a = [r for r in rows if r["D"] != LEGACY[0] and r["CP"] > 1 or
              (r["D"] != LEGACY[0] and r["DP"] == 1 and r["CP"] == 1)]
    ctrl = [r for r in rows if r["DP"] > 1]

    if repro:
        table(repro, "ARM 1  reproduction (must match the old xc7z020 trend)")
    if main_a:
        table(sorted(main_a, key=lambda r: (r["KP"], r["CP"])),
              "ARM 2  main -- CP swept at D=10240")
    if ctrl:
        table(ctrl, "ARM 3  control -- DP swept at D=10240 (known-good knob)")

    fail = [r for r in rows if r.get("status") != "ok"]
    if fail:
        print("\n!! {} run(s) produced no report:".format(len(fail)))
        for r in fail:
            print("   D={} KP={} DP={} CP={}".format(r["D"], r["KP"], r["DP"], r["CP"]))

    # A report that EXISTS but whose numbers did not parse is a different
    # failure from a run that never produced one, and it needs a different fix.
    # Name the file so it can be inspected directly rather than guessed at.
    unparsed = [r for r in rows if r.get("status") == "ok"
                and (r.get("LUT") is None or r.get("latency") is None)]
    if unparsed:
        print("\n!! {} report(s) found but not fully parsed "
              "(missing LUT and/or latency):".format(len(unparsed)))
        for r in unparsed:
            print("   D={} KP={} DP={} CP={}  latency={}  LUT={}".format(
                r["D"], r["KP"], r["DP"], r["CP"],
                r.get("latency"), r.get("LUT")))
            print("      {}".format(r.get("report", "?")))
        print("   Inspect one with:")
        print("      grep -n -A3 'Utilization Estimates' <report>")
        print("      grep -n -B2 -A6 'Latency (cycles)' <report>")
        print("   A csynth that hit an error still writes a report file, but")
        print("   without the summary tables -- check the sweep log for that tag.")

    # ---------------------------- checks ----------------------------------
    print("\n" + "=" * 75)
    print(" VERDICT")
    print("=" * 75)

    # -- check 0: did the legacy configuration reproduce? ------------------
    r8 = next((r for r in repro if r["CP"] == 8 and "speedup" in r), None)
    if r8 is None:
        print(" [repro] MISSING -- no D=256 KP=10 CP=8 point. Cannot trust the rest.")
    else:
        lo = LEGACY_CP8_SPEEDUP * (1 - LEGACY_TOL)
        hi = LEGACY_CP8_SPEEDUP * (1 + LEGACY_TOL)
        if lo <= r8["speedup"] <= hi:
            print(" [repro] OK -- CP=8 at the legacy size gives {:.2f}x, consistent".format(
                r8["speedup"]))
            print("         with the {:.2f}x measured on xc7z020. Retarget is sound.".format(
                LEGACY_CP8_SPEEDUP))
        else:
            print(" [repro] !! MISMATCH -- CP=8 at the legacy size gives {:.2f}x, but".format(
                r8["speedup"]))
            print("         xc7z020 measured {:.2f}x. Something other than the".format(
                LEGACY_CP8_SPEEDUP))
            print("         library changed (part, tool version, script). INVESTIGATE")
            print("         THIS BEFORE reading anything below.")

    # -- check 1: is the control arm healthy? ------------------------------
    dp_best = [r for r in ctrl if r.get("efficiency") is not None]
    dp_ok = None
    if dp_best:
        best = max(dp_best, key=lambda r: r["efficiency"])
        dp_ok = best["efficiency"] >= GOOD_EFF
        print("\n [control] DP reaches {:.2f} efficiency ({:.2f}x at DP={}, KP={}).".format(
            best["efficiency"], best["speedup"], best["DP"], best["KP"]))
        if dp_ok:
            print("           The setup is sound -- a flat CP is attributable to CP.")
        else:
            print("           !! DP IS ALSO FLAT. The fault is NOT specific to CP.")
            print("           Suspect the sweep, the part, or the tool version.")
            print("           Do not draw any CP conclusion from this run.")
    else:
        print("\n [control] MISSING -- no DP>1 points. CP result will be ambiguous.")

    # -- check 2: the actual question --------------------------------------
    cp_pts = [r for r in rows if r["CP"] == 8 and r["D"] != LEGACY[0]
              and r.get("efficiency") is not None]
    cp_pts.sort(key=lambda r: r["KP"])

    print("\n [main] efficiency at CP=8 as KP grows:")
    for r in cp_pts:
        print("        KP={:<6} efficiency {:.3f}   cls_trip {}".format(
            r["KP"], r["efficiency"], r.get("cls_trip", "-")))

    if dp_ok is False:
        print("\n INCONCLUSIVE -- the control arm failed. Fix that first.")
    elif len(cp_pts) < 2:
        print("\n INCONCLUSIVE -- not enough CP points. Check the FAILED list above.")
    else:
        first, last = cp_pts[0]["efficiency"], cp_pts[-1]["efficiency"]
        if last >= GOOD_EFF and last > first * 1.5:
            print("\n (A) TOO FEW CLASSES. Efficiency climbs {:.2f} (KP={}) -> {:.2f}".format(
                first, cp_pts[0]["KP"], last))
            print("     (KP={}). CP works; it was characterised outside its useful".format(
                cp_pts[-1]["KP"]))
            print("     range. ACTION: report the range where CP pays, and run the")
            print("     full re-characterisation at a realistic KP.")
        elif last < GOOD_EFF and last <= first * 1.5:
            print("\n (B) CP DOES NOT PARALLELISE. Efficiency is {:.2f} at KP={} and".format(
                first, cp_pts[0]["KP"]))
            print("     still {:.2f} at KP={}, while LUTs kept rising. More classes".format(
                last, cp_pts[-1]["KP"]))
            print("     changed nothing, so the shortage of work was never the cause.")
            print("     The outer UNROLL is replicating the datapath without letting")
            print("     the copies run concurrently.")
            print("     ACTION: restructure CP (flatten the class loop, bank `proto`")
            print("     explicitly, or use DATAFLOW) BEFORE the full re-characterisation.")
            print("     Confirm directly: cls_trip should have fallen to about KP/8.")
            print("     If it did not, that is hypothesis (B) shown, not inferred.")
        else:
            print("\n MIXED. Efficiency went {:.2f} -> {:.2f}. Read cls_trip: if it".format(
                first, last))
            print(" falls as CP rises, the unroll IS applying and the remaining loss")
            print(" is the un-parallelised SEED_DIM prologue plus the argmin fold --")
            print(" a real and reportable structural limit rather than a bug.")
    print("=" * 75)
    print("\nwrote", out_csv)


if __name__ == "__main__":
    main()
