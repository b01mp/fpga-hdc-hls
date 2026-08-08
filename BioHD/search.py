"""BioHD similarity search: T-membership function and ROC evaluation.

Implements the thresholding logic of Section 3.3 (Eq. 2) and the ROC analysis of
Section 6.2 (Phase 4 of CLAUDE.md).
"""

from __future__ import annotations

import torch


def membership(similarity: torch.Tensor, dim: int, threshold: float) -> torch.Tensor:
    """T-membership function (Eq. 2): 1 if similarity >= threshold * dim, else 0."""
    return (similarity >= threshold * dim).to(torch.int8)


def true_positive_rate(stored_similarities: torch.Tensor, dim: int, threshold: float) -> float:
    """Fraction of stored (matching) patterns correctly identified as members at this threshold."""
    return membership(stored_similarities, dim, threshold).float().mean().item()


def false_positive_rate(unrelated_similarities: torch.Tensor, dim: int, threshold: float) -> float:
    """Fraction of unrelated (non-matching) patterns incorrectly identified as members."""
    return membership(unrelated_similarities, dim, threshold).float().mean().item()


def roc_curve(
    stored_similarities: torch.Tensor,
    unrelated_similarities: torch.Tensor,
    dim: int,
    thresholds: torch.Tensor | None = None,
    n_thresholds: int = 50,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Sweep threshold T_m in [0, 1] and compute (thresholds, TPR, FPR)."""
    if thresholds is None:
        thresholds = torch.linspace(0.0, 1.0, n_thresholds)
    tprs = torch.tensor([true_positive_rate(stored_similarities, dim, t.item()) for t in thresholds])
    fprs = torch.tensor([false_positive_rate(unrelated_similarities, dim, t.item()) for t in thresholds])
    return thresholds, tprs, fprs


def auc(fprs: torch.Tensor, tprs: torch.Tensor) -> float:
    """Area under the ROC curve via the trapezoidal rule (inputs need not be pre-sorted)."""
    order = torch.argsort(fprs)
    return torch.trapezoid(tprs[order], fprs[order]).item()


def best_threshold(
    stored_similarities: torch.Tensor,
    unrelated_similarities: torch.Tensor,
    dim: int,
    n_thresholds: int = 200,
) -> tuple[float, float, float]:
    """Pick the threshold maximizing Youden's J statistic (TPR - FPR).
    Returns (threshold, tpr, fpr) at that point."""
    thresholds, tprs, fprs = roc_curve(stored_similarities, unrelated_similarities, dim, n_thresholds=n_thresholds)
    j = tprs - fprs
    best_idx = int(torch.argmax(j).item())
    return thresholds[best_idx].item(), tprs[best_idx].item(), fprs[best_idx].item()
