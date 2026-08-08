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
import math
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

# Pre-fix U280 measurement at the legacy size, kept for the record only.
# The reproduction arm originally asserted against the xc7z020 number (1.096x)
# to detect an ENVIRONMENT change. That assertion is now void: the CP
# implementation was deliberately restructured, so the legacy-size result is
# SUPPOSED to differ. The arm is still run and printed -- it is the cheapest
# place to see the change at a glance -- but it no longer fails the run.
LEGACY_PREFIX_U280 = 0.581      # what this configuration measured before the fix
LEGACY_PREFIX_XC7Z = 1.096      # what xc7z020 measured, on the old code


def cp_ideal(K, CP):
    """Ideal speedup from CP groups, which is NOT simply CP.

    The class loop runs in ceil(K/CP) groups. When K is not a multiple of CP the
    final group is partial, and the design still pays for a whole group, so the
    best achievable speedup is K / ceil(K/CP), not CP.

    This matters at the legacy size: K=10 with CP=8 is TWO groups, so the ideal
    is 10/2 = 5x, not 8x. Scoring 4.82x against 8 gives a misleading 0.60
    efficiency; scoring it against 5 gives 0.96, which is what actually
    happened. At K=64/256/1024 with CP<=8 the division is exact and this
    reduces to CP.
    """
    groups = int(math.ceil(K / float(CP)))
    return K / float(groups)


def parse_report(path):
    t = open(path, "r", errors="ignore").read()
    out = {"BRAM18K": None, "DSP": None, "FF": None, "LUT": None, "URAM": None,
           "latency": None, "cls_trip": None, "dim_trip": None,
           "cls_loop": None, "dim_loop": None}

    m = re.search(r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|", t)
    if m:
        out.update(BRAM18K=int(m.group(1)), DSP=int(m.group(2)),
                   FF=int(m.group(3)), LUT=int(m.group(4)), URAM=int(m.group(5)))

    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|", t, re.S)
    if m:
        out["latency"] = int(m.group(2).replace(",", ""))

    # ---- loop table -------------------------------------------------------
    #
    # Rows look like:
    #   |- SEARCH_CLASSES_SEARCH_DIM | min | max | iter | ach | tgt | trip | yes |
    #
    # NOTE THE NAME. Vitis MERGES a nested loop pair into one entry named
    # OUTER_INNER when it flattens them. An earlier version of this parser
    # matched the loop name exactly ("SEARCH_CLASSES" followed by a column
    # separator) and therefore matched nothing at all on a flattened design --
    # every cls_trip came back empty.
    #
    # That merge is not a parsing nuisance, it is EVIDENCE: a flattened
    # SEARCH_CLASSES_SEARCH_DIM means the outer loop no longer exists as a
    # separate entity, so an UNROLL factor on it has nothing to apply to. The
    # actual loop name is therefore recorded alongside the trip count.
    #
    # Matching is now by PREFIX so both the flattened and unflattened forms are
    # found, and the trip count is taken positionally (the last plain integer
    # before the yes/no "Pipelined" cell) because the column count varies
    # between Vitis versions.
    for prefix, tkey, nkey in (("SEARCH_CLASSES", "cls_trip", "cls_loop"),
                               ("CLASS_GROUP",    "cls_trip", "cls_loop"),
                               ("SEARCH_DIM",     "dim_trip", "dim_loop")):
        if out.get(tkey) is not None:
            continue                      # an earlier prefix already matched
        for line in t.splitlines():
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            if not cells:
                continue
            label = cells[0].lstrip("-+ ").strip()
            if not label.startswith(prefix):
                continue
            nums = [c for c in cells[1:] if re.match(r"^\d[\d,]*$", c)]
            if nums:
                out[tkey] = int(nums[-1].replace(",", ""))
                out[nkey] = label
            break

    # Fallback: HLS renames loops as it restructures them, so a fixed prefix
    # list will always eventually miss one. If nothing matched, take the loop
    # row with the LARGEST trip count -- that is the dominant loop whatever it
    # ended up being called -- and record its real name. An unrecognised name
    # is information, not an error.
    if out.get("cls_trip") is None:
        best_label, best_trip = None, -1
        in_loop_table = False
        for line in t.splitlines():
            if "Loop Name" in line:
                in_loop_table = True
                continue
            if not in_loop_table or "|" not in line:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip() != ""]
            if len(cells) < 3:
                continue
            label = cells[0].lstrip("-+ ").strip()
            if not label or label.startswith("Loop"):
                continue
            nums = [c for c in cells[1:] if re.match(r"^\d[\d,]*$", c)]
            if not nums:
                continue
            trip = int(nums[-1].replace(",", ""))
            if trip > best_trip:
                best_trip, best_label = trip, label
        if best_label is not None:
            out["cls_trip"] = best_trip
            out["cls_loop"] = best_label + " (auto)"
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
        ideal = cp_ideal(r["KP"], r["CP"]) if knob == "CP" else float(val)
        r["knob"] = knob
        r["knob_value"] = val
        r["ideal"] = round(ideal, 3)
        r["speedup"] = round(b["latency"] / float(r["latency"]), 3)
        r["efficiency"] = round(r["speedup"] / ideal, 3)
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
            "ideal", "cls_trip", "cls_loop", "dim_trip", "dim_loop", "status"]
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

    # -- check 0: the legacy-size configuration, for the record ------------
    #
    # This is no longer a pass/fail assertion. It asserted against the xc7z020
    # number while the question was "did the ENVIRONMENT change?". Once the CP
    # implementation was deliberately restructured, a difference here is the
    # intended outcome, not a warning -- so it is reported and not judged.
    r8 = next((r for r in repro if r["CP"] == 8 and "speedup" in r), None)
    if r8 is None:
        print(" [legacy] no D=256 KP=10 CP=8 point in this run.")
    else:
        print(" [legacy] D=256, KP=10, CP=8 -> {:.2f}x".format(r8["speedup"]))
        print("          for reference: {:.2f}x pre-fix on this same U280 setup,".format(
            LEGACY_PREFIX_U280))
        print("          {:.2f}x on the old xc7z020 measurements.".format(
            LEGACY_PREFIX_XC7Z))
        print("          NOTE: K=10 with CP=8 is two groups, so the ideal here is")
        print("          10/2 = 5.00x, not 8x. Efficiency above is scored on that.")

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
        worst = min(p["efficiency"] for p in cp_pts)
        if worst >= 0.80:
            print("\n (C) CP SCALES. Efficiency is {:.2f} or better at EVERY".format(worst))
            print("     prototype count measured ({} .. {}), so the knob delivers".format(
                cp_pts[0]["KP"], cp_pts[-1]["KP"]))
            print("     what it advertises across the whole range rather than only")
            print("     in a narrow regime.")
            best = max(cp_pts, key=lambda p: p["speedup"])
            print("     Best point: {:.2f}x at KP={}, CP={}, for {}x the LUTs.".format(
                best["speedup"], best["KP"], best["CP"],
                best.get("LUT_growth", "?")))
            print("     ACTION: none. Proceed to the full characterisation --")
            print("     phase 3 of scripts/sweep_characterize.tcl.")
        elif last >= GOOD_EFF and last > first * 1.5:
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
