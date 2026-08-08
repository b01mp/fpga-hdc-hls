"""Phase 2 validation: encoding pipeline (encoder.py), built bottom-up.

Go/no-go condition (CLAUDE.md): can encode a 10-amino-acid protein, and its hypervector
is near-orthogonal to unrelated sequences.

Run from the project root:
    .venv\\Scripts\\python.exe experiments\\phase2_encoding_pipeline.py
"""

import math
import random
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import primitives as p
from encoder import AMINO_ACIDS, HDCAlphabet

DIM = 10_000
MODE = "binary"
SEED = 0
PROTEIN_LEN = 10
N_PAIRS = 1000

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def level_1_mrna(alphabet: HDCAlphabet) -> None:
    print("--- Level 1: mRNA encoding ---")
    h_acgu = alphabet.encode_mrna("ACGU")
    print(f"H('ACGU') first 8 dims: {h_acgu[:8].tolist()}")

    rng = random.Random(SEED)
    bases = "ACGU"
    sims = []
    for _ in range(N_PAIRS):
        seq1 = "".join(rng.choice(bases) for _ in range(12))
        seq2 = "".join(rng.choice(bases) for _ in range(12))
        h1, h2 = alphabet.encode_mrna(seq1), alphabet.encode_mrna(seq2)
        sims.append(p.similarity(h1, h2, mode=MODE).item())
    sims = torch.tensor(sims, dtype=torch.float64)
    print(f"{N_PAIRS} random length-12 mRNA pairs: mean={sims.mean():+8.2f} std={sims.std():8.2f} "
          f"(expected mean~0, std~{math.sqrt(DIM):.2f})\n")


def level_2_amino_acid(alphabet: HDCAlphabet) -> None:
    print("--- Level 2: amino acid encoding ---")
    phe = alphabet.amino_acid_hvs["Phe"]
    uuu = alphabet.encode_mrna("UUU")
    uuc = alphabet.encode_mrna("UUC")
    print(f"Phe (merged from UUU/UUC) cosine similarity to UUU: {p.cosine_similarity(phe, uuu):.3f}")
    print(f"Phe (merged from UUU/UUC) cosine similarity to UUC: {p.cosine_similarity(phe, uuc):.3f}")

    rng = random.Random(SEED)
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    sims = []
    for _ in range(N_PAIRS):
        a1, a2 = rng.sample(acids_no_stop, 2)
        sims.append(p.similarity(alphabet.amino_acid_hvs[a1], alphabet.amino_acid_hvs[a2], mode=MODE).item())
    sims = torch.tensor(sims, dtype=torch.float64)
    print(f"{N_PAIRS} random unrelated amino-acid pairs: mean={sims.mean():+8.2f} std={sims.std():8.2f}\n")


def level_3_protein(alphabet: HDCAlphabet) -> tuple[torch.Tensor, bool]:
    print(f"--- Level 3: protein encoding ({PROTEIN_LEN}-amino-acid sequences) ---")
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)

    example_seq = rng.choices(acids_no_stop, k=PROTEIN_LEN)
    example_hv = alphabet.encode_protein(example_seq)
    print(f"Example sequence: {example_seq}")
    print(f"Encoded HV shape: {tuple(example_hv.shape)}, dtype: {example_hv.dtype}")

    sims = []
    for _ in range(N_PAIRS):
        seq1 = rng.choices(acids_no_stop, k=PROTEIN_LEN)
        seq2 = rng.choices(acids_no_stop, k=PROTEIN_LEN)
        h1, h2 = alphabet.encode_protein(seq1), alphabet.encode_protein(seq2)
        sims.append(p.similarity(h1, h2, mode=MODE).item())
    sims = torch.tensor(sims, dtype=torch.float64)

    expected_std = math.sqrt(DIM)
    standard_error_of_mean = expected_std / math.sqrt(N_PAIRS)
    passed = abs(sims.mean().item()) < 4 * standard_error_of_mean
    print(f"{N_PAIRS} random {PROTEIN_LEN}-acid protein pairs: "
          f"mean={sims.mean():+8.2f} std={sims.std():8.2f} (expected mean~0, std~{expected_std:.2f})")

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(sims.numpy(), bins=40)
    ax.set_title(f"Similarity of {N_PAIRS} unrelated {PROTEIN_LEN}-acid protein pairs (D={DIM})")
    ax.set_xlabel("similarity (dot product)")
    ax.set_ylabel("count")
    fig.tight_layout()
    out_path = OUTPUT_DIR / "phase2_protein_similarity_distribution.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  -> histogram saved to {out_path}\n")
    return example_hv, passed


def level_4_indel_tolerant(alphabet: HDCAlphabet) -> None:
    print("--- Level 4: indel-tolerant encoding ---")
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)
    base_seq = rng.choices(acids_no_stop, k=24)
    inserted_seq = base_seq[:15] + [rng.choice(acids_no_stop)] + base_seq[15:]

    gen = torch.Generator()
    gen.manual_seed(SEED)
    indel_base = alphabet.encode_indel_tolerant(base_seq, chunk_size=4, generator=gen)
    gen.manual_seed(SEED)
    indel_inserted = alphabet.encode_indel_tolerant(inserted_seq, chunk_size=4, generator=gen)
    indel_sim = p.cosine_similarity(indel_base, indel_inserted).item()

    exact_base = alphabet.encode_protein(base_seq)
    exact_inserted = alphabet.encode_protein(inserted_seq)
    exact_sim = p.cosine_similarity(exact_base, exact_inserted).item()

    print(f"Single mid-sequence insertion into a 24-acid protein:")
    print(f"  exact (full-chain) encoding similarity:   {exact_sim:.3f}")
    print(f"  indel-tolerant (chunked) encoding similarity: {indel_sim:.3f}")
    print(f"  indel-tolerant more robust: {indel_sim > exact_sim}\n")


def main() -> None:
    print(f"Phase 2: encoding pipeline (D={DIM}, mode={MODE})\n")
    alphabet = HDCAlphabet(DIM, mode=MODE, seed=SEED)

    level_1_mrna(alphabet)
    level_2_amino_acid(alphabet)
    _, passed = level_3_protein(alphabet)
    level_4_indel_tolerant(alphabet)

    verdict = "GO" if passed else "NO-GO"
    print(f"Phase 2 milestone: {verdict} "
          f"({PROTEIN_LEN}-amino-acid protein hypervectors are near-orthogonal for unrelated sequences)")


if __name__ == "__main__":
    main()
