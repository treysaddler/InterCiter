"""Ingestion pipeline — parsed paper to immutable system-of-record records.

This is the thin vertical slice end to end:

1. hash + parse the (untrusted) document;
2. resolve or create the ``PaperWork`` / ``PaperVersion``;
3. record an ``ExtractionRun`` for full provenance;
4. persist passages and citation mentions with exact offsets;
5. run the swappable extractor to get occurrences, interpretations, and relations;
6. resolve each relation's target — **claim-level when confident, paper-level as an
   honest fallback, with ranked candidates and abstention when unsure**.

Nothing is overwritten; every record points back to the run that produced it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..enums import (
    AssertionStatus,
    AvailabilityState,
    ClusteringMethod,
    Manifestation,
    MembershipStatus,
    ParseStatus,
    RelationResolution,
    RelationStance,
)
from ..ids import new_id
from .extractor import Extractor, default_extractor
from .parser import ParsedPaper, ParsedReference, parse_jats

# Target-resolution thresholds. Calibrated against the gold set in a real system
# (docs/evaluation.md); the standing policy is prefer abstention over overclaiming.
_CLAIM_RESOLVE_THRESHOLD = 0.18
_CANDIDATE_FLOOR = 0.05
_MAX_CANDIDATES = 3
_CLUSTER_THRESHOLD = 0.34  # prefer fragmentation over pollution

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "and", "or", "to", "for", "with", "was",
    "were", "is", "are", "be", "been", "that", "this", "these", "those", "we",
    "our", "by", "as", "at", "from", "not", "no", "than", "which", "it", "its",
    "significantly", "significant", "study", "results", "showed", "found",
}
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class IngestResult:
    work_id: str
    version_id: str
    run_id: str
    availability_state: AvailabilityState
    passages: int = 0
    citation_mentions: int = 0
    occurrences: int = 0
    interpretations: int = 0
    relation_assertions: int = 0
    claim_resolved: int = 0
    paper_resolved: int = 0
    unresolved: int = 0
    warnings: list[str] = field(default_factory=list)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS}


def _overlap_score(a: str, b: str) -> float:
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _resolve_work_by_ids(
    session: Session, doi: str | None, pmid: str | None
) -> models.PaperWork | None:
    if doi:
        found = session.scalar(select(models.PaperWork).where(models.PaperWork.doi == doi))
        if found:
            return found
    if pmid:
        found = session.scalar(select(models.PaperWork).where(models.PaperWork.pmid == pmid))
        if found:
            return found
    return None


def _interpretations_for_work(
    session: Session, work_id: str
) -> list[models.ClaimInterpretation]:
    stmt = (
        select(models.ClaimInterpretation)
        .join(
            models.ClaimOccurrence,
            models.ClaimInterpretation.claim_occurrence_id
            == models.ClaimOccurrence.occurrence_id,
        )
        .join(models.Passage, models.ClaimOccurrence.passage_id == models.Passage.passage_id)
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .where(models.PaperVersion.work_id == work_id)
    )
    return list(session.scalars(stmt))


def _resolve_cited_work(
    session: Session, ref: ParsedReference
) -> models.PaperWork:
    """Resolve a bibliographic reference to an existing work or create a metadata stub."""
    existing = _resolve_work_by_ids(session, ref.doi, ref.pmid)
    if existing:
        return existing
    work = models.PaperWork(
        work_id=new_id("PaperWork"),
        title=ref.title,
        year=ref.year,
        doi=ref.doi,
        pmid=ref.pmid,
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    return work


def ingest_paper(
    session: Session,
    *,
    xml: str,
    manifestation: Manifestation = Manifestation.published,
    doi: str | None = None,
    pmid: str | None = None,
    extractor: Extractor | None = None,
    settings: Settings | None = None,
) -> IngestResult:
    settings = settings or get_settings()
    extractor = extractor or default_extractor()

    artifact_hash = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    paper = parse_jats(xml)

    work = _create_or_upgrade_work(session, paper, doi, pmid)
    version = models.PaperVersion(
        version_id=new_id("PaperVersion"),
        work_id=work.work_id,
        manifestation=manifestation,
        artifact_hash=artifact_hash,
        full_text_available=True,
        license_status="open-access",
        parser_name="interciter-jats",
        parser_version="0.1.0",
        parse_status=ParseStatus.parsed,
    )
    session.add(version)

    run = models.ExtractionRun(
        run_id=new_id("ExtractionRun"),
        model=extractor.name,
        provider=extractor.provider,
        model_version=extractor.version,
        prompt_template_version=extractor.prompt_template_version,
        parser_version=version.parser_version,
        code_revision=None,
        inference_parameters={"deterministic": True},
    )
    session.add(run)

    result = IngestResult(
        work_id=work.work_id,
        version_id=version.version_id,
        run_id=run.run_id,
        availability_state=AvailabilityState.full_text_extracted,
    )

    # Passages (exact offsets against this version).
    passage_rows: list[models.Passage] = []
    for parsed in paper.passages:
        row = models.Passage(
            passage_id=new_id("Passage"),
            paper_version_id=version.version_id,
            section=parsed.section,
            paragraph=parsed.paragraph,
            sentence=parsed.sentence,
            char_start=parsed.char_start,
            char_end=parsed.char_end,
            verbatim_text=parsed.text,
        )
        session.add(row)
        passage_rows.append(row)
    result.passages = len(passage_rows)

    # Resolve references to cited works (existing or metadata stubs).
    rid_to_work: dict[str, models.PaperWork] = {}
    for rid, ref in paper.references.items():
        rid_to_work[rid] = _resolve_cited_work(session, ref)

    # Citation mentions, keyed by (passage_index, citation offset) for later linking.
    mention_index: dict[tuple[int, int], models.CitationMention] = {}
    for p_index, parsed in enumerate(paper.passages):
        for cit in parsed.citations:
            cited_work = rid_to_work.get(cit.rid) if cit.rid else None
            mention = models.CitationMention(
                mention_id=new_id("CitationMention"),
                passage_id=passage_rows[p_index].passage_id,
                marker_span=cit.marker_text,
                cited_work_id=cited_work.work_id if cited_work else None,
                bibliographic_resolution_confidence=0.95 if cited_work else 0.0,
            )
            session.add(mention)
            mention_index[(p_index, cit.offset_in_passage)] = mention
    result.citation_mentions = len(mention_index)

    session.flush()  # assign nothing new (ids are app-side) but materialize for queries

    # Extraction: occurrences, interpretations, relations.
    for claim in extractor.extract(paper):
        passage_row = passage_rows[claim.passage_index]
        occurrence = models.ClaimOccurrence(
            occurrence_id=new_id("ClaimOccurrence"),
            passage_id=passage_row.passage_id,
            span_start=claim.span_start,
            span_end=claim.span_end,
            occurrence_type=claim.occurrence_type,
            extraction_run_id=run.run_id,
        )
        session.add(occurrence)
        interpretation = models.ClaimInterpretation(
            interpretation_id=new_id("ClaimInterpretation"),
            claim_occurrence_id=occurrence.occurrence_id,
            normalized_text=claim.normalized_text,
            qualifiers=claim.qualifiers,
            extraction_run_id=run.run_id,
            parent_interpretation_ids=[],
            created_by=run.run_id,
        )
        session.add(interpretation)
        result.occurrences += 1
        result.interpretations += 1

        for rel in claim.relations:
            mention = mention_index.get(
                (claim.passage_index, rel.citation.offset_in_passage)
            )
            cited_work = rid_to_work.get(rel.citation.rid) if rel.citation.rid else None
            assertion = _build_relation_assertion(
                session,
                run=run,
                citing_occurrence=occurrence,
                citing_text=claim.normalized_text,
                mention=mention,
                evidence_passage=passage_row,
                cited_work=cited_work,
                relation=rel,
                result=result,
            )
            session.add(assertion)
            result.relation_assertions += 1

    session.commit()
    _cluster_new_interpretations(session, run.run_id, settings)
    return result


def _create_or_upgrade_work(
    session: Session, paper: ParsedPaper, doi: str | None, pmid: str | None
) -> models.PaperWork:
    doi = paper.doi or doi
    pmid = paper.pmid or pmid
    existing = _resolve_work_by_ids(session, doi, pmid)
    if existing:
        # A previously-seen stub now has full text; upgrade its availability and fill gaps.
        existing.availability_state = AvailabilityState.full_text_extracted
        if not existing.title and paper.title:
            existing.title = paper.title
        if not existing.authors and paper.authors:
            existing.authors = paper.authors
        if not existing.venue and paper.venue:
            existing.venue = paper.venue
        if not existing.year and paper.year:
            existing.year = paper.year
        return existing
    work = models.PaperWork(
        work_id=new_id("PaperWork"),
        title=paper.title,
        authors=paper.authors,
        venue=paper.venue,
        year=paper.year,
        doi=doi,
        pmid=pmid,
        availability_state=AvailabilityState.full_text_extracted,
    )
    session.add(work)
    return work


def _build_relation_assertion(
    session: Session,
    *,
    run: models.ExtractionRun,
    citing_occurrence: models.ClaimOccurrence,
    citing_text: str,
    mention: models.CitationMention | None,
    evidence_passage: models.Passage,
    cited_work: models.PaperWork | None,
    relation,
    result: IngestResult,
) -> models.RelationAssertion:
    target_interpretation_id: str | None = None
    candidates: list[dict] = []
    resolution = RelationResolution.unresolved
    target_link_score: float | None = None

    if cited_work is not None:
        # Attempt claim-level alignment against the cited work's interpretations.
        scored = [
            (interp.interpretation_id, _overlap_score(citing_text, interp.normalized_text))
            for interp in _interpretations_for_work(session, cited_work.work_id)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored and scored[0][1] >= _CLAIM_RESOLVE_THRESHOLD:
            target_interpretation_id = scored[0][0]
            target_link_score = round(scored[0][1], 3)
            resolution = RelationResolution.claim_resolved
            result.claim_resolved += 1
        else:
            # Honest paper-level fallback: still walkable, never overstated.
            resolution = RelationResolution.paper_resolved
            candidates = [
                {"interpretation_id": iid, "score": round(score, 3)}
                for iid, score in scored[:_MAX_CANDIDATES]
                if score >= _CANDIDATE_FLOOR
            ]
            target_link_score = round(scored[0][1], 3) if scored else None
            result.paper_resolved += 1
    else:
        result.unresolved += 1

    # Abstaining on stance leaves the assertion proposed for review, not accepted.
    status = (
        AssertionStatus.proposed
        if relation.stance is RelationStance.unclear
        else AssertionStatus.proposed
    )

    return models.RelationAssertion(
        assertion_id=new_id("RelationAssertion"),
        citing_occurrence_id=citing_occurrence.occurrence_id,
        citation_mention_id=mention.mention_id if mention else None,
        evidence_passage_id=evidence_passage.passage_id,
        cited_work_id=cited_work.work_id if cited_work else None,
        target_interpretation_id=target_interpretation_id,
        target_candidates=candidates,
        function=relation.function,
        stance=relation.stance,
        scope=relation.scope,
        resolution=resolution,
        target_link_score=target_link_score,
        stance_distribution=relation.stance_distribution,
        extraction_run_id=run.run_id,
        status=status,
    )


def _interp_corpus_map(session: Session, interp_ids: list[str]) -> dict[str, str | None]:
    """Map each interpretation id to its paper's ``s2_corpus_id`` (via occurrence→work)."""
    if not interp_ids:
        return {}
    rows = session.execute(
        select(
            models.ClaimInterpretation.interpretation_id,
            models.PaperWork.s2_corpus_id,
        )
        .join(
            models.ClaimOccurrence,
            models.ClaimInterpretation.claim_occurrence_id
            == models.ClaimOccurrence.occurrence_id,
        )
        .join(models.Passage, models.ClaimOccurrence.passage_id == models.Passage.passage_id)
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .join(models.PaperWork, models.PaperVersion.work_id == models.PaperWork.work_id)
        .where(models.ClaimInterpretation.interpretation_id.in_(interp_ids))
    ).all()
    return {iid: cid for iid, cid in rows}


