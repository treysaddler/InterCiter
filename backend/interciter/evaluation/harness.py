"""The evaluation runner.

Ingests the gold papers into an isolated in-memory database, aligns the pipeline's
predictions to the adjudicated gold labels, and scores every stage separately. Alignment
of predicted claims to gold claims is by content-token overlap (a stand-in for span
matching), so the same harness works unchanged when the extractor is swapped.
"""

from __future__ import annotations

import re
import time
from itertools import combinations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .. import models
from ..config import get_settings
from ..enums import (
    MembershipStatus,
    OccurrenceType,
    RelationFunction,
    RelationResolution,
    RelationStance,
)
from ..ingestion.extractor import Extractor, default_extractor
from ..ingestion.pipeline import ingest_paper
from ..models import Base
from ..schemas import ClaimView
from ..services import projection
from . import metrics
from .gold import GoldCorpus, load_gold, load_paper_xml
from .report import (
    CalibrationReport,
    ClaimExtractionReport,
    ClassificationReport,
    ClassMetrics,
    EvaluationReport,
    OperationsReport,
    ParsingReport,
    PRF,
    TargetRetrievalReport,
)

_STOP = {
    "the", "a", "an", "of", "in", "on", "and", "or", "to", "for", "with", "was",
    "were", "is", "are", "be", "been", "that", "this", "these", "those", "we",
    "our", "by", "as", "at", "from", "not", "no", "than", "which", "it", "its",
}
_TOKEN = re.compile(r"[a-z0-9]+")
_ALIGN_THRESHOLD = 0.3
_COVERAGES = [0.25, 0.5, 0.75, 1.0]


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in _STOP}


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _isolated_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def _align(
    gold_claims, pred_claims: list[ClaimView]
) -> dict[str, ClaimView]:
    """Greedy one-to-one alignment of gold claims to predicted claims by token overlap."""
    scored = []
    for g in gold_claims:
        for pc in pred_claims:
            s = _overlap(g.text, pc.normalized_text)
            if s >= _ALIGN_THRESHOLD:
                scored.append((s, g.gold_id, pc))
    scored.sort(key=lambda x: x[0], reverse=True)
    used_gold: set[str] = set()
    used_pred: set[str] = set()
    mapping: dict[str, ClaimView] = {}
    for _, gold_id, pc in scored:
        if gold_id in used_gold or pc.interpretation_id in used_pred:
            continue
        mapping[gold_id] = pc
        used_gold.add(gold_id)
        used_pred.add(pc.interpretation_id)
    return mapping


def _mentions_for_work(session: Session, work_id: str) -> dict[str, str | None]:
    """marker text -> cited work DOI, for one paper's citation mentions."""
    stmt = (
        select(models.CitationMention, models.PaperWork.doi)
        .join(models.Passage, models.CitationMention.passage_id == models.Passage.passage_id)
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .outerjoin(
            models.PaperWork,
            models.CitationMention.cited_work_id == models.PaperWork.work_id,
        )
        .where(models.PaperVersion.work_id == work_id)
    )
    out: dict[str, str | None] = {}
    for mention, cited_doi in session.execute(stmt):
        out[mention.marker_span] = cited_doi
    return out


