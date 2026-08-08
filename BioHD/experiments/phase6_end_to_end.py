"""Phase 6 validation: end-to-end DNA search at query length 200.

Go/no-go condition (CLAUDE.md): >95% true positive rate on the E. coli dataset.

DATA CAVEAT: this environment has no real E. coli FASTA file available locally, and per
project policy this assistant does not guess/fabricate download URLs for external genomic
databases without the user supplying one. So this script builds a SYNTHETIC stand-in
"genome": a random DNA string with ~50% GC content, at a size scaled down for compute
feasibility (real E. coli K-12 MG1655 is ~4.6 Mbp; we use a much shorter sequence here).
Everything downstream — DNA-level HDC encoding, sliding-window library construction, and
threshold search — is the same code that would run against a real FASTA file. To validate
against the real genome, replace `synthetic_genome()`'s output with a real sequence string
(e.g. loaded from a FASTA file) and re-run.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase6_end_to_end.py
"""

import random
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from encoder import HDCAlphabet
from library import HDCLibrary, sliding_windows
import search as s

DIM = 10_000
MODE = "bipolar"
QUERY_LENGTH = 200
GENOME_LENGTH = 20_000  # scaled down from real E. coli's ~4.6 Mbp; see module docstring
STRIDE = 100
N_QUERIES = 200
SEED = 0


def synthetic_genome(length: int, seed: int) -> str:
    """Random DNA string with ~50% GC content, standing in for a real E. coli genome."""
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def main() -> None:
    print(f"Phase 6: end-to-end DNA search (D={DIM}, mode={MODE}, query length={QUERY_LENGTH})")
    print("NOTE: using a synthetic stand-in genome, not a real E. coli FASTA file (see module docstring).\n")

    alphabet = HDCAlphabet(DIM, mode=MODE, seed=SEED)
    genome = synthetic_genome(GENOME_LENGTH, seed=SEED)
    windows = sliding_windows(genome, QUERY_LENGTH, STRIDE)
    print(f"Synthetic genome length: {len(genome)} bp, stride={STRIDE} -> {len(windows)} windows")

    lib = HDCLibrary(DIM, capacity=10 ** 9)  # single reference hypervector
    for win in windows:
        hv = alphabet.encode_mrna("".join(win))
        lib.add_pattern(hv)
    print(f"Memorized {len(lib.pattern_hvs)} windows into {len(lib.references)} reference hypervector(s)\n")

    # True positives: re-query a random sample of windows actually present in the genome.
    rng = random.Random(SEED)
    n_pos = min(N_QUERIES, len(windows))
    positive_idxs = rng.sample(range(len(windows)), n_pos)
    positive_sims = torch.tensor(
        [lib.similarities(lib.pattern_hvs[i])[0].item() for i in positive_idxs], dtype=torch.float64
    )

    # False positives: fresh random 200bp DNA strings, vanishingly unlikely to collide with a
    # stored window (D=10000 makes accidental matches astronomically improbable).
    negative_queries = [synthetic_genome(QUERY_LENGTH, seed=10_000 + i) for i in range(N_QUERIES)]
    negative_sims = torch.tensor(
        [lib.similarities(alphabet.encode_mrna(q))[0].item() for q in negative_queries], dtype=torch.float64
    )

    print(f"Stored-window similarity:   mean={positive_sims.mean():9.1f} std={positive_sims.std():8.1f}")
    print(f"Unrelated-query similarity: mean={negative_sims.mean():9.1f} std={negative_sims.std():8.1f}\n")

    threshold, tpr, fpr = s.best_threshold(positive_sims, negative_sims, DIM, n_thresholds=400)
    print(f"Best threshold T_m={threshold:.3f}: TPR={tpr:.3f}, FPR={fpr:.3f}\n")

    verdict = "GO" if tpr > 0.95 else "NO-GO"
    print(f"Phase 6 milestone: {verdict} (TPR={tpr * 100:.1f}% on {n_pos} positive / "
          f"{N_QUERIES} negative length-{QUERY_LENGTH} DNA queries against a synthetic "
          f"E. coli-like genome; target >95%)")
    print("\nCaveat: this used a synthetic stand-in genome, not real E. coli sequence data — "
          "see the module docstring for why, and how to re-run against a real FASTA file.")


if __name__ == "__main__":
    main()
