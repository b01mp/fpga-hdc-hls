"""Phase 3 validation: reference library (library.py).

Go/no-go condition (CLAUDE.md): library correctly memorizes 10^3 sequences at D=10k.

We build a synthetic "reference protein" long enough to produce exactly 1000 overlapping
windows, memorize all of them via sliding-window scanning (Section 3.2), and check how many
can be correctly recalled (best-matching reference == the one they were stored in) before and
after adaptive library refinement (Section 3.3). Patterns are split across multiple reference
hypervectors (capacity per reference < total patterns) specifically so refinement has
cross-reference mistakes to correct, mirroring the paper's "look at the same object multiple
times" memorization narrative.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase3_reference_library.py
"""

import random
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from encoder import AMINO_ACIDS, HDCAlphabet
from library import HDCLibrary

DIM = 10_000
WINDOW = 10
N_PATTERNS = 1_000
CAPACITY = 100  # -> 10 reference hypervectors
SEED = 0
RECALL_TARGET = 0.95
REFINE_EPOCHS = 30


def build_library(mode: str) -> tuple[HDCAlphabet, HDCLibrary]:
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)
    long_protein = rng.choices(acids_no_stop, k=N_PATTERNS + WINDOW - 1)

    lib = HDCLibrary(DIM, capacity=CAPACITY)
    n_added = lib.add_sequence_windows(alphabet, long_protein, window=WINDOW, stride=1)
    assert n_added == N_PATTERNS, f"expected {N_PATTERNS} windows, got {n_added}"
    return alphabet, lib


def signal_noise_report(lib: HDCLibrary, label: str) -> None:
    """For each stored pattern, similarity to its assigned reference (signal) vs. the mean
    similarity to all other references (noise)."""
    signal, noise = [], []
    for i, hv in enumerate(lib.pattern_hvs):
        sims = lib.similarities(hv)
        correct_idx = lib.pattern_ref_idx[i]
        signal.append(sims[correct_idx].item())
        other = torch.cat([sims[:correct_idx], sims[correct_idx + 1:]])
        if len(other) > 0:
            noise.append(other.mean().item())
    signal_t = torch.tensor(signal)
    noise_t = torch.tensor(noise) if noise else torch.tensor([0.0])
    print(f"  [{label}] signal (similarity to assigned ref): mean={signal_t.mean():9.1f} std={signal_t.std():8.1f}")
    print(f"  [{label}] noise  (mean similarity to others):   mean={noise_t.mean():9.1f} std={noise_t.std():8.1f}")


def run(mode: str) -> float:
    print(f"=== mode={mode} ===")
    alphabet, lib = build_library(mode)
    print(f"Built library: {len(lib.pattern_hvs)} patterns across {len(lib.references)} reference hypervectors "
          f"(capacity={CAPACITY} each)")

    accuracy_before = lib.recall_accuracy()
    print(f"Recall accuracy before refinement: {accuracy_before:.3f}")
    signal_noise_report(lib, "before refinement")

    mistakes = lib.refine(epochs=REFINE_EPOCHS)
    print(f"Refinement mistake counts per epoch: {mistakes}")

    accuracy_after = lib.recall_accuracy()
    print(f"Recall accuracy after refinement:  {accuracy_after:.3f}")
    signal_noise_report(lib, "after refinement")
    print()
    return accuracy_after


def main() -> None:
    print(f"Phase 3: reference library — memorizing {N_PATTERNS} sequences at D={DIM}\n")

    accuracy = run("binary")
    mode_used = "binary"
    if accuracy < RECALL_TARGET:
        print(f"binary mode recall {accuracy:.3f} < target {RECALL_TARGET}; "
              f"retrying with full-precision (bipolar) mode for higher capacity.\n")
        accuracy = run("bipolar")
        mode_used = "bipolar"

    verdict = "GO" if accuracy >= RECALL_TARGET else "NO-GO"
    print(f"Phase 3 milestone: {verdict} "
          f"(library [{mode_used} mode] recalls {accuracy * 100:.1f}% of {N_PATTERNS} memorized "
          f"sequences at D={DIM}, target >= {RECALL_TARGET * 100:.0f}%)")


if __name__ == "__main__":
    main()
