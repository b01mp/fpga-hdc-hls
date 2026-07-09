"""
calibrate.py -- validate the estimator against real Vitis csynth reports and fit
its cost constants.

The estimator's numbers are only trustworthy if they track real synthesis. This
module:
  1. parses a Vitis HLS <top>_csynth.rpt into actual metrics,
  2. compares predicted vs actual (per metric, with error %),
  3. suggests scale factors for the constants in models/datatypes.py so the model
     tracks reality.

It is fully functional now, but it has nothing to chew on until the architecture
parameters are synthesized -- feed it (params, report_path) pairs once you have
csynth reports. See __main__ for the expected usage.

IMPORTANT: Vitis report table headers vary slightly by version. The parser is
best-effort; verify the fields against your FIRST real report and adjust
_METRIC_ALIASES if any come back None.
"""
import re
from .estimate import estimate
from .models import primitives as P


# Vitis reports resources under version-dependent column names.
_METRIC_ALIASES = {
    "LUT":      ["LUT"],
    "FF":       ["FF"],
    "DSP":      ["DSP48E", "DSP"],
    "BRAM_18K": ["BRAM_18K"],
    "URAM":     ["URAM"],
}


def _to_int(s):
    s = str(s).replace(",", "").strip()
    try:
        return int(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# report parsing
# --------------------------------------------------------------------------- #
def parse_csynth_report(path):
    """Best-effort parse of a Vitis HLS <top>_csynth.rpt.

    Returns a dict with keys latency_cycles, LUT, FF, DSP, BRAM_18K, URAM
    (any field that can't be found is None).
    """
    with open(path, "r", errors="ignore") as fh:
        text = fh.read()

    out = {"latency_cycles": None, "LUT": None, "FF": None,
           "DSP": None, "BRAM_18K": None, "URAM": None}
    lines = text.splitlines()

    # --- utilization: find the header row (has LUT and FF), then the Total row
    header_idx, cols = None, []
    for i, ln in enumerate(lines):
        if "|" in ln and "LUT" in ln and "FF" in ln:
            cols = [c.strip() for c in ln.strip().strip("|").split("|")]
            header_idx = i
            break
    if header_idx is not None:
        for ln in lines[header_idx + 1:]:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and cells[0].lower() == "total":
                row = dict(zip(cols, cells))
                for metric, aliases in _METRIC_ALIASES.items():
                    for alias in aliases:
                        if alias in row:
                            out[metric] = _to_int(row[alias])
                            break
                break

    # --- latency: grab the 'max' cycles from the Latency (cycles) summary
    m = re.search(r"Latency\s*\(cycles\).*?\|\s*(\d[\d,]*)\s*\|\s*(\d[\d,]*)\s*\|",
                  text, re.S)
    if m:
        out["latency_cycles"] = _to_int(m.group(2))     # second column = max
    return out


# --------------------------------------------------------------------------- #
# predict / compare / fit
# --------------------------------------------------------------------------- #
def predict_metrics(params):
    """Estimator's prediction in the SAME units the report uses (BRAM as 18K)."""
    m = estimate(params)
    r = m["resources"]
    return {
        "latency_cycles": m["latency_cycles"],
        "LUT": r["LUT"], "FF": r["FF"], "DSP": r["DSP"],
        "BRAM_18K": r["BRAM36"] * 2,        # model counts 36K blocks; report is 18K
        "URAM": r["URAM"],
    }


_METRICS = ("latency_cycles", "LUT", "FF", "DSP", "BRAM_18K", "URAM")


def compare(params, actual):
    """Per-metric predicted vs actual with error %."""
    pred = predict_metrics(params)
    rows = {}
    for k in _METRICS:
        a, p = actual.get(k), pred.get(k)
        err = None if (a in (None, 0) or p is None) else 100.0 * (p - a) / a
        rows[k] = {"predicted": p, "actual": a, "error_pct": err}
    return rows


def fit_scale(samples, metrics=("latency_cycles", "LUT", "FF", "DSP")):
    """Suggested multiplier per metric = sum(actual)/sum(predicted).

    samples: list of (params, actual_metrics). Multiply the model's constants by
    the returned factor to line the estimator up with synthesis.
    """
    acc = {m: [0.0, 0.0] for m in metrics}     # metric -> [pred_sum, actual_sum]
    for params, actual in samples:
        pred = predict_metrics(params)
        for m in metrics:
            a, p = actual.get(m), pred.get(m)
            if a and p:
                acc[m][0] += p
                acc[m][1] += a
    return {m: (acc[m][1] / acc[m][0] if acc[m][0] else None) for m in metrics}


def samples_from_reports(pairs):
    """Turn [(params, report_path), ...] into [(params, actual_metrics), ...]."""
    return [(params, parse_csynth_report(path)) for params, path in pairs]


def calibrate(samples):
    """Print predicted-vs-actual errors and suggested constant scale factors.

    samples: list of (params_dict, actual_metrics_dict).
    """
    print("== calibration: predicted vs actual ==")
    for i, (params, actual) in enumerate(samples):
        tag = f"dp={params.get('dp')} family={params.get('family')} elem_bits={params.get('elem_bits')}"
        print(f"\n[sample {i}] {tag}")
        for k, row in compare(params, actual).items():
            if row["error_pct"] is None:
                continue
            print(f"  {k:<15} pred={row['predicted']:>12,.0f}  "
                  f"actual={row['actual']:>12,.0f}  err={row['error_pct']:+7.1f}%")

    print("\n== suggested constant scale factors (actual / predicted) ==")
    for m, s in fit_scale(samples).items():
        if s:
            print(f"  {m:<15} x {s:.3f}")
        else:
            print(f"  {m:<15} (no data)")


# --------------------------------------------------------------------------- #
# Per-primitive calibration against real csynth.
#
# Our first synthesis was per-primitive (each category top wraps ONE primitive at
# D=256, binary, on xc7z020 @ 10ns), so we calibrate the per-primitive cost models
# in models/primitives.py -- NOT the full-pipeline estimate(). Numbers below are
# from DSE/synth_results/{dp1_baseline, dp8}.
# --------------------------------------------------------------------------- #
SYNTH_DATA = {
    #  name         (DP, CP): dict(cycles, lut, ff)
    "bind":       {(1, 1): dict(cycles=258,  lut=63,   ff=20),
                   (8, 1): dict(cycles=35,   lut=82,   ff=20)},
    "threshold":  {(1, 1): dict(cycles=258,  lut=100,  ff=52),
                   (8, 1): dict(cycles=35,   lut=378,  ff=52)},
    "gather":     {(1, 1): dict(cycles=258,  lut=61,   ff=20),
                   (8, 1): dict(cycles=34,   lut=45,   ff=18)},
    "similarity": {(1, 1): dict(cycles=2569, lut=539,  ff=201),
                   (8, 2): dict(cycles=341,  lut=1376, ff=237)},
}
_SYNTH_D, _SYNTH_K, _SYNTH_ACC, _SYNTH_SIM = 256, 10, 32, 32


def predict_primitive(name, DP, CP):
    """Estimator prediction (cycles, LUT, FF) for one primitive at the synth sizes."""
    if name == "bind":
        c, r = P.cost_bind(_SYNTH_D, DP, "binary", 1)
    elif name == "threshold":
        c, r = P.cost_threshold(_SYNTH_D, DP, _SYNTH_ACC)
    elif name == "gather":
        c, r = P.cost_gather(_SYNTH_D, DP)
    elif name == "similarity":
        c, r = P.cost_similarity(_SYNTH_D, _SYNTH_K, DP, CP, "binary", 1, _SYNTH_SIM)
    else:
        raise ValueError(name)
    return c, r.lut, r.ff


def _errpct(pred, act):
    return None if not act else 100.0 * (pred - act) / act


def calibrate_primitives():
    """Print predicted vs actual (cycles + LUT) for each synthesized primitive."""
    hdr = (f"{'primitive':<11}{'DP':>3}{'CP':>3} |{'cyc pred':>9}{'cyc act':>9}{'err%':>7} "
           f"|{'LUT pred':>9}{'LUT act':>9}{'err%':>7}")
    print(hdr)
    print("-" * len(hdr))
    for name, pts in SYNTH_DATA.items():
        for (DP, CP), act in pts.items():
            pc, plut, _ = predict_primitive(name, DP, CP)
            ce, le = _errpct(pc, act["cycles"]), _errpct(plut, act["lut"])
            print(f"{name:<11}{DP:>3}{CP:>3} |{pc:>9.0f}{act['cycles']:>9}{ce:>6.0f}% "
                  f"|{plut:>9.0f}{act['lut']:>9}{le:>6.0f}%")


if __name__ == "__main__":
    calibrate_primitives()
