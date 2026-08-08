"""
analyze_scaling.py -- the reduction-scaling ablation, as an ANALYSIS layer.

    cd C:/USC/fpga-hdc-hls
    python DSE/analyze_scaling.py

WHAT THIS IS
    master_table.csv already records, per primitive, what latency and area a
    given knob setting costs. What it does NOT record is what that knob
    actually BOUGHT. This script computes that.

    For every primitive and every knob (DP, CP), it takes the knob=1 point as
    the baseline, walks the knob up, and reports:

        speedup     = latency(1) / latency(n)      -- what you got
        ideal       = n                            -- what a perfectly
                                                      parallel primitive would
                                                      have given
        efficiency  = speedup / n                  -- the fraction you kept
        area growth = LUT(n) / LUT(1)              -- what you paid
        return      = speedup / area growth        -- speedup per unit of area

    A primitive whose work is MAP-shaped (independent per dimension: bind,
    permute, threshold, gather) keeps efficiency near 1. A primitive that ends
    in a REDUCTION (many values collapse to one: similarity, convergence,
    normalize, bundle) cannot -- the combining step does not shrink when you
    add lanes, so efficiency falls and, once the parallel tree costs more to
    build than the serial tail cost to run, the knob can make things WORSE.

    The output is the scaling CLASS of each primitive per knob. That is the
    thing a library owes its users and a DSE owes its search: which knobs are
    worth turning, and which should be pinned at 1.

HONEST LIMITS OF THE CURRENT INPUT
    The parallelism rows in master_table.csv were measured on xc7z020 at
    D=256, K=10. Two consequences, both printed in the report footer:

      * Wrong device. The paper targets U280. Every number here has to be
        re-measured before it is publishable. This run is a PREVIEW whose job
        is to say whether the effect is worth U280 hours.

      * K=10 is small enough that CP=8 nearly fully unrolls the class loop.
        A saturating CP curve at K=10 may be an artifact of there being almost
        no work to divide, not a property of the reduction. Any CP conclusion
        drawn from this file is PROVISIONAL until it is re-run at large K.

    Nothing here is a new measurement. It is arithmetic on measurements that
    already exist, which is exactly why it is cheap to run first.

OUTPUT
    DSE/synth_results/scaling_analysis.csv   -- one row per (function, knob,
                                                knob value)
    DSE/synth_results/scaling_classes.csv    -- one row per (function, knob):
                                                the class verdict
    plus a printed report.
"""
import os
import csv
from collections import defaultdict

SR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth_results")

TAG = os.environ.get("HDC_TAG", "u280").strip() or "u280"

# Input preference, best first. The tagged U280 file wins when it exists,
# because it is the only one measured on the paper's target at a realistic
# problem size. master_table is the legacy xc7z020 / D=256 / KP=10 data and is
# used only as a fallback, with the caveat footer saying so on every run.
CANDIDATES = [
    os.path.join(SR, "characterize_{}.csv".format(TAG)),
    os.path.join(SR, "master_table.csv"),
    os.path.join(SR, "characterize.csv"),
]

KNOBS = ["DP", "CP"]

# Which sweep rows constitute a clean single-knob ablation. The datatype,
# memory and HBM rows vary something else and are excluded on purpose.
ABLATION_SOURCES = {"parallelism"}


# ---------------------------------------------------------------- classify
#
# Thresholds are on efficiency = speedup / knob, evaluated at the LARGEST knob
# value measured. They are deliberately loose: the point is to sort primitives
# into behaviours a DSE can act on, not to grade them.
#
#   negative    the knob makes it SLOWER. Pin at 1. Always.
#   saturating  under 25% of ideal -- you are paying area for nothing.
#   sublinear   25-70%. Real but diminishing; worth searching, not worth maxing.
#   linear      70-115%. The knob does what it says.
#   superlinear over 115%. The knob is changing more than one thing (usually
#               unlocking II=1 or inferring DSPs as well as widening the
#               datapath). Flagged, not celebrated -- it needs an explanation
#               before it goes in a paper.
def classify(speedup, efficiency):
    if speedup < 1.0:
        return "negative"
    if efficiency < 0.25:
        return "saturating"
    if efficiency < 0.70:
        return "sublinear"
    if efficiency <= 1.15:
        return "linear"
    return "superlinear"


CLASS_ORDER = ["superlinear", "linear", "sublinear", "saturating", "negative"]

# A DSE only needs to search a knob whose class is in this set. The others it
# can pin at 1 and lose nothing (or gain).
WORTH_SEARCHING = {"superlinear", "linear", "sublinear"}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_rows():
    """Read the ablation rows from the best available input.

    The tagged characterize_<TAG>.csv is preferred: it is the only file
    measured on the paper's target. master_table.csv is filtered to its
    `parallelism` rows, which are the single-knob ablation slices; its other
    sources vary datatype or memory tier and would be confounds here.
    """
    for path in CANDIDATES:
        if not os.path.exists(path):
            continue
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue

        if "source" in rows[0]:                      # master_table
            rows = [r for r in rows if r.get("source", "") in ABLATION_SOURCES]
            if not rows:
                continue

        for r in rows:
            r.setdefault("device", "xc7z020")
            r.setdefault("datatype", "binary")
        # Drop rows the collector marked as failed -- a missing report becomes
        # a missing latency, which would otherwise divide into a bogus speedup.
        rows = [r for r in rows if r.get("status", "ok") == "ok"]
        if rows:
            return rows, os.path.basename(path)

    raise SystemExit(
        "No input found. Looked for:\n  " + "\n  ".join(CANDIDATES) +
        "\nRun a characterization sweep and its collector first.")


