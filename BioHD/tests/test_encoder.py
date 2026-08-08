"""Unit tests for encoder.py: mRNA, amino acid, protein, and indel-tolerant encoding.

Verifies the distributional properties demanded by Phase 2 of CLAUDE.md: a 10-amino-acid
protein can be encoded and its hypervector is near-orthogonal to unrelated sequences.
"""

import math
import random

import pytest
import torch

import primitives as p
from encoder import (
    AMINO_ACIDS,
    CODON_TABLE,
    HDCAlphabet,
    codons_for,
    correlated_position_hvs,
    probabilistic_merge,
)

MODES = ("binary", "bipolar")
DIM = 10_000
SEED = 0


# ---------------------------------------------------------------------------
# Codon table
# ---------------------------------------------------------------------------

def test_codon_table_has_64_codons():
    assert len(CODON_TABLE) == 64


def test_codon_table_known_mappings():
    assert CODON_TABLE["AUG"] == "Met"
    assert CODON_TABLE["UGG"] == "Trp"
    assert CODON_TABLE["UUU"] == "Phe"
    assert CODON_TABLE["UUC"] == "Phe"
    stop_codons = [c for c, a in CODON_TABLE.items() if a == "Stop"]
    assert sorted(stop_codons) == ["UAA", "UAG", "UGA"]


def test_codons_for_phe_matches_paper_example():
    assert sorted(codons_for("Phe")) == ["UUC", "UUU"]


def test_amino_acids_cover_20_acids_plus_stop():
    assert len(AMINO_ACIDS) == 21  # 20 standard amino acids + Stop


# ---------------------------------------------------------------------------
# probabilistic_merge
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_probabilistic_merge_each_dim_comes_from_an_input(mode):
    g = torch.Generator()
    g.manual_seed(SEED)
    a = p.random_hv(DIM, mode=mode, generator=g)
    b = p.random_hv(DIM, mode=mode, generator=g)
    merged = probabilistic_merge(torch.stack([a, b]), generator=g)
    matches_a = merged == a
    matches_b = merged == b
    assert torch.all(matches_a | matches_b)


def test_probabilistic_merge_splits_roughly_in_half():
    # Use disjoint values (all-0 vs all-1) so dimension-wise equality unambiguously
    # reveals which source each dimension was sampled from (random a/b could coincide).
    g = torch.Generator()
    g.manual_seed(SEED)
    a = torch.zeros(DIM, dtype=torch.int8)
    b = torch.ones(DIM, dtype=torch.int8)
    merged = probabilistic_merge(torch.stack([a, b]), generator=g)
    frac_from_b = (merged == b).float().mean().item()
    assert abs(frac_from_b - 0.5) < 0.05


def test_probabilistic_merge_requires_at_least_two_vectors():
    a = p.random_hv(DIM)
    with pytest.raises(ValueError):
        probabilistic_merge(a.unsqueeze(0))


# ---------------------------------------------------------------------------
# correlated_position_hvs
# ---------------------------------------------------------------------------

def test_correlated_position_hvs_adjacent_are_similar_far_are_orthogonal():
    # Note: raw cosine_similarity on {0,1}-valued vectors isn't zero-centered (two
    # independent random binary vectors score ~0.5, not ~0), so use the zero-centered
    # p.similarity (normalized by D) to judge (near-)orthogonality here.
    g = torch.Generator()
    g.manual_seed(SEED)
    n_positions = 40
    positions = correlated_position_hvs(n_positions, DIM, mode="binary", generator=g)
    adjacent_sim = p.similarity(positions[0], positions[1], mode="binary").item() / DIM
    far_sim = p.similarity(positions[0], positions[-1], mode="binary").item() / DIM
    assert adjacent_sim > 0.8
    assert abs(far_sim) < 0.15


def test_correlated_position_hvs_single_position():
    positions = correlated_position_hvs(1, DIM)
    assert positions.shape == (1, DIM)


