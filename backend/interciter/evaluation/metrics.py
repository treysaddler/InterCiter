"""Metric primitives — pure functions over labels and scores.

Kept deliberately dependency-free (no numpy) so the harness stays lightweight. Every
helper is defensive about empty inputs and returns ``0.0`` rather than dividing by zero.
"""

from __future__ import annotations

from collections import defaultdict


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Precision, recall, F1 from raw counts."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


def confusion_matrix(
    pairs: list[tuple[str, str]], labels: list[str]
) -> dict[str, dict[str, int]]:
    """Confusion matrix indexed ``matrix[gold][predicted]``."""
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for gold, pred in pairs:
        if gold in matrix and pred in matrix[gold]:
            matrix[gold][pred] += 1
    return matrix


def per_class_prf(
    pairs: list[tuple[str, str]], labels: list[str]
) -> tuple[dict[str, tuple[float, float, float, int]], float]:
    """Per-class (precision, recall, f1, support) plus macro-F1 over classes with support."""
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    support: dict[str, int] = defaultdict(int)
    for gold, pred in pairs:
        support[gold] += 1
        if gold == pred:
            tp[gold] += 1
        else:
            fp[pred] += 1
            fn[gold] += 1

    result: dict[str, tuple[float, float, float, int]] = {}
    f1s: list[float] = []
    for label in labels:
        p, r, f = prf(tp[label], fp[label], fn[label])
        result[label] = (p, r, f, support[label])
        if support[label] > 0:
            f1s.append(f)
    macro_f1 = round(sum(f1s) / len(f1s), 4) if f1s else 0.0
    return result, macro_f1


def expected_calibration_error(
    confidences: list[float], corrects: list[bool], n_bins: int = 5
) -> float:
    """Expected Calibration Error (ECE): weighted gap between confidence and accuracy."""
    if not confidences:
        return 0.0
    n = len(confidences)
    total = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        # Include the right edge in the final bin.
        idx = [
            i
            for i, c in enumerate(confidences)
            if (lo < c <= hi) or (b == 0 and c <= lo)
        ]
        if not idx:
            continue
        avg_conf = sum(confidences[i] for i in idx) / len(idx)
        acc = sum(1 for i in idx if corrects[i]) / len(idx)
        total += (len(idx) / n) * abs(avg_conf - acc)
    return round(total, 4)


def risk_coverage(
    confidences: list[float], corrects: list[bool], coverages: list[float]
) -> list[tuple[float, float]]:
    """Selective risk (error rate) at each coverage level, answering most-confident first."""
    if not confidences:
        return [(cov, 0.0) for cov in coverages]
    order = sorted(range(len(confidences)), key=lambda i: confidences[i], reverse=True)
    n = len(order)
    out: list[tuple[float, float]] = []
    for cov in coverages:
        k = max(1, round(cov * n))
        chosen = order[:k]
        errors = sum(1 for i in chosen if not corrects[i])
        out.append((round(cov, 3), round(errors / k, 4)))
    return out


def recall_at_k(ranks: list[int | None], k: int) -> float:
    """Fraction of items whose gold target appears at rank <= k (1-indexed)."""
    if not ranks:
        return 0.0
    hits = sum(1 for r in ranks if r is not None and r <= k)
    return round(hits / len(ranks), 4)


def pair_prf(
    gold_pairs: set[frozenset[str]], pred_pairs: set[frozenset[str]]
) -> tuple[float, float, float, int, int, int]:
    """Pairwise precision/recall/F1 for clustering, plus TP/FP/FN counts."""
    tp = len(gold_pairs & pred_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)
    p, r, f = prf(tp, fp, fn)
    return p, r, f, tp, fp, fn