def _build_paper_prefilter(session: Session, settings: Settings, interps):
    """Return ``allows(a_id, b_id) -> bool``: a paper-level SPECTER2 gate for clustering.

    Narrows which *cross-paper* claim pairs are even compared: two claims from different
    papers are only considered when the papers' SPECTER2 cosine clears the threshold. The
    claim-level equivalence decision still uses token-overlap — embeddings never assert
    claim equivalence (docs/architecture.md). The gate is skipped (returns ``True``) for
    same-paper pairs or whenever either paper lacks a cached embedding, so behavior
    degrades to the token-overlap baseline rather than over-fragmenting.
    """
    if not settings.embedding_prefilter_enabled:
        return lambda a_id, b_id: True

    from ..services.enrichment import cosine, load_embedding

    corpus = _interp_corpus_map(session, [i.interpretation_id for i in interps])
    emb_cache: dict[str, list[float] | None] = {}
    threshold = settings.embedding_prefilter_threshold

    def _embedding(corpus_id: str) -> list[float] | None:
        if corpus_id not in emb_cache:
            emb_cache[corpus_id] = load_embedding(corpus_id, settings=settings)
        return emb_cache[corpus_id]

    def allows(a_id: str, b_id: str) -> bool:
        ca, cb = corpus.get(a_id), corpus.get(b_id)
        if not ca or not cb or ca == cb:
            return True  # can't gate (missing id) or same paper -> defer to token overlap
        ea, eb = _embedding(ca), _embedding(cb)
        if not ea or not eb:
            return True  # missing embedding -> fall back to the baseline
        return cosine(ea, eb) >= threshold

    return allows