def evaluate(
    gold: GoldCorpus | None = None, extractor: Extractor | None = None
) -> EvaluationReport:
    gold = gold or load_gold()
    extractor = extractor or default_extractor()
    session = _isolated_session()
    settings = get_settings()

    # 1. Ingest gold papers in adjudicated order, timing each.
    latencies: list[float] = []
    for paper in sorted(gold.papers, key=lambda p: p.order):
        xml = load_paper_xml(paper, settings)
        start = time.perf_counter()
        ingest_paper(session, xml=xml, extractor=extractor, settings=settings)
        latencies.append(time.perf_counter() - start)

    # 2. Index works and predictions.
    works = list(session.scalars(select(models.PaperWork)))
    work_by_doi = {w.doi: w for w in works if w.doi}
    work_by_id = {w.work_id: w for w in works}

    pred_by_doi: dict[str, list[ClaimView]] = {}
    for paper in gold.papers:
        work = work_by_doi.get(paper.doi)
        pred_by_doi[paper.doi] = (
            projection.claims_for_paper(session, work.work_id) if work else []
        )

    gold_to_pred: dict[str, ClaimView] = {}
    pred_to_gold: dict[str, str] = {}
    occ_to_gold: dict[str, str] = {}
    for paper in gold.papers:
        mapping = _align(paper.claims, pred_by_doi.get(paper.doi, []))
        for gold_id, pc in mapping.items():
            gold_to_pred[gold_id] = pc
            pred_to_gold[pc.interpretation_id] = gold_id
            occ_to_gold[pc.occurrence_id] = gold_id

    report = EvaluationReport(
        domain=gold.domain,
        corpus_version=gold.corpus_version,
        extractor=f"{extractor.name}@{extractor.version}",
    )
    _score_parsing(report, gold, session, work_by_doi, gold_to_pred)
    _score_claim_extraction(report, gold, gold_to_pred, pred_by_doi)
    _score_relationships(report, gold, session, gold_to_pred, work_by_id)
    _score_target_retrieval(report, gold, session, gold_to_pred, pred_to_gold, occ_to_gold, work_by_id)
    _score_clustering(report, gold, session, pred_to_gold)
    _score_operations(report, latencies, extractor)
    return report


# ---------------------------------------------------------------------------------
# Stage scorers
# ---------------------------------------------------------------------------------


def _score_parsing(report, gold, session, work_by_doi, gold_to_pred) -> None:
    cite_correct = cite_total = 0
    for paper in gold.papers:
        if not paper.citations:
            continue
        work = work_by_doi.get(paper.doi)
        if work is None:
            continue
        predicted = _mentions_for_work(session, work.work_id)
        for citation in paper.citations:
            cite_total += 1
            if predicted.get(citation.marker) == citation.resolved_doi:
                cite_correct += 1

    sec_correct = sec_total = 0
    for claim in gold.all_claims():
        if claim.section is None:
            continue
        pc = gold_to_pred.get(claim.gold_id)
        if pc is None:
            continue
        sec_total += 1
        predicted_section = (pc.evidence.section or "").strip().lower()
        if predicted_section == claim.section.strip().lower():
            sec_correct += 1

    report.parsing = ParsingReport(
        citation_resolution_accuracy=round(cite_correct / cite_total, 4) if cite_total else 0.0,
        citations_evaluated=cite_total,
        section_recognition_accuracy=round(sec_correct / sec_total, 4) if sec_total else 0.0,
        sections_evaluated=sec_total,
    )


def _score_claim_extraction(report, gold, gold_to_pred, pred_by_doi) -> None:
    gold_results = [c for c in gold.all_claims() if c.occurrence_type is OccurrenceType.reported_result]
    pred_results = [
        pc
        for claims in pred_by_doi.values()
        for pc in claims
        if pc.occurrence_type is OccurrenceType.reported_result
    ]

    tp = 0
    matched_pred: set[str] = set()
    dir_c = dir_t = neg_c = neg_t = cert_c = cert_t = 0
    for g in gold_results:
        pc = gold_to_pred.get(g.gold_id)
        if pc is None or pc.occurrence_type is not OccurrenceType.reported_result:
            continue
        tp += 1
        matched_pred.add(pc.interpretation_id)
        quals = pc.qualifiers or {}
        if g.effect_direction is not None:
            dir_t += 1
            dir_c += int(quals.get("effect_direction") == g.effect_direction.value)
        if g.negated is not None:
            neg_t += 1
            neg_c += int(bool(quals.get("negated")) == g.negated)
        if g.certainty is not None:
            cert_t += 1
            cert_c += int(quals.get("certainty") == g.certainty.value)

    fn = len(gold_results) - tp
    fp = len([pc for pc in pred_results if pc.interpretation_id not in matched_pred])
    if gold.exhaustive_claims:
        p, r, f = metrics.prf(tp, fp, fn)
        spans = PRF(p, r, f, tp, fp, fn)
    else:
        # Precision over all predictions is meaningless when gold is a subset; recall only.
        r = round(tp / (tp + fn), 4) if (tp + fn) else 0.0
        spans = PRF(0.0, r, 0.0, tp, 0, fn)
    report.claim_extraction = ClaimExtractionReport(
        spans=spans,
        exhaustive=gold.exhaustive_claims,
        effect_direction_accuracy=round(dir_c / dir_t, 4) if dir_t else 0.0,
        negation_accuracy=round(neg_c / neg_t, 4) if neg_t else 0.0,
        certainty_accuracy=round(cert_c / cert_t, 4) if cert_t else 0.0,
        qualifiers_evaluated=tp,
    )


