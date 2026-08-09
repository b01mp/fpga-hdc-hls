"""
join_precision_pareto.py -- the accuracy/area Pareto. No synthesis required.

    cd C:/USC/fpga-hdc-hls
    python DSE/join_precision_pareto.py

Joins the two halves of the same axis, bits per stored element:

    DSE/synth_results/capacity_sweep.csv      what a width COSTS   (measured)
    DSE/synth_results/precision_accuracy.csv  what a width BUYS    (modelled)

Writes DSE/synth_results/precision_pareto.csv

WHY THIS IS THE FIGURE THAT MATTERS
    The capacity crossover established that on-chip footprint scales with bits
    per element, and that the U280's block-RAM ceiling therefore lands at a
    different library size for every precision. The precision study established
    what accuracy each of those precisions delivers. Separately they are two
    tables; together they answer the question a designer actually has:

        for a fixed device, how many references can I hold, and at what accuracy?

    That framing is stronger than "bits vs AUC" because the x-axis becomes a
    capability -- library size -- rather than an implementation detail.

HOW STORAGE IS DERIVED
    Bytes per reference is exact: D * bits / 8. No packing assumptions.

    Block count is measured where the capacity sweep covers the width (X in
    {1, 8, 32}) and scaled linearly from the X=1 measurement elsewhere. The
    measured points carry ~2% packing overhead over the ideal D*X/18432, and
    that overhead is roughly constant in X, so linear scaling is sound within a
    few percent. Rows say which they are.

    Maximum library size is the device ceiling divided by blocks per reference.
    The capacity study confirmed this model against Vivado at the int32
    boundary to within 0.28%, so it is not a guess -- but it is a model, and
    rows are labelled accordingly.
"""
import os
import csv
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(ROOT, "DSE", "synth_results")

CAPACITY = os.path.join(SR, "capacity_sweep.csv")
ACCURACY = os.path.join(SR, "precision_accuracy.csv")
OUT = os.path.join(SR, "precision_pareto.csv")

U280_BRAM18K = 4032          # 4032 x 18 Kb = 9.07 MB
D_ANCHOR = 10240             # the dimension both studies share


def read_csv(path):
    if not os.path.exists(path):
        raise SystemExit(
            "missing {}\nRun the sweep that produces it first.".format(path))
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def num(x, cast=float):
    try:
        return cast(x)
    except (TypeError, ValueError):
        return None


def blocks_per_ref_measured(cap_rows):
    """blocks per reference at each measured precision, from the largest K.

    Taken at the largest K available because the small-K points carry a fixed
    overhead that inflates the per-reference figure -- at K=32 the binary
    design reports 0.906 blocks/ref against 0.566 at K>=256, purely because a
    partial block still costs a whole block. The asymptote is the honest number
    for extrapolating a ceiling.
    """
    best = {}
    for r in cap_rows:
        if r.get("tier") != "onchip":
            continue
        if num(r.get("D"), int) != D_ANCHOR:
            continue
        X, K = num(r.get("X"), int), num(r.get("K"), int)
        blocks = num(r.get("bram18k_required"), int)
        if None in (X, K, blocks):
            continue
        if X not in best or K > best[X][0]:
            best[X] = (K, blocks)
    return {X: blocks / float(K) for X, (K, blocks) in best.items()}