def curves(rows, knob):
    """Yield clean single-knob curves.

    A curve is a set of points that differ ONLY in `knob`. Every other knob is
    held fixed, so the comparison is an ablation and not a confound. Where a
    primitive has a full grid (e.g. convergence and similarity have DP x CP),
    this yields one curve per setting of the other knob -- and the summary
    later uses the slice where the others sit at their minimum, which is the
    cleanest read of the knob in isolation.
    """
    others = [k for k in KNOBS if k != knob]
    groups = defaultdict(list)

    for r in rows:
        v = num(r.get(knob))
        lat = num(r.get("latency"))
        if v is None or lat is None or v <= 0:
            continue
        # D and KP are part of the key: a curve must not mix problem sizes, or
        # the "speedup" would be measuring the workload change, not the knob.
        key = (r.get("function"), r.get("device", ""), r.get("datatype", ""),
               r.get("D", ""), r.get("KP", ""),
               tuple(r.get(o) or "" for o in others))
        groups[key].append((v, r))

    for key, pts in groups.items():
        if len(pts) < 2:
            continue                       # a single point is not a curve
        pts.sort(key=lambda p: p[0])
        if pts[0][0] != 1.0:
            continue                       # no baseline to divide by
        yield key, pts


def analyze():
    rows, src = load_rows()

    detail = []      # every point on every curve
    verdicts = []    # one row per (function, knob): the class

    for knob in KNOBS:
        for (fn, dev, dt, dval, kpval, othv), pts in curves(rows, knob):
            base = pts[0][1]
            lat0 = num(base.get("latency"))
            lut0 = num(base.get("LUT")) or 0.0
            ff0 = num(base.get("FF")) or 0.0
            dsp0 = num(base.get("DSP")) or 0.0
            if not lat0:
                continue

            # Is this the isolated slice -- every other knob parked at 1?
            isolated = all(v in ("", "1", "1.0") for v in othv)

            last = None
            for v, r in pts:
                lat = num(r.get("latency"))
                lut = num(r.get("LUT")) or 0.0
                ff = num(r.get("FF")) or 0.0
                dsp = num(r.get("DSP")) or 0.0

                speedup = lat0 / lat if lat else 0.0
                eff = speedup / v
                area = (lut / lut0) if lut0 else float("nan")
                ret = (speedup / area) if (lut0 and area) else float("nan")

                rec = {
                    "function": fn, "device": dev, "datatype": dt,
                    "D": dval, "KP": kpval,
                    "knob": knob, "knob_value": int(v),
                    "other_knobs": ";".join(
                        "{}={}".format(k, x or "-")
                        for k, x in zip([k for k in KNOBS if k != knob], othv)),
                    "isolated_slice": int(isolated),
                    "latency": lat,
                    "speedup": round(speedup, 3),
                    "ideal_speedup": int(v),
                    "efficiency": round(eff, 3),
                    "LUT": int(lut), "FF": int(ff), "DSP": int(dsp),
                    "LUT_growth": round(area, 3) if lut0 else "",
                    "return_per_area": round(ret, 3) if lut0 else "",
                    "class": classify(speedup, eff),
                }
                detail.append(rec)
                last = rec

            if isolated and last is not None:
                verdicts.append({
                    "function": fn, "device": dev, "datatype": dt,
                    "D": dval, "KP": kpval,
                    "knob": knob,
                    "max_knob": last["knob_value"],
                    "speedup": last["speedup"],
                    "efficiency": last["efficiency"],
                    "LUT_growth": last["LUT_growth"],
                    "return_per_area": last["return_per_area"],
                    "class": last["class"],
                    "dse_action": ("search" if last["class"] in WORTH_SEARCHING
                                   else "pin at 1"),
                })

    return detail, verdicts, src


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def report(detail, verdicts, src):
    print("=" * 84)
    print(" REDUCTION-SCALING ABLATION  --  what each knob actually bought")
    print(" input: {}   ({} curve points, {} verdicts)".format(
        src, len(detail), len(verdicts)))
    print("=" * 84)

    for knob in KNOBS:
        vs = [v for v in verdicts if v["knob"] == knob]
        if not vs:
            continue
        vs.sort(key=lambda v: (CLASS_ORDER.index(v["class"]), -float(v["efficiency"])))

        print("\n---- {} knob (other knobs held at 1) ----".format(knob))
        print("{:<16} {:>5} {:>9} {:>7} {:>8} {:>8}  {:<11} {}".format(
            "primitive", "max", "speedup", "eff", "LUTx", "ret/area",
            "class", "DSE"))
        print("-" * 84)
        for v in vs:
            print("{:<16} {:>5} {:>8.2f}x {:>7.2f} {:>7}x {:>8}  {:<11} {}".format(
                v["function"], v["max_knob"], v["speedup"], v["efficiency"],
                v["LUT_growth"], v["return_per_area"], v["class"],
                v["dse_action"]))

    # ---- what this buys the DSE ---------------------------------------
    per_fn = defaultdict(dict)
    for v in verdicts:
        per_fn[v["function"]][v["knob"]] = v["class"]

    # Stated per AXIS, not as a product over every primitive in the library --
    # no single design instantiates all 19 axes, so a product would be a
    # made-up number. Each dead axis a DSE can pin divides ITS design's search
    # space by the number of levels swept.
    LEVELS = 4          # a knob swept over {1,2,4,8} is 4 settings
    dead = [(v["function"], v["knob"]) for v in verdicts
            if v["class"] not in WORTH_SEARCHING]
    total_axes = len(verdicts)
    live_axes = total_axes - len(dead)

    print("\n---- design-space implication ----")
    print("knob axes characterized                     : {}".format(total_axes))
    print("axes worth searching                        : {}".format(live_axes))
    print("axes a DSE can pin at 1 and lose nothing    : {}".format(len(dead)))
    if dead:
        print("pinned: " + ", ".join("{}.{}".format(f, k) for f, k in dead))
        print("for a design instantiating all {} dead axes, the search space".format(
            len(dead)))
        print("shrinks by {}^{} = {}x".format(
            LEVELS, len(dead), LEVELS ** len(dead)))

    # ---- caveats, printed every run so they cannot be forgotten -------
    # Driven by the data's own provenance columns rather than hardcoded, so
    # they stop firing by themselves once the underlying problem is fixed.
    devs = sorted({v["device"] for v in verdicts if v["device"]})
    ds = sorted({v["D"] for v in verdicts if v.get("D")})
    kps = sorted({v["KP"] for v in verdicts if v.get("KP")})

    print("\n" + "=" * 84)
    print(" CAVEATS -- read before quoting any number above")
    print("=" * 84)
    print(" device(s): {}".format(", ".join(devs) or "unknown"))
    print(" D: {}    KP: {}".format(
        ", ".join(str(x) for x in ds) or "unknown",
        ", ".join(str(x) for x in kps) or "unknown"))

    clean = True
    if any(d.startswith("xc7z") or d.startswith("xczu") for d in devs):
        clean = False
        print("   ! not measured on the U280. Resource counts are not comparable")
        print("     to the paper's target, and the xc7z020 sweep contains points")
        print("     (gemm/matvec at DP=8, 256 DSP) that cannot be built on it.")
    if not ds or not kps:
        clean = False
        print("   ! this input carries no D/KP provenance columns, so it is the")
        print("     legacy sweep: xc7z020, D=256, KP=10. Treat every number as")
        print("     a preview, and the CP verdicts as PROVISIONAL -- at KP=10")
        print("     CP=8 has almost no work to divide, so a saturating CP curve")
        print("     is ambiguous. Resolve with scripts/sweep_cp_diag.tcl.")
    if any(int(x) <= 1024 for x in ds if str(x).isdigit()):
        clean = False
        print("   ! D is below 10240. HDC dimensions this small are not")
        print("     representative, and a reviewer will discount the section.")
    if any(int(x) <= 10 for x in kps if str(x).isdigit()):
        clean = False
        print("   ! KP is 10 or fewer. CP=8 on a 10-iteration class loop has")
        print("     almost nothing to divide, so a saturating CP curve here is")
        print("     ambiguous between 'the knob does not work' and 'there was no")
        print("     work to give it'. CP verdicts are PROVISIONAL.")
        print("     Resolve with scripts/sweep_cp_diag.tcl.")
    if clean:
        print("   - provenance is clean: paper target, realistic D, adequate KP.")
    sup = [v["function"] for v in verdicts if v["class"] == "superlinear"]
    if sup:
        print("   ! superlinear: {}. Speedup above ideal means the knob is".format(
            ", ".join(sorted(set(sup)))))
        print("     changing more than the datapath width (II, DSP inference).")
        print("     Explain it or report those separately -- unexplained, it")
        print("     reads as a measurement bug.")
    print("=" * 84)


def main():
    detail, verdicts, src = analyze()

    d_cols = ["function", "device", "datatype", "D", "KP", "knob", "knob_value",
              "other_knobs", "isolated_slice", "latency", "speedup",
              "ideal_speedup", "efficiency", "LUT", "FF", "DSP",
              "LUT_growth", "return_per_area", "class"]
    v_cols = ["function", "device", "datatype", "D", "KP", "knob", "max_knob", "speedup",
              "efficiency", "LUT_growth", "return_per_area", "class",
              "dse_action"]

    p1 = os.path.join(SR, "scaling_analysis.csv")
    p2 = os.path.join(SR, "scaling_classes.csv")
    write_csv(p1, detail, d_cols)
    write_csv(p2, verdicts, v_cols)

    report(detail, verdicts, src)
    print("\nwrote {}".format(p1))
    print("wrote {}".format(p2))


if __name__ == "__main__":
    main()