# ---------------------------------------------------------------------------
# HDCAlphabet: mRNA encoding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_mrna_encoding_matches_paper_formula(mode):
    """H = A * rho^1(C) * rho^2(G) * rho^3(U) for the example sequence 'ACGU'."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    a, c, g, u = (alphabet.base_hvs[base] for base in "ACGU")
    expected = p.bind(
        p.bind(p.bind(a, p.permute(c, 1), mode=mode), p.permute(g, 2), mode=mode),
        p.permute(u, 3),
        mode=mode,
    )
    actual = alphabet.encode_mrna("ACGU")
    assert torch.equal(actual, expected)


@pytest.mark.parametrize("mode", MODES)
def test_mrna_encoding_is_deterministic(mode):
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    assert torch.equal(alphabet.encode_mrna("ACGUACGU"), alphabet.encode_mrna("ACGUACGU"))


@pytest.mark.parametrize("mode", MODES)
def test_mrna_encoding_near_orthogonal_for_different_sequences(mode):
    """H1, H2 from different random sequences: H1 . H2 ~ 2*Bin(D,0.5) - D (near 0)."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    rng = random.Random(SEED)
    seq_len = 12
    n_pairs = 200
    rna_bases = "ACGU"
    sims = []
    for _ in range(n_pairs):
        seq1 = "".join(rng.choice(rna_bases) for _ in range(seq_len))
        seq2 = "".join(rng.choice(rna_bases) for _ in range(seq_len))
        h1 = alphabet.encode_mrna(seq1)
        h2 = alphabet.encode_mrna(seq2)
        sims.append(p.similarity(h1, h2, mode=mode).item())
    sims = torch.tensor(sims, dtype=torch.float64)
    expected_std = math.sqrt(DIM)
    standard_error_of_mean = expected_std / math.sqrt(n_pairs)
    assert abs(sims.mean().item()) < 5 * standard_error_of_mean


# ---------------------------------------------------------------------------
# HDCAlphabet: amino acid encoding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_single_codon_amino_acid_equals_its_codon_encoding(mode):
    """Met (AUG) and Trp (UGG) each have exactly one codon, so no merge is needed."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    assert torch.equal(alphabet.amino_acid_hvs["Met"], alphabet.encode_mrna("AUG"))
    assert torch.equal(alphabet.amino_acid_hvs["Trp"], alphabet.encode_mrna("UGG"))


@pytest.mark.parametrize("mode", MODES)
def test_multi_codon_amino_acid_correlates_with_each_codon(mode):
    """Phe's merged hypervector should be appreciably similar to both UUU and UUC encodings."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    phe = alphabet.amino_acid_hvs["Phe"]
    uuu = alphabet.encode_mrna("UUU")
    uuc = alphabet.encode_mrna("UUC")
    sim_uuu = p.cosine_similarity(phe, uuu).item()
    sim_uuc = p.cosine_similarity(phe, uuc).item()
    assert 0.3 < sim_uuu < 0.9
    assert 0.3 < sim_uuc < 0.9


@pytest.mark.parametrize("mode", MODES)
def test_unrelated_amino_acids_are_near_orthogonal(mode):
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    sim = p.similarity(alphabet.amino_acid_hvs["Phe"], alphabet.amino_acid_hvs["Asp"], mode=mode).item()
    assert abs(sim) < 5 * math.sqrt(DIM)


