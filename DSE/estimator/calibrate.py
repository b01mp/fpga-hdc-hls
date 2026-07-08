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


if __name__ == "__main__":
    print(__doc__)
    print("No calibration data yet. Once the architecture parameters are synthesized,")
    print("collect (params, report_path) pairs and call:")
    print()
    print("    from estimator.calibrate import samples_from_reports, calibrate")
    print("    pairs = [({'dp': 8, 'family': 'binary'}, 'proj_synth_bind/sol1/syn/report/encoding_bind_top_csynth.rpt')]")
    print("    calibrate(samples_from_reports(pairs))")
