"""BioHD genome sequence encoding: mRNA -> amino acid -> protein, plus indel-tolerant chunking.

Implements Section 3.1 of the paper (Phase 2 of CLAUDE.md), built entirely on top of the
primitives in primitives.py (bind, bundle, permute, similarity).
"""

from __future__ import annotations

from typing import Sequence

import torch

import primitives as p

RNA_BASES: tuple[str, ...] = ("A", "C", "G", "U")
DNA_BASES: tuple[str, ...] = ("A", "C", "G", "T")
# Union of bases an HDCAlphabet generates hypervectors for, so encode_mrna works on raw DNA
# (Section 5.6: "for DNA and RNA alignment ... Sigma = {A,C,G,T}") as well as RNA/codon strings.
ALL_BASES: tuple[str, ...] = ("A", "C", "G", "U", "T")

# Standard genetic code (RNA codon -> 3-letter amino acid code), matching Figure 1b of the paper.
CODON_TABLE: dict[str, str] = {
    "UUU": "Phe", "UUC": "Phe", "UUA": "Leu", "UUG": "Leu",
    "UCU": "Ser", "UCC": "Ser", "UCA": "Ser", "UCG": "Ser",
    "UAU": "Tyr", "UAC": "Tyr", "UAA": "Stop", "UAG": "Stop",
    "UGU": "Cys", "UGC": "Cys", "UGA": "Stop", "UGG": "Trp",
    "CUU": "Leu", "CUC": "Leu", "CUA": "Leu", "CUG": "Leu",
    "CCU": "Pro", "CCC": "Pro", "CCA": "Pro", "CCG": "Pro",
    "CAU": "His", "CAC": "His", "CAA": "Gln", "CAG": "Gln",
    "CGU": "Arg", "CGC": "Arg", "CGA": "Arg", "CGG": "Arg",
    "AUU": "Ile", "AUC": "Ile", "AUA": "Ile", "AUG": "Met",
    "ACU": "Thr", "ACC": "Thr", "ACA": "Thr", "ACG": "Thr",
    "AAU": "Asn", "AAC": "Asn", "AAA": "Lys", "AAG": "Lys",
    "AGU": "Ser", "AGC": "Ser", "AGA": "Arg", "AGG": "Arg",
    "GUU": "Val", "GUC": "Val", "GUA": "Val", "GUG": "Val",
    "GCU": "Ala", "GCC": "Ala", "GCA": "Ala", "GCG": "Ala",
    "GAU": "Asp", "GAC": "Asp", "GAA": "Glu", "GAG": "Glu",
    "GGU": "Gly", "GGC": "Gly", "GGA": "Gly", "GGG": "Gly",
}

AMINO_ACIDS: tuple[str, ...] = tuple(sorted(set(CODON_TABLE.values())))


def codons_for(amino_acid: str) -> list[str]:
    """All RNA codons that translate to the given 3-letter amino acid code."""
    return [codon for codon, acid in CODON_TABLE.items() if acid == amino_acid]


def probabilistic_merge(vectors: torch.Tensor | Sequence[torch.Tensor], generator: torch.Generator | None = None) -> torch.Tensor:
    """Merge n >= 2 hypervectors into one by sampling each dimension from a uniformly
    random source vector (~1/n of dimensions come from each input).

    For n == 2 this is exactly the paper's "probabilistic merge" (⌢): random half-dimension
    sampling from the first and second hypervector. The merged result is correlated with
    every input but identical to none of them.
    """
    stacked = torch.stack(list(vectors)) if not isinstance(vectors, torch.Tensor) else vectors
    if stacked.ndim != 2:
        raise ValueError("vectors must be a 2D (n, dim) tensor")
    n, dim = stacked.shape
    if n < 2:
        raise ValueError("probabilistic_merge requires at least 2 vectors")
    choice = torch.randint(0, n, (dim,), generator=generator)
    return stacked[choice, torch.arange(dim)]


