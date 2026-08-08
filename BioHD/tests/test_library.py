"""Unit tests for library.py: sliding windows, capacity splitting, and adaptive refinement."""

import random

import pytest
import torch

import primitives as p
from encoder import AMINO_ACIDS, HDCAlphabet
from library import HDCLibrary, sliding_windows

DIM = 2_000
SEED = 0


# ---------------------------------------------------------------------------
# sliding_windows
# ---------------------------------------------------------------------------

def test_sliding_windows_basic():
    seq = list("ABCDEFGH")
    windows = sliding_windows(seq, window=3, stride=1)
    assert windows[0] == list("ABC")
    assert windows[1] == list("BCD")
    assert windows[-1] == list("FGH")
    assert len(windows) == len(seq) - 3 + 1


def test_sliding_windows_stride():
    seq = list(range(10))
    windows = sliding_windows(seq, window=2, stride=3)
    assert windows == [[0, 1], [3, 4], [6, 7]]


def test_sliding_windows_too_short_returns_empty():
    assert sliding_windows(list("AB"), window=5) == []


def test_sliding_windows_rejects_invalid_args():
    with pytest.raises(ValueError):
        sliding_windows(list("ABC"), window=0)
    with pytest.raises(ValueError):
        sliding_windows(list("ABC"), window=1, stride=0)


# ---------------------------------------------------------------------------
# HDCLibrary: storage & capacity
# ---------------------------------------------------------------------------

def test_add_pattern_accumulates_into_a_single_reference_under_capacity():
    lib = HDCLibrary(DIM, capacity=10)
    g = torch.Generator()
    g.manual_seed(SEED)
    hvs = p.random_hvs(3, DIM, mode="bipolar", generator=g)
    for hv in hvs:
        lib.add_pattern(hv)
    assert len(lib.references) == 1
    assert torch.equal(lib.references[0], hvs.to(torch.float32).sum(dim=0))


def test_add_pattern_splits_across_references_at_capacity():
    lib = HDCLibrary(DIM, capacity=2)
    g = torch.Generator()
    g.manual_seed(SEED)
    hvs = p.random_hvs(5, DIM, mode="binary", generator=g)
    for hv in hvs:
        lib.add_pattern(hv)
    # 5 patterns at capacity 2 -> references of size [2, 2, 1]
    assert len(lib.references) == 3
    assert lib.pattern_ref_idx == [0, 0, 1, 1, 2]


def test_recall_accuracy_of_empty_library_is_one():
    lib = HDCLibrary(DIM, capacity=10)
    assert lib.recall_accuracy() == 1.0


# ---------------------------------------------------------------------------
# HDCLibrary: protein sliding-window memorization
# ---------------------------------------------------------------------------

def test_add_sequence_windows_uses_alphabet_encoding():
    alphabet = HDCAlphabet(DIM, mode="binary", seed=SEED)
    acids = [a for a in AMINO_ACIDS if a != "Stop"]
    rng = random.Random(SEED)
    long_seq = rng.choices(acids, k=20)
    lib = HDCLibrary(DIM, capacity=100)
    n_added = lib.add_sequence_windows(alphabet, long_seq, window=5, stride=1)
    assert n_added == 20 - 5 + 1
    assert len(lib.pattern_hvs) == n_added
    expected_first = alphabet.encode_protein(long_seq[0:5])
    assert torch.equal(lib.pattern_hvs[0], expected_first)


# ---------------------------------------------------------------------------
# HDCLibrary: refinement (Section 3.3)
# ---------------------------------------------------------------------------

def test_refine_improves_or_maintains_recall_accuracy():
    """Heavily load several references so single-pass bundling causes mispredictions,
    then check that refinement does not make recall worse, and converges (returns a
    mistake count for each epoch, with the last epoch having <= mistakes than the first)."""
    g = torch.Generator()
    g.manual_seed(SEED)
    lib = HDCLibrary(DIM, capacity=50)
    # 4 references x 50 patterns each, using bipolar (full precision) hypervectors.
    hvs = p.random_hvs(200, DIM, mode="bipolar", generator=g)
    for hv in hvs:
        lib.add_pattern(hv)

    accuracy_before = lib.recall_accuracy()
    mistakes = lib.refine(epochs=15)
    accuracy_after = lib.recall_accuracy()

    assert accuracy_after >= accuracy_before
    assert mistakes[-1] <= mistakes[0]


def test_refine_converges_to_perfect_recall_on_small_easy_case():
    """With plenty of capacity headroom (small load per reference), refinement should be
    able to drive recall accuracy to 1.0."""
    g = torch.Generator()
    g.manual_seed(SEED)
    lib = HDCLibrary(DIM, capacity=5)
    hvs = p.random_hvs(20, DIM, mode="bipolar", generator=g)  # 4 references x 5 patterns
    for hv in hvs:
        lib.add_pattern(hv)

    lib.refine(epochs=30)
    assert lib.recall_accuracy() == 1.0


def test_query_returns_assigned_reference_for_lightly_loaded_library():
    g = torch.Generator()
    g.manual_seed(SEED)
    lib = HDCLibrary(DIM, capacity=1)  # one pattern per reference: trivially recallable
    hvs = p.random_hvs(10, DIM, mode="binary", generator=g)
    for hv in hvs:
        lib.add_pattern(hv)
    for i, hv in enumerate(hvs):
        predicted_idx, _ = lib.query(hv)
        assert predicted_idx == i
