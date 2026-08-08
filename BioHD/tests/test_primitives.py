"""Unit tests for primitives.py.

Verifies the distributional properties demanded by Phase 1 of CLAUDE.md:
unit tests pass, and 1000 random hypervector pairs show dot products
(== similarity scores) clustered near 0.
"""

import math

import pytest
import torch

import primitives as p

MODES = ("binary", "bipolar")
DIM = 10_000
SEED = 0


def _gen(seed: int = SEED) -> torch.Generator:
    g = torch.Generator()
    g.manual_seed(seed)
    return g


@pytest.mark.parametrize("mode", MODES)
def test_random_hv_value_range(mode):
    hv = p.random_hv(DIM, mode=mode, generator=_gen())
    expected = {0, 1} if mode == "binary" else {-1, 1}
    assert set(torch.unique(hv).tolist()) <= expected


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        p.random_hv(10, mode="not-a-mode")
    a, b = p.random_hv(10), p.random_hv(10)
    with pytest.raises(ValueError):
        p.bind(a, b, mode="not-a-mode")
    with pytest.raises(ValueError):
        p.similarity(a, b, mode="not-a-mode")


@pytest.mark.parametrize("mode", MODES)
def test_bind_is_self_inverse(mode):
    """bind(bind(a, b), b) == a for both XOR and bipolar-multiply binding."""
    g = _gen()
    a = p.random_hv(DIM, mode=mode, generator=g)
    b = p.random_hv(DIM, mode=mode, generator=g)
    bound = p.bind(a, b, mode=mode)
    recovered = p.bind(bound, b, mode=mode)
    assert torch.equal(recovered, a)


@pytest.mark.parametrize("mode", MODES)
def test_bind_with_self_collapses(mode):
    """A bound with itself carries no information: all zeros (XOR) / all ones (bipolar)."""
    a = p.random_hv(DIM, mode=mode, generator=_gen())
    bound = p.bind(a, a, mode=mode)
    expected = torch.zeros(DIM, dtype=torch.int8) if mode == "binary" else torch.ones(DIM, dtype=torch.int8)
    assert torch.equal(bound, expected)


@pytest.mark.parametrize("mode", MODES)
def test_bind_produces_near_orthogonal_vector(mode):
    """delta(bind(A, B), A) ~= 0: binding maps to an unrelated region of hyperspace."""
    g = _gen()
    a = p.random_hv(DIM, mode=mode, generator=g)
    b = p.random_hv(DIM, mode=mode, generator=g)
    bound = p.bind(a, b, mode=mode)
    sim = p.similarity(bound, a, mode=mode).item()
    # Expected to behave like similarity between two independent random HVs: mean 0, std sqrt(D).
    assert abs(sim) < 5 * math.sqrt(DIM)


@pytest.mark.parametrize("mode", MODES)
def test_bundle_preserves_similarity_to_components(mode):
    """delta(bundle([A, B]), A) >> 0: bundling preserves similarity to its inputs."""
    g = _gen()
    a = p.random_hv(DIM, mode=mode, generator=g)
    b = p.random_hv(DIM, mode=mode, generator=g)
    bundled = p.bundle(torch.stack([a, b]), mode=mode)
    sim = p.cosine_similarity(bundled, a).item()
    assert sim > 0.5


@pytest.mark.parametrize("mode", MODES)
def test_bundle_rejects_non_2d_input(mode):
    a = p.random_hv(DIM, mode=mode)
    with pytest.raises(ValueError):
        p.bundle(a, mode=mode)


def test_permute_changes_the_vector():
    a = p.random_hv(DIM, generator=_gen())
    rotated = p.permute(a, shifts=1)
    assert not torch.equal(a, rotated)


def test_permute_is_invertible():
    a = p.random_hv(DIM, generator=_gen())
    rotated = p.permute(a, shifts=3)
    restored = p.permute(rotated, shifts=-3)
    assert torch.equal(a, restored)


def test_permute_produces_near_orthogonal_vector():
    """delta(A, rho(A)) ~= 0, as claimed in the paper's background section."""
    a = p.random_hv(DIM, generator=_gen())
    rotated = p.permute(a, shifts=1)
    sim = p.similarity(a, rotated, mode="binary").item()
    assert abs(sim) < 5 * math.sqrt(DIM)


@pytest.mark.parametrize("mode", MODES)
def test_similarity_of_identical_vector_is_maximal(mode):
    a = p.random_hv(DIM, mode=mode, generator=_gen())
    sim = p.similarity(a, a, mode=mode).item()
    assert sim == DIM


@pytest.mark.parametrize("mode", MODES)
def test_dot_products_of_random_pairs_cluster_near_zero(mode):
    """Phase 1 go/no-go check: 1000 random HV pairs show dot products clustered near 0.

    For independent random hypervectors, similarity ~ 2*Binomial(D, 0.5) - D, which has
    mean 0 and standard deviation sqrt(D). We check the empirical mean of 1000 samples
    falls well within a few standard errors of 0, and the empirical std is close to sqrt(D).
    """
    n_pairs = 1000
    g = _gen()
    a = p.random_hvs(n_pairs, DIM, mode=mode, generator=g)
    b = p.random_hvs(n_pairs, DIM, mode=mode, generator=g)
    sims = p.similarity(a, b, mode=mode).to(torch.float64)

    expected_std = math.sqrt(DIM)
    standard_error_of_mean = expected_std / math.sqrt(n_pairs)

    mean = sims.mean().item()
    std = sims.std().item()

    assert abs(mean) < 4 * standard_error_of_mean
    assert abs(std - expected_std) / expected_std < 0.1