def correlated_position_hvs(
    n: int,
    dim: int,
    mode: p.Mode = "binary",
    target_final_similarity: float = 0.05,
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """Generate n position hypervectors P1..Pn, shape (n, dim), where adjacent positions are
    highly similar (small bit-flip step) while the first and last become near-orthogonal.

    Each dimension independently follows a two-state Markov chain that flips with per-step
    probability q. Solving for the expected similarity between P1 and Pn after n-1 steps gives
    q = (1 - target_final_similarity ** (1 / (n - 1))) / 2.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    hvs = torch.empty((n, dim), dtype=torch.int8)
    hvs[0] = p.random_hv(dim, mode=mode, generator=generator)
    if n == 1:
        return hvs
    flip_prob = (1 - target_final_similarity ** (1 / (n - 1))) / 2
    for i in range(1, n):
        flips = torch.rand(dim, generator=generator) < flip_prob
        hvs[i] = hvs[i - 1].clone()
        if mode == "binary":
            hvs[i][flips] = 1 - hvs[i][flips]
        else:
            hvs[i][flips] = -hvs[i][flips]
    return hvs


class HDCAlphabet:
    """Fixed set of base/amino-acid hypervectors for a given dimension, mode, and seed.

    Construct once per (dim, mode) configuration and reuse it for all encoding calls so that
    results are deterministic and comparable.
    """

    def __init__(self, dim: int, mode: p.Mode = "binary", seed: int = 0):
        self.dim = dim
        self.mode = mode
        self.seed = seed

        base_gen = torch.Generator()
        base_gen.manual_seed(seed)
        bases = p.random_hvs(len(ALL_BASES), dim, mode=mode, generator=base_gen)
        self.base_hvs: dict[str, torch.Tensor] = {base: bases[i] for i, base in enumerate(ALL_BASES)}

        self.amino_acid_hvs: dict[str, torch.Tensor] = {}
        for offset, amino_acid in enumerate(AMINO_ACIDS):
            merge_gen = torch.Generator()
            merge_gen.manual_seed(seed + 1 + offset)
            self.amino_acid_hvs[amino_acid] = self._encode_amino_acid(amino_acid, merge_gen)

    def encode_chain(self, hvs: Sequence[torch.Tensor]) -> torch.Tensor:
        """Bind a sequence of hypervectors with positional permutation:
        h0 * rho^1(h1) * rho^2(h2) * ... * rho^(k-1)(h_{k-1})."""
        if len(hvs) == 0:
            raise ValueError("hvs must be non-empty")
        result = hvs[0]
        for i, hv in enumerate(hvs[1:], start=1):
            result = p.bind(result, p.permute(hv, shifts=i), mode=self.mode)
        return result

    def encode_mrna(self, seq: str) -> torch.Tensor:
        """Encode a raw nucleotide sequence (e.g. 'ACGU') by binding its base hypervectors."""
        return self.encode_chain([self.base_hvs[base] for base in seq])

    def _encode_amino_acid(self, amino_acid: str, generator: torch.Generator) -> torch.Tensor:
        codon_hvs = [self.encode_mrna(codon) for codon in codons_for(amino_acid)]
        if len(codon_hvs) == 1:
            return codon_hvs[0]
        return probabilistic_merge(codon_hvs, generator=generator)

    def encode_protein(self, sequence: Sequence[str]) -> torch.Tensor:
        """Encode a protein given as a list of 3-letter amino-acid codes,
        e.g. ['Met', 'Phe', 'Ser', 'Gly', 'Stop']."""
        return self.encode_chain([self.amino_acid_hvs[acid] for acid in sequence])

    def encode_indel_tolerant(
        self,
        sequence: Sequence[str],
        chunk_size: int,
        generator: torch.Generator | None = None,
    ) -> torch.Tensor:
        """Encode a protein in a way that's robust to small insertions/deletions: split into
        non-overlapping chunks, bind each chunk independently, then bundle the chunks together
        weighted by correlated position hypervectors (Q = P1*S1 + P2*S2 + ... + Pk*Sk).

        Because the P_i are correlated, an indel that shifts later chunks degrades similarity
        gracefully instead of destroying it the way full-sequence binding would.
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        chunks = [sequence[i:i + chunk_size] for i in range(0, len(sequence), chunk_size)]
        chunk_hvs = torch.stack([
            self.encode_chain([self.amino_acid_hvs[acid] for acid in chunk]) for chunk in chunks
        ])
        positions = correlated_position_hvs(len(chunks), self.dim, mode=self.mode, generator=generator)
        bound = torch.stack([
            p.bind(positions[i], chunk_hvs[i], mode=self.mode) for i in range(len(chunks))
        ])
        return p.bundle(bound, mode=self.mode)
