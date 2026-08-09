"""Phase 7: task accuracy as a function of stored-element width and overflow policy.

    cd BioHD
    python experiments/phase7_precision_accuracy.py

WHAT THIS MEASURES, AND HOW IT PAIRS WITH THE HARDWARE DATA
    The capacity-crossover study already measured what element width COSTS: at
    D=10240, on-chip footprint scales exactly with bits per element, and the
    device ceiling moves 32x between binary and int32 (DSE/synth_results/
    capacity_sweep.csv). What it did not measure is what element width BUYS.

    This does that half. Same quantity -- bits per stored element -- against
    retrieval accuracy instead of block RAM. The two join into an
    accuracy-versus-area Pareto without needing a single extra synthesis run.

THE TASK
    Phase 4's membership problem, unchanged: bundle P patterns into one
    reference hypervector, then ask whether a query was one of them. Stored
    patterns are the positive class, fresh random hypervectors the negative
    class, and the separation between the two similarity distributions is the
    accuracy. This is the BioHD reference-library operation, so the precision
    conclusion applies to the design the paper is about.

WHY BIPOLAR AND NOT BINARY
    In binary mode `bundle` re-binarises via majority vote, so the reference is
    1 bit per element by construction and there is no width to sweep. Bipolar
    mode keeps the accumulated counts, which is exactly the "wide accumulate,
    narrow store" case: counts range over -P..P and something has to happen when
    they are stored in W bits. That something is the variable under test.

    W = 1 IS a special case, and getting it wrong was instructive. A binary
    element is the two-valued alphabet {-1,+1} carried in one bit; ap_int<1>
    spans -1..0, because one signed bit has a sign and no magnitude. Truncating
    counts into ap_int<1> keeps the LOW BIT -- parity, not sign -- and with an
    even number of bundled patterns every count is even, so the reference
    collapses to zero and AUC lands on exactly 0.5. That is a property of the
    wrong model, not of binary HDC.

    So at W=1 the sweep stores sign(counts) in {-1,+1}, which is what
    primitives.bundle(mode="binary") computes and what the library's binary_tag
    path builds. All three policies coincide there -- there is only one sensible
    way to keep one bit of a signed quantity -- and the storage column says so.

THREE OVERFLOW POLICIES, BECAUSE THE WIDTH ALONE DOES NOT DETERMINE THE ANSWER
    wrap      what ap_int<W> does by default
    saturate  clamp, costing a comparator per store
    scale     rescale once, then store at reduced resolution

    Reporting only one of these would be choosing the number that suits the
    argument. The gap between them is itself the finding: "int8 library" is not
    a specification until the policy is stated.

WHY AUC IS COMPUTED HERE RATHER THAN VIA search.roc_curve
    search.roc_curve sweeps an ABSOLUTE threshold expressed as a fraction of D,
    which assumes the similarity scale is ~D. Rescaling the reference changes
    that scale, so the shared threshold grid would penalise `scale` for a units
    change rather than for lost information. The Mann-Whitney form used below is
    rank-based and therefore scale-invariant, and it equals the ROC AUC exactly.
    search.roc_curve is still used for the threshold-level reporting, where the
    absolute scale is the point.

OUTPUT
    DSE/synth_results/precision_accuracy.csv   one row per (P, bits, policy)
    BioHD/experiments/output/phase7_precision_accuracy.png
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import primitives as p          # noqa: E402
import quantize as q            # noqa: E402

DIM = 10_000
P_VALUES = (50, 500, 2_000)
BIT_WIDTHS = (1, 2, 4, 8, 16, 32)
POLICIES = ("wrap", "saturate", "scale")
N_UNRELATED = 1_000
SEED = 0

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"
REPO = HERE.parent.parent
RESULTS = REPO / "DSE" / "synth_results"


def auc_rank(pos: torch.Tensor, neg: torch.Tensor) -> float:
    """ROC AUC via the Mann-Whitney U statistic: P(pos > neg), ties at 0.5.

    Rank-based, so it is invariant to any monotone rescaling of the similarity
    values. That matters here because the `scale` policy deliberately changes
    the units of the score.
    """
    both = torch.cat([pos, neg]).to(torch.float64)
    ranks = torch.empty_like(both)
    order = torch.argsort(both)
    sorted_vals = both[order]

    # average ranks within tied groups, so ties contribute 0.5 rather than 1
    i = 0
    n = both.numel()
    r = torch.empty(n, dtype=torch.float64)
    while i < n:
        j = i
        while j + 1 < n and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        r[i:j + 1] = 0.5 * (i + j) + 1.0
        i = j + 1
    ranks[order] = r

    n_pos = pos.numel()
    n_neg = neg.numel()
    rank_sum_pos = ranks[:n_pos].sum().item()
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / float(n_pos * n_neg)


def evaluate(n_patterns: int, bits: int, policy: str) -> dict:
    """Bundle n_patterns, store the reference at `bits` bits under `policy`,
    and measure how well stored patterns separate from unrelated ones."""
    g = torch.Generator()
    g.manual_seed(SEED)

    patterns = p.random_hvs(n_patterns, DIM, mode="bipolar", generator=g)
    unrelated = p.random_hvs(N_UNRELATED, DIM, mode="bipolar", generator=g)

    # Full-precision bundled reference: per-dimension counts in -P..P.
    counts = patterns.to(torch.int64).sum(dim=0)

    needed = int(counts.abs().max().item())
    mode = q.storage_mode(bits, signed=True)
    # At 1 bit the value is RE-REPRESENTED, not overflowed. Flagging it as an
    # overflow would imply a defect where there is a deliberate encoding choice.
    overflowed = (bits > 1) and (not q.fits(counts, bits, signed=True))

    ref = q.apply_policy(counts, bits, policy, signed=True).to(torch.int64)

    # Similarity is a dot product against the stored reference. Vectorised --
    # phase4 loops one pattern at a time, which is far too slow at P=2000.
    sims_pos = (patterns.to(torch.int64) * ref).sum(dim=1).to(torch.float64)
    sims_neg = (unrelated.to(torch.int64) * ref).sum(dim=1).to(torch.float64)

    return {
        "P": n_patterns,
        "bits": bits,
        "policy": policy,
        "auc": round(auc_rank(sims_pos, sims_neg), 6),
        "signal_mean": round(sims_pos.mean().item(), 3),
        "signal_std": round(sims_pos.std().item(), 3),
        "noise_mean": round(sims_neg.mean().item(), 3),
        "noise_std": round(sims_neg.std().item(), 3),
        "peak_count": needed,
        "storage": mode,
        "bits_needed": int(needed).bit_length() + 1,   # signed: magnitude + sign
        "overflowed": int(overflowed),
    }


def main() -> int:
    print("Phase 7: accuracy vs stored-element width  (D=%d, bipolar)\n" % DIM)

    if q.self_test() != 0:
        print("quantize self_test FAILED -- refusing to produce accuracy numbers "
              "from an unverified precision model.")
        return 1
    print()

    rows = []
    for P in P_VALUES:
        print("---- P = %d bundled patterns ----" % P)
        print("%6s %10s %14s %8s %10s %12s" %
              ("bits", "policy", "storage", "AUC", "overflow", "signal mean"))
        for bits in BIT_WIDTHS:
            for policy in POLICIES:
                r = evaluate(P, bits, policy)
                rows.append(r)
                print("%6d %10s %14s %8.4f %10s %12.1f" %
                      (r["bits"], r["policy"], r["storage"], r["auc"],
                       "YES" if r["overflowed"] else "-", r["signal_mean"]))
        print()

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_csv = RESULTS / "precision_accuracy.csv"
    cols = ["P", "bits", "policy", "storage", "auc", "signal_mean", "signal_std",
            "noise_mean", "noise_std", "peak_count", "bits_needed", "overflowed"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", out_csv)

    # ---------------- what the numbers say ----------------
    print("\n" + "=" * 72)
    print(" READING IT")
    print("=" * 72)
    for P in P_VALUES:
        grp = [r for r in rows if r["P"] == P]
        full = max(r["auc"] for r in grp)
        # narrowest width whose best policy stays within 1% of full precision
        keep = [r for r in grp if r["auc"] >= full - 0.01]
        if keep:
            best = min(keep, key=lambda r: (r["bits"], r["policy"]))
            print(" P=%-5d full-precision AUC %.4f ; %d bits under `%s` still within 1%%"
                  % (P, full, best["bits"], best["policy"]))
        wrapped = [r for r in grp if r["overflowed"] and r["policy"] == "wrap"]
        if wrapped:
            worst = min(wrapped, key=lambda r: r["auc"])
            print("        wrap at %d bits (counts peak at %d) collapses AUC to %.4f"
                  % (worst["bits"], worst["peak_count"], worst["auc"]))
    print("\n Pair these with DSE/synth_results/capacity_sweep.csv, which gives")
    print(" the on-chip cost of the SAME bits-per-element axis, to get the")
    print(" accuracy-vs-area Pareto without any further synthesis.")

    # ---------------- plot ----------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(1, len(P_VALUES), figsize=(5 * len(P_VALUES), 4),
                                 sharey=True)
        if len(P_VALUES) == 1:
            axes = [axes]
        for ax, P in zip(axes, P_VALUES):
            for policy in POLICIES:
                pts = sorted([r for r in rows if r["P"] == P and r["policy"] == policy],
                             key=lambda r: r["bits"])
                ax.plot([r["bits"] for r in pts], [r["auc"] for r in pts],
                        marker="o", label=policy)
            ax.set_xscale("log", base=2)
            ax.set_xlabel("bits per stored element")
            ax.set_title("P = %d" % P)
            ax.grid(alpha=0.3)
        axes[0].set_ylabel("AUC")
        axes[0].legend()
        fig.suptitle("Retrieval accuracy vs stored-element width and overflow policy "
                     "(D=%d)" % DIM)
        fig.tight_layout()
        path = OUTPUT_DIR / "phase7_precision_accuracy.png"
        fig.savefig(path, dpi=150)
        print("\nwrote", path)
    except ImportError:
        print("\n(matplotlib not available -- CSV written, plot skipped)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