def _assertion_for(session, occ_id, cited_doi, work_by_id):
    rels = session.scalars(
        select(models.RelationAssertion).where(
            models.RelationAssertion.citing_occurrence_id == occ_id
        )
    )
    for r in rels:
        cited = work_by_id.get(r.cited_work_id) if r.cited_work_id else None
        if cited is not None and cited.doi == cited_doi:
            return r
    return None


def _score_relationships(report, gold, session, gold_to_pred, work_by_id) -> None:
    function_pairs: list[tuple[str, str]] = []
    stance_pairs: list[tuple[str, str]] = []
    scope_correct = scope_total = 0
    for claim in gold.all_claims():
        pc = gold_to_pred.get(claim.gold_id)
        if pc is None:
            continue
        for rel in claim.relations:
            assertion = _assertion_for(session, pc.occurrence_id, rel.cited_doi, work_by_id)
            if assertion is None:
                continue
            if assertion.function is not None:
                function_pairs.append((rel.function.value, assertion.function.value))
            if assertion.stance is not None:
                stance_pairs.append((rel.stance.value, assertion.stance.value))
            if assertion.scope is not None:
                scope_total += 1
                scope_correct += int(assertion.scope.value == rel.scope.value)

    report.function_classification = _classification(
        function_pairs, [f.value for f in RelationFunction]
    )
    report.stance_classification = _classification(
        stance_pairs, [s.value for s in RelationStance]
    )
    report.citation_scope_accuracy = round(scope_correct / scope_total, 4) if scope_total else 0.0
    report.citation_scope_evaluated = scope_total


def _classification(pairs, labels) -> ClassificationReport:
    per_class, macro = metrics.per_class_prf(pairs, labels)
    return ClassificationReport(
        macro_f1=macro,
        n=len(pairs),
        per_class={
            label: ClassMetrics(p, r, f, s) for label, (p, r, f, s) in per_class.items()
        },
        confusion=metrics.confusion_matrix(pairs, labels),
    )


