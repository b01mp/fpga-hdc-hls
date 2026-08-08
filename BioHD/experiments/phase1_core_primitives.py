"""Phase 1 validation: core HDC primitives (primitives.py).

Go/no-go condition (CLAUDE.md): unit tests pass, and 1000 random hypervector pairs
show dot products (similarity scores) clustered near 0.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase1_core_primitives.py
"""

import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import primitives as p

N_PAIRS = 1000
DIMS = (1_000, 4_000, 10_000, 40_000)
MODES = ("binary", "bipolar")
SEED = 0

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def evaluate(dim: int, mode: str) -> torch.Tensor:
    g = torch.Generator()
    g.manual_seed(SEED)
    a = p.random_hvs(N_PAIRS, dim, mode=mode, generator=g)
    b = p.random_hvs(N_PAIRS, dim, mode=mode, generator=g)
    return p.similarity(a, b, mode=mode).to(torch.float64)


def report(dim: int, mode: str, sims: torch.Tensor) -> None:
    expected_std = math.sqrt(dim)
    mean = sims.mean().item()
    std = sims.std().item()
    print(
        f"D={dim:>6}  mode={mode:<7}  "
        f"mean={mean:+9.2f} (expected ~0)  "
        f"std={std:9.2f} (expected ~{expected_std:.2f})  "
        f"min={sims.min().item():+9.2f}  max={sims.max().item():+9.2f}"
    )


def plot(dim: int, results: dict) -> Path:
    fig, ax = plt.subplots(figsize=(6, 4))
    for mode, sims in results.items():
        ax.hist(sims.numpy(), bins=40, alpha=0.6, label=mode)
    ax.set_title(f"Similarity of {N_PAIRS} random HV pairs (D={dim})")
    ax.set_xlabel("similarity (dot product)")
    ax.set_ylabel("count")
    ax.legend()
    fig.tight_layout()

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"dot_product_distribution_D{dim}.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def main() -> None:
    print(f"Phase 1: core primitives — {N_PAIRS} random HV pairs across D in {DIMS}\n")

    all_passed = True
    for dim in DIMS:
        results = {}
        for mode in MODES:
            sims = evaluate(dim, mode)
            report(dim, mode, sims)
            results[mode] = sims

            expected_std = math.sqrt(dim)
            standard_error_of_mean = expected_std / math.sqrt(N_PAIRS)
            if abs(sims.mean().item()) > 4 * standard_error_of_mean:
                all_passed = False

        out_path = plot(dim, results)
        print(f"  -> histogram saved to {out_path}\n")

    verdict = "GO" if all_passed else "NO-GO"
    print(f"Phase 1 milestone: {verdict} "
          f"(dot products of random HV pairs clustered near 0 across all tested D)")


if __name__ == "__main__":
    main()
