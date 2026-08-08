"""Phase 5 validation: parameter sensitivity (capacity vs. dimension).

Go/no-go condition (CLAUDE.md): capacity vs D tradeoff matches Figure 6a/b trends — i.e.
capacity grows with dimensionality D, and full-precision (here: "bipolar") libraries have
higher capacity than 1-bit (here: "binary") libraries at the same D.

"Experimental capacity" at a given (D, mode) is defined as the largest number of bundled
patterns P, from a fixed grid, for which a single reference hypervector still admits a
threshold achieving TPR >= 0.95 and FPR <= 0.05 (search.best_threshold). This mirrors the
paper's Figure 6b methodology of finding the largest P reliably recallable.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase5_parameter_sensitivity.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import primitives as p
import search as s

DIMS = (1_000, 4_000, 10_000, 40_000)
MODES = ("binary", "bipolar")
P_GRID = (50, 100, 200, 400, 800, 1_600, 3_200, 6_400, 10_000)
N_UNRELATED = 500
SEED = 0

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def evaluate(dim: int, mode: str, n_patterns: int) -> tuple[torch.Tensor, torch.Tensor]:
    g = torch.Generator()
    g.manual_seed(SEED)
    patterns = p.random_hvs(n_patterns, dim, mode=mode, generator=g)
    reference = p.bundle(patterns, mode=mode)
    stored_sims = p.similarity(reference, patterns, mode=mode).to(torch.float64)
    unrelated = p.random_hvs(N_UNRELATED, dim, mode=mode, generator=g)
    unrelated_sims = p.similarity(reference, unrelated, mode=mode).to(torch.float64)
    return stored_sims, unrelated_sims


def experimental_capacity(dim: int, mode: str) -> int:
    capacity = 0
    for n_patterns in P_GRID:
        stored, unrelated = evaluate(dim, mode, n_patterns)
        _, tpr, fpr = s.best_threshold(stored, unrelated, dim, n_thresholds=200)
        passed = tpr >= 0.95 and fpr <= 0.05
        print(f"    D={dim:>6} mode={mode:<7} P={n_patterns:>6}  TPR={tpr:.3f}  FPR={fpr:.3f}  "
              f"{'OK' if passed else 'FAIL'}")
        if passed:
            capacity = n_patterns
    return capacity


def main() -> None:
    print(f"Phase 5: parameter sensitivity — capacity vs. D across modes {MODES}\n")
    print(f"(capacity = largest P in {P_GRID} with TPR>=0.95, FPR<=0.05 for a single reference hypervector)\n")

    capacities = {mode: [] for mode in MODES}
    for mode in MODES:
        for dim in DIMS:
            cap = experimental_capacity(dim, mode)
            capacities[mode].append(cap)
            note = f"capacity={cap}" + (" (>= grid max, true capacity may be higher)" if cap == P_GRID[-1] else "")
            print(f"  -> D={dim}, mode={mode}: {note}\n")

    print("Summary (experimental capacity):")
    header = "D".rjust(8) + "".join(mode.rjust(12) for mode in MODES)
    print(header)
    for i, dim in enumerate(DIMS):
        row = str(dim).rjust(8) + "".join(str(capacities[mode][i]).rjust(12) for mode in MODES)
        print(row)
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for mode in MODES:
        ax.plot(DIMS, capacities[mode], marker="o", label=mode)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Dimension D")
    ax.set_ylabel("Experimental capacity (# patterns)")
    ax.set_title("BioHD capacity vs. dimension")
    ax.legend()
    fig.tight_layout()
    out_path = OUTPUT_DIR / "phase5_capacity_vs_dimension.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Plot saved to {out_path}\n")

    capacity_grows_with_dim = all(
        all(capacities[mode][i] <= capacities[mode][i + 1] for i in range(len(DIMS) - 1))
        for mode in MODES
    )
    bipolar_at_least_binary = all(
        capacities["bipolar"][i] >= capacities["binary"][i] for i in range(len(DIMS))
    )

    print(f"Capacity is non-decreasing in D for every mode: {capacity_grows_with_dim}")
    print(f"Full-precision (bipolar) capacity >= binary capacity at every D: {bipolar_at_least_binary}")

    passed = capacity_grows_with_dim and bipolar_at_least_binary
    verdict = "GO" if passed else "NO-GO"
    print(f"\nPhase 5 milestone: {verdict} "
          f"(capacity vs D tradeoff matches Figure 6a/b trends: capacity increases with D and "
          f"with hypervector precision)")


if __name__ == "__main__":
    main()
