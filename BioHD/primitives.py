"""Core HDC primitives: bind, bundle, permute, similarity.

Two interchangeable representations are supported via the `mode` flag:

- "binary":  hypervectors are {0,1}-valued. bind = XOR, similarity = Hamming-based.
- "bipolar": hypervectors are {-1,+1}-valued. bind = elementwise multiply, similarity = dot product.

The two representations are related by the affine map x -> 1 - 2x and produce the
same near-orthogonality statistics for random hypervectors: for independent random
hypervectors A, B of dimension D, similarity(A, B) ~ 2*Binomial(D, 0.5) - D, which
has mean 0 and standard deviation sqrt(D).
"""

from __future__ import annotations

import torch

Mode = str  # "binary" or "bipolar"

_VALID_MODES = ("binary", "bipolar")


def _check_mode(mode: Mode) -> None:
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {_VALID_MODES}, got {mode!r}")


def random_hv(dim: int, mode: Mode = "binary", generator: torch.Generator | None = None) -> torch.Tensor:
    """Generate a single random hypervector of dimension `dim`."""
    return random_hvs(1, dim, mode=mode, generator=generator)[0]


def random_hvs(n: int, dim: int, mode: Mode = "binary", generator: torch.Generator | None = None) -> torch.Tensor:
    """Generate `n` i.i.d. random hypervectors, stacked as an (n, dim) tensor."""
    _check_mode(mode)
    bits = torch.randint(0, 2, (n, dim), generator=generator, dtype=torch.int64)
    if mode == "binary":
        return bits.to(torch.int8)
    return (1 - 2 * bits).to(torch.int8)  # 0 -> +1, 1 -> -1


def bind(a: torch.Tensor, b: torch.Tensor, mode: Mode = "binary") -> torch.Tensor:
    """Bind two hypervectors: XOR for binary, elementwise multiply for bipolar.

    Binding is its own inverse: bind(bind(a, b), b) == a.
    """
    _check_mode(mode)
    if mode == "binary":
        return torch.bitwise_xor(a.to(torch.int8), b.to(torch.int8))
    return a * b


def bundle(vectors: torch.Tensor, mode: Mode = "binary") -> torch.Tensor:
    """Bundle a stack of hypervectors, shape (n, dim), into one reference hypervector.

    - "binary": per-dimension majority vote (ties broken toward 1).
    - "bipolar": elementwise sum kept at full precision (no re-binarization), so the
      result can store more information than a single binary hypervector at the cost
      of needing dot-product (rather than Hamming) similarity.
    """
    _check_mode(mode)
    if vectors.ndim != 2:
        raise ValueError("vectors must be a 2D (n, dim) tensor")
    n = vectors.shape[0]
    if mode == "binary":
        counts = vectors.to(torch.int64).sum(dim=0)
        return (2 * counts >= n).to(torch.int8)
    return vectors.to(torch.int64).sum(dim=0)


def permute(hv: torch.Tensor, shifts: int = 1) -> torch.Tensor:
    """Cyclically rotate a hypervector by `shifts` positions (rho^shifts)."""
    return torch.roll(hv, shifts=shifts, dims=-1)


def hamming_distance(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Number of differing positions between two (batches of) hypervectors."""
    return (a != b).sum(dim=-1)


def similarity(a: torch.Tensor, b: torch.Tensor, mode: Mode = "binary") -> torch.Tensor:
    """Similarity on a shared scale: ~2*Binomial(D,0.5)-D for unrelated random hypervectors.

    - "binary": D - 2 * Hamming distance (numerically equal to the bipolar dot product).
    - "bipolar": direct dot product.
    """
    _check_mode(mode)
    if mode == "binary":
        dim = a.shape[-1]
        return dim - 2 * hamming_distance(a, b)
    return (a.to(torch.int64) * b.to(torch.int64)).sum(dim=-1)


def cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Normalized similarity in [-1, 1], usable on any integer/float representation
    (e.g. a full-precision bundled reference hypervector)."""
    a = a.to(torch.float32)
    b = b.to(torch.float32)
    return (a * b).sum(dim=-1) / (a.norm(dim=-1) * b.norm(dim=-1))