def main():
    cap = read_csv(CAPACITY)
    acc = read_csv(ACCURACY)

    measured = blocks_per_ref_measured(cap)
    if not measured:
        raise SystemExit("no onchip rows at D=%d in capacity_sweep.csv" % D_ANCHOR)

    base = measured.get(1)
    if base is None:
        base = min(measured.values()) / max(measured.keys())

    def blocks_per_ref(bits):
        if bits in measured:
            return measured[bits], "measured"
        return base * bits, "scaled from X=1"

    # accuracy CSV may be the aggregated (auc_mean) or the older single-seed
    # (auc) form -- accept either so the join does not break on a re-run
    def auc_of(r):
        v = num(r.get("auc_mean"))
        return v if v is not None else num(r.get("auc"))

    def sd_of(r):
        return num(r.get("auc_sd")) or 0.0

    rows = []
    for r in acc:
        bits = num(r.get("bits"), int)
        P = num(r.get("P"), int)
        a = auc_of(r)
        if None in (bits, P, a):
            continue
        bpr, prov = blocks_per_ref(bits)
        kb_per_ref = D_ANCHOR * bits / 8.0 / 1024.0
        k_max = int(U280_BRAM18K / bpr) if bpr else None
        rows.append({
            "P": P, "bits": bits, "policy": r.get("policy"),
            "storage": r.get("storage"),
            "auc": round(a, 6), "auc_sd": round(sd_of(r), 6),
            "tpr_mean": num(r.get("tpr_mean")),
            "overflowed": num(r.get("overflowed"), int),
            "KB_per_ref": round(kb_per_ref, 3),
            "blocks_per_ref": round(bpr, 4),
            "blocks_provenance": prov,
            "K_max_on_U280": k_max,
        })

    if not rows:
        raise SystemExit("nothing joined -- check the two CSVs share a bits column")

    # relative to the 32-bit point at the same P and policy
    ref = {(r["P"], r["policy"]): r for r in rows if r["bits"] == 32}
    for r in rows:
        b = ref.get((r["P"], r["policy"]))
        if not b:
            continue
        r["auc_vs_int32"] = round(r["auc"] - b["auc"], 6)
        if r.get("tpr_mean") is not None and b.get("tpr_mean") is not None:
            r["tpr_vs_int32"] = round(r["tpr_mean"] - b["tpr_mean"], 6)
        if b["K_max_on_U280"]:
            r["capacity_gain"] = round(r["K_max_on_U280"] / float(b["K_max_on_U280"]), 2)

    cols = ["P", "bits", "policy", "storage", "auc", "auc_sd", "tpr_mean", "tpr_vs_int32",
            "auc_vs_int32", "KB_per_ref", "blocks_per_ref", "blocks_provenance",
            "K_max_on_U280", "capacity_gain", "overflowed"]
    rows.sort(key=lambda r: (r["P"], r["bits"], r["policy"] or ""))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ------------------------------- report -------------------------------
    print("=" * 96)
    print(" ACCURACY vs CAPACITY on one U280, D = {}".format(D_ANCHOR))
    print("=" * 96)
    print(" blocks/reference: " + ", ".join(
        "X={} -> {:.4f} ({})".format(b, *blocks_per_ref(b)) for b in sorted(
            set([1, 2, 4, 8, 16, 32]))))
    print(" device ceiling: {} BRAM18K".format(U280_BRAM18K))

    # AUC saturates on the easy configurations -- at P=50 every non-wrap row is
    # 1.0000 +/- 0.0000, which cannot distinguish anything. TPR at a low FPR is
    # the operating point a retrieval system is actually judged at, and it keeps
    # resolving differences after AUC has run out of room. Both are shown; the
    # writeup should quote TPR wherever AUC is above ~0.99.
    fmt = "{:>5} {:<9} {:>8} {:>17} {:>17} {:>10} {:>8}  {}"
    for P in sorted({r["P"] for r in rows}):
        print("\n---- P = {} bundled patterns ----".format(P))
        print(fmt.format("bits", "policy", "KB/ref", "AUC",
                         "TPR@FPR<=0.05", "K max", "gain", "verdict"))
        print("-" * 96)
        for r in [x for x in rows if x["P"] == P]:
            if r["auc"] < 0.6:
                verdict = "BROKEN (chance)"
            elif r.get("overflowed"):
                verdict = "overflowed"
            else:
                verdict = "ok"
            tpr = r.get("tpr_mean")
            tpr_s = "-" if tpr is None else "{:.4f}".format(tpr)
            print(fmt.format(
                r["bits"], r["policy"], r["KB_per_ref"],
                "{:.4f}+/-{:.4f}".format(r["auc"], r["auc_sd"]),
                tpr_s, r["K_max_on_U280"],
                "{}x".format(r.get("capacity_gain", "-")), verdict))

    # ---- the headline: cheapest width within 1% of full precision ----
    print("\n" + "=" * 96)
    print(" THE TRADE, STATED AS A CAPABILITY")
    print("=" * 96)
    for P in sorted({r["P"] for r in rows}):
        grp = [r for r in rows if r["P"] == P]

        # Select on TPR, not AUC. AUC saturates -- at P=500 a 1-bit reference is
        # within 0.005 AUC of int32 and looks free, while costing 0.026 of TPR,
        # i.e. 2.6 points of recall at the operating point anyone would deploy.
        # Choosing on AUC would recommend a configuration the stricter metric
        # rejects, which is precisely the failure the TPR column exists to catch.
        have_tpr = all(r.get("tpr_mean") is not None for r in grp)
        key = "tpr_mean" if have_tpr else "auc"
        full = max(r[key] for r in grp)
        ok = [r for r in grp if r[key] >= full - 0.01]
        if not ok:
            continue
        best = min(ok, key=lambda r: (r["bits"], r["policy"] or ""))
        if have_tpr:
            print(" [selected on TPR@FPR<=0.05, within 0.01 of the best]")
        b32 = ref.get((P, best["policy"])) or ref.get((P, "scale"))
        if not b32:
            continue
        gain = best["K_max_on_U280"] / float(b32["K_max_on_U280"])
        print(" P={:<6} {} bits under `{}`: {:>6} references vs int32's {:>4}"
              .format(P, best["bits"], best["policy"], best["K_max_on_U280"],
                      b32["K_max_on_U280"]))
        print("           AUC {:.4f} vs {:.4f}  ({:+.4f})"
              .format(best["auc"], b32["auc"], best["auc"] - b32["auc"]))
        bt, rt = b32.get("tpr_mean"), best.get("tpr_mean")
        if bt is not None and rt is not None:
            print("           TPR@FPR<=0.05 {:.4f} vs {:.4f}  ({:+.4f})"
                  .format(rt, bt, rt - bt))
        print("           -> {:.0f}x the library.".format(gain))
        if b32["auc"] >= 0.999:
            print("           NOTE: AUC is saturated at this load -- both rows sit")
            print("           at the top of the metric, so quote TPR here, not AUC.")

    print("\n" + "=" * 96)
    print(" WHAT IS MEASURED AND WHAT IS MODELLED")
    print("=" * 96)
    print(" blocks/reference at X in {1,8,32}   MEASURED (capacity sweep, csynth)")
    print(" blocks/reference elsewhere          scaled linearly from X=1")
    print(" K_max                               MODELLED; the capacity study")
    print("                                     confirmed this model against")
    print("                                     Vivado at the int32 boundary to")
    print("                                     within 0.28%")
    print(" AUC                                 software model, bit-accurate to")
    print("                                     ap_int wrap semantics; RANDOM")
    print("                                     hypervectors on a synthetic")
    print("                                     membership task, NOT BioHD's")
    print("                                     protein data -- the claim is")
    print("                                     about the capacity property, not")
    print("                                     an end-to-end biology result")
    print("=" * 96)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
