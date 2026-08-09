"""
collect_precision_pnr.py -- post-place-and-route confirmation of the precision study.

Run AFTER the Vivado confirmation loop:
    cd ~/fpga-hdc-hls
    python3 DSE/collect_precision_pnr.py

Reads  cliff_confirm_proj_prec_<app>_d<D>_<config>/post_synth_utilization.rpt
Writes DSE/synth_results/precision_pnr.csv

WHY THIS EXISTS
    The headline of the precision study is a block-RAM saving, and csynth's
    block-RAM estimate has now been wrong TWICE on this project, in opposite
    directions:

      capacity crossover   csynth reported 144 BRAM18K for a 40 MB codebook,
                           short by roughly 32x   (UNDER-estimate)
      precision study      csynth reported 64 BRAM18K where Vivado places 32
                           (OVER-estimate)

    Neither error is discoverable from the estimate itself. Any block-RAM claim
    in this paper therefore needs an implementation number behind it, and this
    script produces it in the same shape as the csynth collector so the two can
    be compared row by row.

WHAT IT COUNTS
    Vivado reports physical primitives, not the BRAM18K unit csynth uses:

      RAMB36  a full 36 Kb block   = 2 BRAM18K, occupies 1 tile
      RAMB18  a half 18 Kb block   = 1 BRAM18K, 2 fit in 1 tile

    Both are reported. BRAM18K-equivalent is the like-for-like comparison
    against csynth; TILES is what actually gets consumed on the device, and the
    two can move differently -- which is the interesting part. A design that
    drops from RAMB36 to RAMB18 primitives saves more tiles than its bit count
    alone suggests, because it stops occupying whole tiles for half-full blocks.
"""
import os
import re
import glob
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")

PROJ_PAT = re.compile(r"^cliff_confirm_proj_prec_(image|genome|ts)_d(\d+)_([a-z_]+)$")
CONFIG_ORDER = ["wide", "acc_only", "sim_only", "right", "short"]


def parse_utilization(path):
    """Pull the block-RAM rows out of a Vivado utilization report.

    The summary table looks like:
        | Block RAM Tile    |   16 |     0 |          0 |      2016 |  0.79 |
        |   RAMB36/FIFO*    |   16 |     0 |          0 |      2016 |  0.79 |
        |   RAMB18          |    0 |     0 |          0 |      4032 |  0.00 |

    Matched on the leading label with a used-count immediately after, and the
    FIRST occurrence is taken -- later sections of the report repeat these row
    labels with zeros for other categories.
    """
    t = open(path, "r", errors="ignore").read()
    out = {"tiles": None, "ramb36": None, "ramb18": None,
           "tiles_avail": None, "lut": None, "ff": None}

    def first(label):
        m = re.search(r"\|\s*" + label + r"\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|", t)
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)

    out["tiles"], out["tiles_avail"] = first(r"Block RAM Tile")
    out["ramb36"], _ = first(r"RAMB36/FIFO\*?")
    out["ramb18"], _ = first(r"RAMB18")
    out["lut"], _ = first(r"CLB LUTs\*?")
    if out["lut"] is None:
        out["lut"], _ = first(r"Slice LUTs\*?")
    out["ff"], _ = first(r"CLB Registers")
    if out["ff"] is None:
        out["ff"], _ = first(r"Slice Registers")
    return out


def bram18k_equiv(ramb18, ramb36):
    if ramb18 is None or ramb36 is None:
        return None
    return ramb18 + 2 * ramb36


