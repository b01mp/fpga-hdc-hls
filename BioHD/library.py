"""BioHD reference library: sliding-window memorization and adaptive refinement.

Implements Sections 3.2-3.3 of the paper (Phase 3 of CLAUDE.md).
"""

from __future__ import annotations

from typing import Sequence

import torch

from encoder import HDCAlphabet


def sliding_windows(sequence: Sequence, window: int, stride: int = 1) -> list[list]:
    """Generate overlapping windows of length `window` from `sequence`, step `stride`.

    Mirrors Section 3.2: "A window moves through a [sequence], and BioHD encodes a
    [sub]sequence in each window."
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if stride < 1:
        raise ValueError("stride must be >= 1")
    if window > len(sequence):
        return []
    return [list(sequence[i:i + window]) for i in range(0, len(sequence) - window + 1, stride)]


class HDCLibrary:
    """Stores encoded sequence patterns in one or more reference hypervectors.

    Patterns are grouped into reference hypervectors of at most `capacity` patterns each
    (Section 3.2: "each hypervector stores the information of a pre-defined number of
    patterns"). References are kept as full-precision (float32) tensors internally, since
    adaptive refinement (Section 3.3) applies fractional updates regardless of the
    hypervector `mode` ("binary" or "bipolar") used to encode the patterns themselves.
    """

    def __init__(self, dim: int, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.dim = dim
        self.capacity = capacity
        self.references: list[torch.Tensor] = []
        self.pattern_hvs: list[torch.Tensor] = []
        self.pattern_ref_idx: list[int] = []
        self._current_count = 0

    def _ensure_capacity(self) -> int:
        if not self.references or self._current_count >= self.capacity:
            self.references.append(torch.zeros(self.dim, dtype=torch.float32))
            self._current_count = 0
        self._current_count += 1
        return len(self.references) - 1

    def add_pattern(self, hv: torch.Tensor) -> int:
        """Add an already-encoded pattern hypervector R += S (Section 3.2: R = sum_j S_j).
        Returns the index of the reference hypervector it was assigned to."""
        ref_idx = self._ensure_capacity()
        self.references[ref_idx] = self.references[ref_idx] + hv.to(torch.float32)
        self.pattern_hvs.append(hv)
        self.pattern_ref_idx.append(ref_idx)
        return ref_idx

    def add_sequence_windows(
        self, alphabet: HDCAlphabet, long_sequence: Sequence[str], window: int, stride: int = 1
    ) -> int:
        """Sliding-window scan a long reference sequence (e.g. a protein), encoding and
        memorizing each window. Returns the number of windows added."""
        n_added = 0
        for win in sliding_windows(long_sequence, window, stride):
            hv = alphabet.encode_protein(win)
            self.add_pattern(hv)
            n_added += 1
        return n_added

    def similarities(self, query_hv: torch.Tensor) -> torch.Tensor:
        """Dot-product similarity of `query_hv` against every reference hypervector."""
        if not self.references:
            return torch.empty(0)
        q = query_hv.to(torch.float32)
        refs = torch.stack(self.references)
        return refs @ q

    def query(self, query_hv: torch.Tensor) -> tuple[int, float]:
        """Return (best_reference_index, best_similarity)."""
        sims = self.similarities(query_hv)
        best = int(torch.argmax(sims).item())
        return best, sims[best].item()

    def refine(self, epochs: int = 10, lr: float = 1.0) -> list[int]:
        """Adaptive library refinement (Section 3.3): for each stored pattern, if its
        best-matching reference isn't the one it was assigned to, push it toward the
        correct reference and pull it away from the incorrect one:

            R_correct += lr * (1 - R_correct.S/D) * S
            R_wrong   -= lr * (1 - R_wrong.S/D)   * S

        Returns the number of mispredictions made (and corrected) at each epoch; an empty
        suffix means it converged (0 mistakes) before using all `epochs`.
        """
        mistakes_per_epoch = []
        for _ in range(epochs):
            mistakes = 0
            for i, s in enumerate(self.pattern_hvs):
                correct_idx = self.pattern_ref_idx[i]
                sims = self.similarities(s)
                predicted_idx = int(torch.argmax(sims).item())
                if predicted_idx != correct_idx:
                    mistakes += 1
                    s_f = s.to(torch.float32)
                    r_correct = self.references[correct_idx]
                    r_wrong = self.references[predicted_idx]
                    self.references[correct_idx] = r_correct + lr * (1 - (r_correct @ s_f) / self.dim) * s_f
                    self.references[predicted_idx] = r_wrong - lr * (1 - (r_wrong @ s_f) / self.dim) * s_f
            mistakes_per_epoch.append(mistakes)
            if mistakes == 0:
                break
        return mistakes_per_epoch

    def recall_accuracy(self) -> float:
        """Fraction of stored patterns whose best-matching reference is the one they were
        assigned to (Section 3.3's notion of "correctly identify match")."""
        if not self.pattern_hvs:
            return 1.0
        correct = 0
        for i, s in enumerate(self.pattern_hvs):
            predicted_idx, _ = self.query(s)
            if predicted_idx == self.pattern_ref_idx[i]:
                correct += 1
        return correct / len(self.pattern_hvs)
