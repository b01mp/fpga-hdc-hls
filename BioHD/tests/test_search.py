"""Unit tests for search.py: T-membership function and ROC evaluation."""

import torch

from search import auc, best_threshold, false_positive_rate, membership, roc_curve, true_positive_rate

DIM = 1_000


def test_membership_basic_threshold():
    sims = torch.tensor([0.0, 400.0, 500.0, 600.0, 1000.0])
    result = membership(sims, DIM, threshold=0.5)
    assert result.tolist() == [0, 0, 1, 1, 1]


def test_true_positive_rate_all_pass():
    sims = torch.full((10,), float(DIM))
    assert true_positive_rate(sims, DIM, threshold=0.5) == 1.0


def test_false_positive_rate_none_pass():
    sims = torch.zeros(10)
    assert false_positive_rate(sims, DIM, threshold=0.5) == 0.0


def test_roc_curve_endpoints():
    """At threshold 0, everything passes (TPR=FPR=1). At threshold 1, only similarities
    that equal the full dimension pass."""
    stored = torch.full((50,), float(DIM) * 0.9)
    unrelated = torch.zeros(50)
    thresholds, tprs, fprs = roc_curve(stored, unrelated, DIM, thresholds=torch.tensor([0.0, 1.0]))
    assert tprs[0].item() == 1.0
    assert fprs[0].item() == 1.0
    assert tprs[1].item() == 0.0
    assert fprs[1].item() == 0.0


def test_roc_curve_well_separated_populations_gives_high_auc():
    """If stored similarities are clearly higher than unrelated ones, AUC should be near 1.

    Note: BioHD's T_m convention sweeps thresholds in [0, 1] (a fraction of D), which only
    traces the FPR in [0, ~0.5] when noise is zero-centered (since half of zero-mean noise
    already exceeds T_m=0). To validate the generic `auc` helper against the standard full
    ROC space, this test sweeps a wider threshold range covering both populations.
    """
    g = torch.Generator()
    g.manual_seed(0)
    stored = DIM * 0.8 + torch.randn(500, generator=g) * 10
    unrelated = torch.randn(500, generator=g) * 10
    wide_thresholds = torch.linspace(-1.0, 1.0, 400)
    thresholds, tprs, fprs = roc_curve(stored, unrelated, DIM, thresholds=wide_thresholds)
    score = auc(fprs, tprs)
    assert score > 0.95


def test_best_threshold_separates_well_when_populations_differ():
    g = torch.Generator()
    g.manual_seed(0)
    stored = DIM * 0.8 + torch.randn(500, generator=g) * 10
    unrelated = torch.randn(500, generator=g) * 10
    threshold, tpr, fpr = best_threshold(stored, unrelated, DIM)
    assert tpr > 0.9
    assert fpr < 0.1


def test_best_threshold_on_identical_populations_has_low_separation():
    g = torch.Generator()
    g.manual_seed(0)
    stored = torch.randn(500, generator=g) * 10
    unrelated = torch.randn(500, generator=g) * 10
    _, tpr, fpr = best_threshold(stored, unrelated, DIM)
    assert abs(tpr - fpr) < 0.2