def _score_target_retrieval(
    report, gold, session, gold_to_pred, pred_to_gold, occ_to_gold, work_by_id
) -> None:
    ranks: list[int | None] = []
    for claim in gold.all_claims():
        pc = gold_to_pred.get(claim.gold_id)
        if pc is None:
            continue
        for rel in claim.relations:
            if rel.resolution is not RelationResolution.claim_resolved or not rel.target_gold_id:
                continue
            assertion = _assertion_for(session, pc.occurrence_id, rel.cited_doi, work_by_id)
            gold_target = gold_to_pred.get(rel.target_gold_id)
            if assertion is None or gold_target is None:
                ranks.append(None)
                continue
            ranked: list[str] = []
            if assertion.target_interpretation_id:
                ranked.append(assertion.target_interpretation_id)
            ranked += [c["interpretation_id"] for c in (assertion.target_candidates or [])]
            seen: set[str] = set()
            ordered = [x for x in ranked if not (x in seen or seen.add(x))]
            target_id = gold_target.interpretation_id
            ranks.append(ordered.index(target_id) + 1 if target_id in ordered else None)

    # Precision at the automatic-link threshold: of everything the pipeline *chose* to
    # resolve at claim level, how often is the resolved target the adjudicated one?
    gold_targets: dict[tuple[str, str], str] = {}
    for claim in gold.all_claims():
        for rel in claim.relations:
            if rel.resolution is RelationResolution.claim_resolved and rel.target_gold_id:
                gold_targets[(claim.gold_id, rel.cited_doi)] = rel.target_gold_id

    predicted = list(
        session.scalars(
            select(models.RelationAssertion).where(
                models.RelationAssertion.resolution == RelationResolution.claim_resolved
            )
        )
    )
    correct = 0
    for assertion in predicted:
        citing_gold = occ_to_gold.get(assertion.citing_occurrence_id)
        cited = work_by_id.get(assertion.cited_work_id) if assertion.cited_work_id else None
        if citing_gold is None or cited is None:
            continue
        expected = gold_targets.get((citing_gold, cited.doi))
        predicted_target_gold = pred_to_gold.get(assertion.target_interpretation_id)
        if expected is not None and predicted_target_gold == expected:
            correct += 1

    report.target_retrieval = TargetRetrievalReport(
        recall_at_1=metrics.recall_at_k(ranks, 1),
        recall_at_3=metrics.recall_at_k(ranks, 3),
        precision_at_threshold=round(correct / len(predicted), 4) if predicted else 0.0,
        claim_resolved_gold=len(ranks),
        claim_resolved_predicted=len(predicted),
    )

    # Calibration/selective performance on the stance decision.
    confs: list[float] = []
    corrects: list[bool] = []
    for claim in gold.all_claims():
        pc = gold_to_pred.get(claim.gold_id)
        if pc is None:
            continue
        for rel in claim.relations:
            assertion = _assertion_for(session, pc.occurrence_id, rel.cited_doi, work_by_id)
            if assertion is None or not assertion.stance_distribution:
                continue
            confs.append(max(assertion.stance_distribution.values()))
            corrects.append(
                assertion.stance is not None and assertion.stance.value == rel.stance.value
            )
    accuracy = round(sum(corrects) / len(corrects), 4) if corrects else 0.0
    report.calibration = CalibrationReport(
        ece=metrics.expected_calibration_error(confs, corrects),
        accuracy=accuracy,
        n=len(confs),
        risk_coverage=metrics.risk_coverage(confs, corrects, _COVERAGES),
    )


def _score_clustering(report, gold, session, pred_to_gold) -> None:
    # Gold positive pairs among aligned claims.
    aligned = set(pred_to_gold.values())
    gold_pairs: set[frozenset[str]] = set()
    for group in gold.equivalences:
        present = [gid for gid in group if gid in aligned]
        for a, b in combinations(present, 2):
            gold_pairs.add(frozenset({a, b}))

    # Predicted positive pairs: co-membership in an active cluster, mapped to gold ids.
    memberships = list(
        session.scalars(
            select(models.ClusterMembership).where(
                models.ClusterMembership.status == MembershipStatus.active
            )
        )
    )
    by_cluster: dict[str, list[str]] = {}
    for m in memberships:
        gid = pred_to_gold.get(m.interpretation_id)
        if gid is not None:
            by_cluster.setdefault(m.cluster_id, []).append(gid)
    pred_pairs: set[frozenset[str]] = set()
    for gids in by_cluster.values():
        for a, b in combinations(sorted(set(gids)), 2):
            pred_pairs.add(frozenset({a, b}))

    p, r, f, tp, fp, fn = metrics.pair_prf(gold_pairs, pred_pairs)
    report.clustering = PRF(p, r, f, tp, fp, fn)


def _score_operations(report, latencies, extractor) -> None:
    total = sum(latencies)
    n = len(latencies)
    report.operations = OperationsReport(
        papers=n,
        total_seconds=round(total, 4),
        throughput_papers_per_s=round(n / total, 3) if total else 0.0,
        mean_latency_s=round(total / n, 4) if n else 0.0,
        max_latency_s=round(max(latencies), 4) if latencies else 0.0,
        cost_per_paper_usd=0.0,
        cost_note=f"deterministic extractor '{extractor.name}'; no LLM/API cost",
    )