def _cluster_new_interpretations(
    session: Session, run_id: str, settings: Settings
) -> None:
    """High-precision soft clustering across independent papers.

    Groups this run's interpretations with existing ones only when semantic overlap is
    high; uncertain pairs stay unclustered (abstention). Membership is a soft row, never
    a merge — reverting is just deactivating the row. A paper-level SPECTER2 prefilter
    gates which cross-paper pairs are compared at all (paper-level narrowing only).
    """
    new_interps = list(
        session.scalars(
            select(models.ClaimInterpretation).where(
                models.ClaimInterpretation.extraction_run_id == run_id
            )
        )
    )
    if not new_interps:
        return
    all_interps = list(session.scalars(select(models.ClaimInterpretation)))
    active = session.scalars(
        select(models.ClusterMembership).where(
            models.ClusterMembership.status == MembershipStatus.active
        )
    )
    cluster_of: dict[str, str] = {m.interpretation_id: m.cluster_id for m in active}
    allows = _build_paper_prefilter(session, settings, all_interps)

    for interp in new_interps:
        best_id: str | None = None
        best_score = 0.0
        for other in all_interps:
            if other.interpretation_id == interp.interpretation_id:
                continue
            if not allows(interp.interpretation_id, other.interpretation_id):
                continue  # paper-level prefilter: papers too dissimilar to compare
            score = _overlap_score(interp.normalized_text, other.normalized_text)
            if score > best_score:
                best_score, best_id = score, other.interpretation_id
        if best_id is None or best_score < _CLUSTER_THRESHOLD:
            continue  # prefer fragmentation over pollution
        cluster_id = cluster_of.get(best_id)
        if cluster_id is None:
            cluster = models.ClaimCluster(
                cluster_id=new_id("ClaimCluster"),
                clustering_method="token-overlap",
                threshold_version="stub-v1",
            )
            session.add(cluster)
            cluster_id = cluster.cluster_id
            session.add(
                models.ClusterMembership(
                    membership_id=new_id("ClusterMembership"),
                    cluster_id=cluster_id,
                    interpretation_id=best_id,
                    method=ClusteringMethod.automated,
                    membership_confidence=round(best_score, 3),
                    status=MembershipStatus.active,
                    added_by=run_id,
                )
            )
            cluster_of[best_id] = cluster_id
        session.add(
            models.ClusterMembership(
                membership_id=new_id("ClusterMembership"),
                cluster_id=cluster_id,
                interpretation_id=interp.interpretation_id,
                method=ClusteringMethod.automated,
                membership_confidence=round(best_score, 3),
                status=MembershipStatus.active,
                added_by=run_id,
            )
        )
        cluster_of[interp.interpretation_id] = cluster_id
    session.commit()