# ---------------------------------------------------------------------------
# HDCAlphabet: protein encoding (Phase 2 go/no-go)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_protein_encoding_matches_paper_formula(mode):
    """S = H_Met * rho^1(H_Phe) * rho^2(H_Ser) * rho^3(H_Gly) * rho^4(H_Stop)."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    sequence = ["Met", "Phe", "Ser", "Gly", "Stop"]
    hvs = [alphabet.amino_acid_hvs[acid] for acid in sequence]
    expected = hvs[0]
    for i, hv in enumerate(hvs[1:], start=1):
        expected = p.bind(expected, p.permute(hv, i), mode=mode)
    actual = alphabet.encode_protein(sequence)
    assert torch.equal(actual, expected)


@pytest.mark.parametrize("mode", MODES)
def test_protein_encoding_is_deterministic(mode):
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    sequence = ["Met", "Phe", "Ser", "Gly", "Ala", "Val", "Leu", "Trp", "Tyr", "Stop"]
    assert torch.equal(alphabet.encode_protein(sequence), alphabet.encode_protein(sequence))


@pytest.mark.parametrize("mode", MODES)
def test_10_amino_acid_protein_is_near_orthogonal_to_unrelated_sequences(mode):
    """Phase 2 go/no-go check: encode 10-amino-acid proteins and confirm unrelated
    sequences produce near-orthogonal hypervectors."""
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)
    n_pairs = 200
    sims = []
    for _ in range(n_pairs):
        seq1 = rng.choices(acids_no_stop, k=10)
        seq2 = rng.choices(acids_no_stop, k=10)
        h1 = alphabet.encode_protein(seq1)
        h2 = alphabet.encode_protein(seq2)
        sims.append(p.similarity(h1, h2, mode=mode).item())
    sims = torch.tensor(sims, dtype=torch.float64)
    expected_std = math.sqrt(DIM)
    standard_error_of_mean = expected_std / math.sqrt(n_pairs)
    assert abs(sims.mean().item()) < 5 * standard_error_of_mean


@pytest.mark.parametrize("mode", MODES)
def test_identical_protein_sequence_has_maximal_similarity(mode):
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    sequence = ["Met", "Phe", "Ser", "Gly", "Ala", "Val", "Leu", "Trp", "Tyr", "Stop"]
    hv = alphabet.encode_protein(sequence)
    assert p.similarity(hv, hv, mode=mode).item() == DIM


# ---------------------------------------------------------------------------
# HDCAlphabet: indel-tolerant encoding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_indel_tolerant_encoding_is_deterministic_with_fixed_generator(mode):
    alphabet = HDCAlphabet(DIM, mode=mode, seed=SEED)
    sequence = ["Met", "Phe", "Ser", "Gly", "Ala", "Val", "Leu", "Trp", "Tyr", "Stop", "Pro", "Cys"]
    g1 = torch.Generator()
    g1.manual_seed(42)
    g2 = torch.Generator()
    g2.manual_seed(42)
    hv1 = alphabet.encode_indel_tolerant(sequence, chunk_size=3, generator=g1)
    hv2 = alphabet.encode_indel_tolerant(sequence, chunk_size=3, generator=g2)
    assert torch.equal(hv1, hv2)


def test_indel_tolerant_encoding_is_more_robust_to_insertion_than_exact_encoding():
    """An insertion near the end should degrade similarity less for indel-tolerant
    encoding than for the exact (full-chain) protein encoding."""
    alphabet = HDCAlphabet(DIM, mode="binary", seed=SEED)
    acids_no_stop = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)
    base_seq = rng.choices(acids_no_stop, k=12)
    inserted_seq = base_seq[:9] + [rng.choice(acids_no_stop)] + base_seq[9:]

    gen = torch.Generator()
    gen.manual_seed(SEED)
    indel_base = alphabet.encode_indel_tolerant(base_seq, chunk_size=3, generator=gen)
    gen.manual_seed(SEED)
    indel_inserted = alphabet.encode_indel_tolerant(inserted_seq, chunk_size=3, generator=gen)
    indel_sim = p.cosine_similarity(indel_base, indel_inserted).item()

    exact_base = alphabet.encode_protein(base_seq)
    exact_inserted = alphabet.encode_protein(inserted_seq)
    exact_sim = p.cosine_similarity(exact_base, exact_inserted).item()

    assert indel_sim > exact_sim


def test_indel_tolerant_encoding_rejects_invalid_chunk_size():
    alphabet = HDCAlphabet(DIM, mode="binary", seed=SEED)
    with pytest.raises(ValueError):
        alphabet.encode_indel_tolerant(["Met", "Phe"], chunk_size=0)
