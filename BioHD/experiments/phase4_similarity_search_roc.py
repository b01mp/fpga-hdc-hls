"""Phase 4 validation: similarity search + ROC curve (search.py). THE GO/NO-GO GATE.

Go/no-go condition (CLAUDE.md): the ROC curve qualitatively matches Figure 6d of the paper —
i.e. for a lightly loaded reference hypervector there's a threshold achieving ~100% true
positive rate at low false positive rate, while a heavily loaded reference hypervector (storing
many more patterns than its practical capacity) shows degraded quality: true positive rate
stays below 100% even as the false positive rate is allowed to grow, and the ROC curve as a
whole sits below that of the lightly loaded case.

Implementation note: this experiment bundles P >> 1 patterns directly via
primitives.random_hvs rather than running the full mRNA/amino-acid/protein encoder pipeline.
Phases 1-2 already established that encoded sequences behave statistically identically to
independent random hypervectors (near-orthogonal, same dot-product distribution), so this is a
faithful and much faster way to explore the large-P regime needed to see capacity saturation.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase4_similarity_search_roc.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import primitives as p
import search as s

DIM = 10_000
MODE = "binary"
P_VALUES = (50, 500, 2_000, 8_000)
N_UNRELATED = 1_000
SEED = 0

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def evaluate(n_patterns: int) -> tuple[torch.Tensor, torch.Tensor]:
    g = torch.Generator()
    g.manual_seed(SEED)
    patterns = p.random_hvs(n_patterns, DIM, mode=MODE, generator=g)
    reference = p.bundle(patterns, mode=MODE)

    stored_sims = torch.tensor(
        [p.similarity(reference, patterns[i], mode=MODE).item() for i in range(n_patterns)], dtype=torch.float64
    )

    unrelated = p.random_hvs(N_UNRELATED, DIM, mode=MODE, generator=g)
    unrelated_sims = torch.tensor(
        [p.similarity(reference, unrelated[i], mode=MODE).item() for i in range(N_UNRELATED)], dtype=torch.float64
    )

    return stored_sims, unrelated_sims


def main() -> None:
    print(f"Phase 4: similarity search + ROC curve (D={DIM}, mode={MODE})\n")
    print(f"{'P':>6}  {'signal mean/std':>20}  {'noise mean/std':>20}  {'AUC':>6}  "
          f"{'best Tm':>8}  {'TPR@best':>9}  {'FPR@best':>9}  {'TPR@FPR<=0.05':>14}")

    results = {}
    summary = []
    for n_patterns in P_VALUES:
        stored, unrelated = evaluate(n_patterns)
        thresholds, tprs, fprs = s.roc_curve(stored, unrelated, DIM, n_thresholds=400)
        score = s.auc(fprs, tprs)
        best_t, best_tpr, best_fpr = s.best_threshold(stored, unrelated, DIM, n_thresholds=400)

        low_fpr_mask = fprs <= 0.05
        tpr_at_low_fpr = tprs[low_fpr_mask].max().item() if low_fpr_mask.any() else 0.0

        print(f"{n_patterns:>6}  {stored.mean().item():>9.1f}/{stored.std().item():<9.1f}  "
              f"{unrelated.mean().item():>9.1f}/{unrelated.std().item():<9.1f}  "
              f"{score:>6.3f}  {best_t:>8.3f}  {best_tpr:>9.3f}  {best_fpr:>9.3f}  {tpr_at_low_fpr:>14.3f}")

        results[n_patterns] = (fprs, tprs, score)
        summary.append((n_patterns, score, tpr_at_low_fpr))
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    for n_patterns, (fprs, tprs, score) in results.items():
        ax.plot(fprs.numpy(), tprs.numpy(), label=f"P={n_patterns} (AUC={score:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="chance")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"BioHD ROC curve vs. stored pattern count P (D={DIM})")
    ax.legend()
    fig.tight_layout()
    out_path = OUTPUT_DIR / "phase4_roc_curves.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"ROC curves saved to {out_path}\n")

    smallest_p, smallest_auc, smallest_tpr_low_fpr = summary[0]
    largest_p, largest_auc, largest_tpr_low_fpr = summary[-1]

    lightly_loaded_near_perfect = smallest_tpr_low_fpr >= 0.95
    heavily_loaded_degraded = largest_tpr_low_fpr < 0.95
    auc_degrades_with_load = all(summary[i][1] >= summary[i + 1][1] - 0.02 for i in range(len(summary) - 1))

    print(f"Lightly loaded (P={smallest_p}) achieves TPR>=0.95 at FPR<=0.05: {lightly_loaded_near_perfect}")
    print(f"Heavily loaded (P={largest_p}) quality loss (TPR<0.95 at FPR<=0.05): {heavily_loaded_degraded}")
    print(f"AUC degrades (non-increasing within tolerance) as P grows: {auc_degrades_with_load}")

    passed = lightly_loaded_near_perfect and heavily_loaded_degraded and auc_degrades_with_load
    verdict = "GO" if passed else "NO-GO"
    print(f"\nPhase 4 milestone (GO/NO-GO GATE): {verdict} "
          f"(ROC curve qualitatively matches Figure 6d: near-ideal separability at low load, "
          f"degraded true-positive rate at high load)")


if __name__ == "__main__":
    main()
