"""Evaluation harness tests."""

from __future__ import annotations

import json
import os

import pytest

from interciter.evaluation import metrics
from interciter.evaluation.gold import load_gold, load_gold_named
from interciter.evaluation.harness import evaluate

_NET = os.environ.get("INTERCITER_NET_TESTS") == "1"
_netonly = pytest.mark.skipif(not _NET, reason="network test; set INTERCITER_NET_TESTS=1")


def test_gold_corpus_loads():
    gold = load_gold()
    assert len(gold.papers) == 2
    assert gold.all_claims()


def test_harness_runs_and_reports_all_stages():
    report = evaluate()

    # Parsing: the sample citations and sections resolve exactly.
    assert report.parsing.citation_resolution_accuracy == 1.0
    assert report.parsing.citations_evaluated == 3
    assert report.parsing.section_recognition_accuracy == 1.0

    # Claim extraction aligns against gold result claims.
    assert report.claim_extraction.spans.tp > 0
    assert report.claim_extraction.spans.f1 == 1.0
    assert report.claim_extraction.effect_direction_accuracy == 1.0

    # Relationship classification measured separately for function and stance.
    assert report.function_classification.n == 3
    assert 0.0 <= report.function_classification.macro_f1 <= 1.0
    assert report.stance_classification.macro_f1 == 1.0

    # Target retrieval.
    assert report.target_retrieval.recall_at_1 == 1.0
    assert report.target_retrieval.precision_at_threshold == 1.0

    # Operations.
    assert report.operations.papers == 2
    assert report.operations.cost_per_paper_usd == 0.0


def test_calibration_is_measured_and_selective():
    report = evaluate()
    cal = report.calibration
    assert 0.0 <= cal.ece <= 1.0
    # The stub is accurate but over/under-confident, so ECE is a real, non-zero signal.
    assert cal.ece > 0.0
    assert cal.accuracy == 1.0
    assert len(cal.risk_coverage) == 4


def test_clustering_recall_is_measured():
    report = evaluate()
    cl = report.clustering
    # No spurious groupings, but the stub under-recalls equivalence (measured, not hidden).
    assert cl.precision == 1.0
    assert cl.recall < 1.0


# --- Real PMC-OA gold corpus (offline validation + network-gated run) -----------


def test_real_corpus_loads_and_is_wellformed_offline():
    """Loads and validates without any network access (no full text is fetched)."""
    gold = load_gold_named("t2d_glycemic_v1")
    assert gold.source == "pmc-oa"
    # Sparsely annotated real papers: precision must be suppressed, recall reported.
    assert gold.exhaustive_claims is False
    assert len(gold.papers) >= 9
    assert all(p.pmcid and p.doi and p.license for p in gold.papers)

    # Antecedents precede citers by ingestion order.
    orders = [p.order for p in gold.papers]
    assert orders == sorted(orders)

    # Every claim_resolved relation targets an in-corpus antecedent claim id.
    gold_ids = {c.gold_id for c in gold.all_claims()}
    resolved_targets = [
        r.target_gold_id
        for p in gold.papers
        for c in p.claims
        for r in c.relations
        if r.resolution.value == "claim_resolved"
    ]
    assert resolved_targets, "pilot should exercise at least one claim_resolved relation"
    assert all(t in gold_ids for t in resolved_targets)

    # At least one equivalence group spans independent papers (literature corroboration,
    # distinct from same-paper model agreement).
    paper_of = {c.gold_id: p.doi for p in gold.papers for c in p.claims}
    cross_paper = [
        group for group in gold.equivalences if len({paper_of.get(g) for g in group}) >= 2
    ]
    assert cross_paper, "expected a cross-paper corroboration equivalence group"
    # Multiple drug clusters (e.g. semaglutide, ecnoglutide, tirzepatide).
    assert len(cross_paper) >= 3


@_netonly
def test_real_corpus_evaluates_end_to_end():
    report = evaluate(load_gold_named("t2d_glycemic_v1"))
    assert report.claim_extraction.exhaustive is False
    assert report.claim_extraction.spans.recall > 0.0
    assert report.parsing.citation_resolution_accuracy > 0.0


def test_report_serializes_to_json():
    report = evaluate()
    payload = json.dumps(report.to_dict())
    assert "function_classification" in payload
    assert report.format_text().startswith("InterCiter evaluation")


# --- metric primitives ------------------------------------------------------


def test_prf_basic():
    p, r, f = metrics.prf(2, 1, 1)
    assert round(p, 3) == 0.667
    assert round(r, 3) == 0.667


def test_recall_at_k():
    assert metrics.recall_at_k([1, None, 3], 1) == round(1 / 3, 4)
    assert metrics.recall_at_k([1, None, 3], 3) == round(2 / 3, 4)


def test_pair_prf():
    gold = {frozenset({"a", "b"}), frozenset({"a", "c"})}
    pred = {frozenset({"a", "b"})}
    p, r, f, tp, fp, fn = metrics.pair_prf(gold, pred)
    assert (tp, fp, fn) == (1, 0, 1)
    assert p == 1.0
    assert r == 0.5


def test_ece_flags_overconfidence():
    # Always correct but only 60% confident -> ECE reflects the 0.4 gap.
    assert metrics.expected_calibration_error([0.6, 0.6], [True, True]) == 0.4
    assert metrics.expected_calibration_error([1.0, 1.0], [True, True]) == 0.0