def load_csynth():
    """The csynth numbers, so the two can be compared side by side."""
    path = os.path.join(SR, "precision_sweep.csv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                out[(r["app"], int(r["D"]), r["config"])] = int(r["BRAM18K"])
            except (ValueError, KeyError):
                pass
    return out


def main():
    csynth = load_csynth()
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, "cliff_confirm_proj_prec_*"))):
        m = PROJ_PAT.match(os.path.basename(d))
        if not m:
            continue
        app, dim, cfg = m.group(1), int(m.group(2)), m.group(3)
        rpt = os.path.join(d, "post_synth_utilization.rpt")
        if not os.path.exists(rpt):
            rows.append(dict(app=app, D=dim, config=cfg, status="no utilization report"))
            continue
        u = parse_utilization(rpt)
        eq = bram18k_equiv(u["ramb18"], u["ramb36"])
        rows.append(dict(
            app=app, D=dim, config=cfg, status="ok",
            RAMB18=u["ramb18"], RAMB36=u["ramb36"],
            BRAM18K_pnr=eq, tiles=u["tiles"], tiles_avail=u["tiles_avail"],
            BRAM18K_csynth=csynth.get((app, dim, cfg)),
            LUT_pnr=u["lut"], FF_pnr=u["ff"]))

    if not rows:
        raise SystemExit("No cliff_confirm_proj_prec_* directories found.")

    for r in rows:
        c, p = r.get("BRAM18K_csynth"), r.get("BRAM18K_pnr")
        if c and p:
            r["csynth_over_by"] = round(c / float(p), 2)

    rows.sort(key=lambda r: (r["app"], r["D"],
                             CONFIG_ORDER.index(r["config"])
                             if r["config"] in CONFIG_ORDER else 99))

    if not os.path.isdir(SR):
        os.makedirs(SR)
    cols = ["app", "D", "config", "RAMB18", "RAMB36", "BRAM18K_pnr", "tiles",
            "tiles_avail", "BRAM18K_csynth", "csynth_over_by", "LUT_pnr",
            "FF_pnr", "status"]
    out_csv = os.path.join(SR, "precision_pnr.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    def cell(r, k):
        v = r.get(k)
        return "-" if v is None else str(v)

    print("=" * 92)
    print(" PRECISION STUDY -- POST-PLACE-AND-ROUTE")
    print("=" * 92)
    fmt = "{:<9}{:<10}{:>8}{:>8}{:>10}{:>8}{:>11}{:>10}"
    print(fmt.format("app", "config", "RAMB18", "RAMB36", "BRAM18K", "tiles",
                     "csynth", "over by"))
    print("-" * 76)
    for r in rows:
        print(fmt.format(r["app"], r["config"], cell(r, "RAMB18"),
                         cell(r, "RAMB36"), cell(r, "BRAM18K_pnr"),
                         cell(r, "tiles"), cell(r, "BRAM18K_csynth"),
                         cell(r, "csynth_over_by")))

    print("\n" + "=" * 92)
    print(" THE SAVING, MEASURED RATHER THAN ESTIMATED")
    print("=" * 92)
    for app in ("image", "genome", "ts"):
        for dim in sorted({r["D"] for r in rows if r["app"] == app}):
            g = {r["config"]: r for r in rows if r["app"] == app and r["D"] == dim}
            if "wide" not in g or "right" not in g:
                continue
            w_, r_ = g["wide"], g["right"]
            if not (w_.get("BRAM18K_pnr") and r_.get("BRAM18K_pnr")):
                continue
            cut = 100.0 * (w_["BRAM18K_pnr"] - r_["BRAM18K_pnr"]) / w_["BRAM18K_pnr"]
            tcut = (100.0 * (w_["tiles"] - r_["tiles"]) / w_["tiles"]
                    if w_.get("tiles") else float("nan"))
            est = (100.0 * (w_["BRAM18K_csynth"] - r_["BRAM18K_csynth"])
                   / w_["BRAM18K_csynth"]) if (w_.get("BRAM18K_csynth")
                                               and r_.get("BRAM18K_csynth")) else float("nan")
            print(" {:<8} D={:<6} BRAM18K {:>3} -> {:<3} = {:5.1f}%   "
                  "tiles {:>3} -> {:<3} = {:5.1f}%   (csynth predicted {:5.1f}%)".format(
                      app, dim, w_["BRAM18K_pnr"], r_["BRAM18K_pnr"], cut,
                      w_["tiles"], r_["tiles"], tcut, est))

            # the mechanism, when it applies
            if w_.get("RAMB36") and not r_.get("RAMB36"):
                print("          `wide` needs {} full 36Kb blocks; `right` fits in {} "
                      "18Kb half-blocks.".format(w_["RAMB36"], r_["RAMB18"]))
                print("          The narrower accumulator drops to a SMALLER PRIMITIVE, "
                      "which a bit count alone does not predict.")

    print("\n" + "=" * 92)
    print(" SCALE CAVEAT")
    print("=" * 92)
    biggest = max((r for r in rows if r.get("tiles") and r.get("tiles_avail")),
                  key=lambda r: r["tiles"], default=None)
    if biggest:
        print(" The largest of these designs uses {} of {} tiles ({:.2f}% of the".format(
            biggest["tiles"], biggest["tiles_avail"],
            100.0 * biggest["tiles"] / biggest["tiles_avail"]))
        print(" device). The percentage saving is real but sits on a small absolute")
        print(" base -- quote the ratio AND the counts, never the ratio alone.")
    print("=" * 92)
    print("\nwrote", out_csv)


if __name__ == "__main__":
    main()
