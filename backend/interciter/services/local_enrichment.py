"""Batch backfill from the local Semantic Scholar bulk datasets.

The bulk shards downloaded by ``interciter s2-datasets pull`` (docs/
external-data-integration.md §2) are a read-only substrate: each pass here makes one
sequential streaming scan of a dataset and joins it against the works already in the
system of record. Postgres remains the system of record; nothing is ever read back
out of the shards at request time.

Same additive-only contract as :mod:`.enrichment` (the network path): fill **only
null** fields, never overwrite a value the graph already holds. Citation records
become ``semantic_scholar`` :class:`~interciter.models.CitationEdge` rows — raw
intents/contexts kept as weak supervision in ``edge_metadata``, never mapped onto
InterCiter's function/stance ontology.

``authors``, ``paper-ids`` and ``publication-venues`` are deliberately not wired in
this phase: no model surface consumes them yet (author names already live on
``PaperWork.authors``; sha→corpusid and venue detail have no table).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..datasets import store
from ..ids import new_id

#: Datasets `backfill` knows how to consume, in the order passes should run
#: (identifiers first so later passes can match on what `papers` filled in).
SUPPORTED_DATASETS = ("papers", "tldrs", "abstracts", "citations")

_COMMIT_EVERY = 500


@dataclass
class BackfillReport:
    dataset: str
    records_scanned: int = 0
    works_matched: int = 0
    fields_filled: dict[str, int] = field(default_factory=dict)
    edges_created: int = 0
    edges_existing: int = 0
    dry_run: bool = False

    def _count(self, field_name: str) -> None:
        self.fields_filled[field_name] = self.fields_filled.get(field_name, 0) + 1


def _works_by_identifier(
    session: Session,
) -> tuple[dict[str, models.PaperWork], dict[str, models.PaperWork], dict[str, models.PaperWork]]:
    """In-memory identifier maps over every work (corpus scale: thousands)."""
    by_corpus: dict[str, models.PaperWork] = {}
    by_doi: dict[str, models.PaperWork] = {}
    by_pmid: dict[str, models.PaperWork] = {}
    for work in session.scalars(select(models.PaperWork)):
        if work.s2_corpus_id:
            by_corpus[work.s2_corpus_id] = work
        if work.doi:
            by_doi[work.doi.lower()] = work
        if work.pmid:
            by_pmid[work.pmid] = work
    return by_corpus, by_doi, by_pmid


def _maybe_commit(session: Session, pending: int, *, dry_run: bool) -> int:
    if dry_run:
        return 0
    if pending >= _COMMIT_EVERY:
        session.commit()
        return 0
    return pending


def backfill_papers(
    session: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    on_shard=None,
) -> BackfillReport:
    """Fill null bibliographic fields (and ``s2_corpus_id``) from the ``papers`` dataset."""
    settings = settings or get_settings()
    report = BackfillReport(dataset="papers", dry_run=dry_run)
    by_corpus, by_doi, by_pmid = _works_by_identifier(session)

    pending = 0
    for record in store.iter_dataset("papers", settings=settings, on_shard=on_shard):
        report.records_scanned += 1
        external = record.get("externalids") or {}
        doi = external.get("DOI")
        pmid = external.get("PubMed")
        work = (
            by_corpus.get(str(record.get("corpusid")))
            or (by_doi.get(doi.lower()) if doi else None)
            or (by_pmid.get(str(pmid)) if pmid else None)
        )
        if work is None:
            continue
        report.works_matched += 1

        author_names = [a["name"] for a in record.get("authors") or [] if a.get("name")]
        filled = _fill_nulls(
            work,
            s2_corpus_id=str(record["corpusid"]) if record.get("corpusid") else None,
            doi=doi,
            pmid=str(pmid) if pmid else None,
            title=record.get("title"),
            authors=author_names or None,
            venue=record.get("venue") or None,
            year=record.get("year"),
            dry_run=dry_run,
        )
        for name in filled:
            report._count(name)
        pending = _maybe_commit(session, pending + len(filled), dry_run=dry_run)
    if not dry_run:
        session.commit()
    return report


def _fill_nulls(work: models.PaperWork, *, dry_run: bool, **values) -> list[str]:
    """Set each value whose current attribute is null/empty; return what was filled."""
    filled = []
    for name, value in values.items():
        if value is None:
            continue
        if getattr(work, name):
            continue
        if not dry_run:
            setattr(work, name, value)
        filled.append(name)
    return filled


def _backfill_text_field(
    dataset: str,
    record_key: str,
    attr: str,
    session: Session,
    *,
    settings: Settings | None,
    dry_run: bool,
    on_shard,
) -> BackfillReport:
    settings = settings or get_settings()
    report = BackfillReport(dataset=dataset, dry_run=dry_run)
    by_corpus, _, _ = _works_by_identifier(session)

    pending = 0
    for record in store.iter_dataset(dataset, settings=settings, on_shard=on_shard):
        report.records_scanned += 1
        work = by_corpus.get(str(record.get("corpusid")))
        if work is None:
            continue
        report.works_matched += 1
        text = record.get(record_key)
        if not text or getattr(work, attr):
            continue
        if not dry_run:
            setattr(work, attr, text)
        report._count(attr)
        pending = _maybe_commit(session, pending + 1, dry_run=dry_run)
    if not dry_run:
        session.commit()
    return report


def backfill_tldrs(
    session: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    on_shard=None,
) -> BackfillReport:
    """Fill ``PaperWork.tldr`` from the ``tldrs`` dataset (display metadata only)."""
    return _backfill_text_field(
        "tldrs", "text", "tldr", session, settings=settings, dry_run=dry_run, on_shard=on_shard
    )


def backfill_abstracts(
    session: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    on_shard=None,
) -> BackfillReport:
    """Fill ``PaperWork.abstract`` from the ``abstracts`` dataset (cached per license)."""
    return _backfill_text_field(
        "abstracts",
        "abstract",
        "abstract",
        session,
        settings=settings,
        dry_run=dry_run,
        on_shard=on_shard,
    )


def backfill_citations(
    session: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    on_shard=None,
) -> BackfillReport:
    """Create ``semantic_scholar`` citation edges for pairs of works we already hold.

    Purely bibliographic and additive (see :class:`~interciter.models.CitationEdge`).
    Only records where **both** endpoints resolve to existing works become edges;
    the bulk graph itself stays in the shards. Idempotent — existing
    (citing, cited, semantic_scholar) edges are skipped, so the pass can be rerun
    as more shards finish downloading.
    """
    settings = settings or get_settings()
    report = BackfillReport(dataset="citations", dry_run=dry_run)
    by_corpus, _, _ = _works_by_identifier(session)
    corpus_to_work_id = {cid: w.work_id for cid, w in by_corpus.items()}

    existing = {
        (e.citing_work_id, e.cited_work_id)
        for e in session.scalars(
            select(models.CitationEdge).where(
                models.CitationEdge.source == "semantic_scholar"
            )
        )
    }

    pending = 0
    for record in store.iter_dataset("citations", settings=settings, on_shard=on_shard):
        report.records_scanned += 1
        citing = corpus_to_work_id.get(str(record.get("citingcorpusid")))
        cited = corpus_to_work_id.get(str(record.get("citedcorpusid")))
        if citing is None or cited is None or citing == cited:
            continue
        report.works_matched += 1
        if (citing, cited) in existing:
            report.edges_existing += 1
            continue
        existing.add((citing, cited))
        report.edges_created += 1
        if dry_run:
            continue
        session.add(
            models.CitationEdge(
                edge_id=new_id("CitationEdge"),
                citing_work_id=citing,
                cited_work_id=cited,
                source="semantic_scholar",
                is_influential=record.get("isinfluential"),
                edge_metadata={
                    "provider": "s2_bulk",
                    "s2_intents": record.get("intents") or [],
                    "contexts": record.get("contexts") or [],
                },
            )
        )
        pending = _maybe_commit(session, pending + 1, dry_run=dry_run)
    if not dry_run:
        session.commit()
    return report


_PASSES = {
    "papers": backfill_papers,
    "tldrs": backfill_tldrs,
    "abstracts": backfill_abstracts,
    "citations": backfill_citations,
}


def backfill(
    session: Session,
    datasets: list[str],
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    on_shard=None,
) -> list[BackfillReport]:
    """Run the requested passes in canonical order; returns one report per dataset."""
    unknown = set(datasets) - set(SUPPORTED_DATASETS)
    if unknown:
        raise ValueError(
            f"unsupported dataset(s) {sorted(unknown)}; supported: {list(SUPPORTED_DATASETS)}"
        )
    reports = []
    for name in SUPPORTED_DATASETS:
        if name not in datasets:
            continue
        pass_fn = _PASSES[name]
        reports.append(
            pass_fn(session, settings=settings, dry_run=dry_run, on_shard=on_shard)
        )
    return reports
