"""Build a large seed corpus by snowballing Semantic Scholar references.

Starting from a handful of seed papers (arbitrary DOIs), this walks the citation graph
*backwards* along resolved references, breadth-first, materializing each paper as a
metadata-only :class:`~interciter.models.PaperWork` and every citation as a
``semantic_scholar`` :class:`~interciter.models.CitationEdge` — until the corpus reaches
a target size. It exists to exercise the Papers list, the network-graph explorer, and
seed-based discovery at realistic scale.

It deliberately does **not** produce claims, relations, or clusters: those require the
full-text extraction pipeline, and Semantic Scholar provides metadata + abstracts, not
JATS. So the corpus is a citation *graph* of stubs, not a set of extracted papers.

Licensing posture (same as the rest of the project): only identifiers and citation edges
are persisted; the raw Semantic Scholar JSON is cached locally (gitignored) by the
client, and abstracts / full text are never fetched or stored. The caller writes a small
manifest of resolved corpus ids for reproducibility.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..enums import AvailabilityState
from ..ids import new_id
from . import semantic_scholar as s2

# Metadata requested for a paper we expand (seeds + BFS hubs). Kept small and explicit so
# cached payloads are predictable and we never pull abstracts or full text.
_PAPER_FIELDS = ("externalIds", "title", "year", "venue", "authors")

# Reference fields — enough to materialize each cited paper as a stub *and* connect its
# authors, without a second round-trip per reference.
_REFERENCE_FIELDS = (
    "isInfluential",
    "intents",
    "citedPaper.externalIds",
    "citedPaper.title",
    "citedPaper.year",
    "citedPaper.authors",
)

# Guardrails so one hyper-cited review or a runaway walk cannot dominate the corpus.
DEFAULT_TARGET_SIZE = 1000
MAX_TARGET_SIZE = 20000
DEFAULT_REFS_PER_PAPER = 50
_COMMIT_EVERY = 25  # flush progress to the DB periodically for a resumable-ish pull


@dataclass
class SnowballResult:
    """Summary of one corpus build."""

    target_size: int
    seeds_resolved: int = 0
    seeds_missing: list[str] = field(default_factory=list)
    works_total: int = 0  # distinct papers in the corpus after this run
    works_created: int = 0
    edges_created: int = 0
    expansions: int = 0  # papers whose references we fetched (one API call each)
    papers_fetched: int = 0  # get_paper calls (seeds + hubs enriched)
    corpus: list[dict] = field(default_factory=list)  # manifest rows (ids only)


def _author_names(authors: list[dict] | None) -> list[str]:
    return [a["name"] for a in (authors or []) if a.get("name")]


def _external_ids(paper: dict) -> dict:
    return paper.get("externalIds") or {}


def _link_from_reference(ref: dict) -> dict | None:
    """Normalize an S2 reference into a resolution/stub link, or ``None`` if unusable."""
    cited = ref.get("citedPaper") or {}
    ext = cited.get("externalIds") or {}
    corpus = ext.get("CorpusId")
    doi = ext.get("DOI")
    pmid = ext.get("PubMed")
    if corpus is None and not doi and not pmid:
        return None  # unidentifiable — cannot dedupe or expand it, so skip
    return {
        "cited_corpus_id": str(corpus) if corpus is not None else None,
        "cited_doi": doi,
        "cited_pmid": pmid,
        "cited_title": cited.get("title"),
        "cited_year": cited.get("year"),
        "cited_authors": _author_names(cited.get("authors")),
        "is_influential": bool(ref.get("isInfluential")),
        "intents": ref.get("intents") or [],
    }


class _Index:
    """In-memory identifier → work_id map so resolution stays O(1) after first touch."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._by_key: dict[tuple[str, str], str] = {}

    @staticmethod
    def _keys(*, corpus: str | None, doi: str | None, pmid: str | None):
        if corpus:
            yield ("corpus", corpus)
        if doi:
            yield ("doi", doi)
        if pmid:
            yield ("pmid", pmid)

    def add(self, work: models.PaperWork) -> None:
        for key in self._keys(corpus=work.s2_corpus_id, doi=work.doi, pmid=work.pmid):
            self._by_key[key] = work.work_id

    def resolve(
        self, *, corpus: str | None, doi: str | None, pmid: str | None
    ) -> models.PaperWork | None:
        keys = list(self._keys(corpus=corpus, doi=doi, pmid=pmid))
        for key in keys:
            hit = self._by_key.get(key)
            if hit is not None:
                return self._session.get(models.PaperWork, hit)
        # Cold miss: a pre-existing work (e.g. from the bundled sample) may match in the DB.
        conditions = []
        if corpus:
            conditions.append(models.PaperWork.s2_corpus_id == corpus)
        if doi:
            conditions.append(models.PaperWork.doi == doi)
        if pmid:
            conditions.append(models.PaperWork.pmid == pmid)
        if not conditions:
            return None
        from sqlalchemy import or_

        work = self._session.scalars(
            select(models.PaperWork).where(or_(*conditions))
        ).first()
        if work is not None:
            self.add(work)
        return work


def _resolve_or_create_stub(
    session: Session, index: _Index, link: dict, result: SnowballResult
) -> models.PaperWork:
    work = index.resolve(
        corpus=link.get("cited_corpus_id"),
        doi=link.get("cited_doi"),
        pmid=link.get("cited_pmid"),
    )
    if work is not None:
        return work
    work = models.PaperWork(
        work_id=new_id("PaperWork"),
        title=link.get("cited_title"),
        authors=link.get("cited_authors") or [],
        year=link.get("cited_year"),
        doi=link.get("cited_doi"),
        pmid=link.get("cited_pmid"),
        s2_corpus_id=link.get("cited_corpus_id"),
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    session.flush()
    index.add(work)
    result.works_created += 1
    return work


def _upsert_seed(
    session: Session, index: _Index, paper: dict, result: SnowballResult
) -> models.PaperWork:
    ext = _external_ids(paper)
    corpus = ext.get("CorpusId")
    link = {
        "cited_corpus_id": str(corpus) if corpus is not None else None,
        "cited_doi": ext.get("DOI"),
        "cited_pmid": ext.get("PubMed"),
        "cited_title": paper.get("title"),
        "cited_year": paper.get("year"),
        "cited_authors": _author_names(paper.get("authors")),
    }
    work = _resolve_or_create_stub(session, index, link, result)
    # Fill any gaps for an already-known work (additive only).
    if not work.venue and paper.get("venue"):
        work.venue = paper["venue"]
    if not work.authors and link["cited_authors"]:
        work.authors = link["cited_authors"]
    return work


def _s2_id(work: models.PaperWork) -> str | None:
    if work.s2_corpus_id:
        return f"CorpusId:{work.s2_corpus_id}"
    if work.doi:
        return f"DOI:{work.doi}"
    if work.pmid:
        return f"PMID:{work.pmid}"
    return None


def _edge_exists(session: Session, citing_id: str, cited_id: str) -> bool:
    return (
        session.scalars(
            select(models.CitationEdge).where(
                models.CitationEdge.citing_work_id == citing_id,
                models.CitationEdge.cited_work_id == cited_id,
                models.CitationEdge.source == "semantic_scholar",
            )
        ).first()
        is not None
    )


def materialize_references(
    session: Session,
    work: models.PaperWork,
    *,
    index: "_Index | None" = None,
    result: SnowballResult | None = None,
    edges_seen: set[tuple[str, str]] | None = None,
    refs_per_paper: int = DEFAULT_REFS_PER_PAPER,
    settings: Settings | None = None,
    use_cache: bool = True,
    on_stub=None,
    stop=None,
) -> SnowballResult:
    """Fetch one work's resolved references and materialize them locally.

    Each usable reference becomes a metadata-stub :class:`~interciter.models.PaperWork`
    (deduped by corpusId / DOI / PMID) and a ``semantic_scholar``
    :class:`~interciter.models.CitationEdge`. Shared by the snowball corpus builder
    (breadth-first, passing its own ``index`` / ``result`` / ``edges_seen`` so state
    accumulates across the walk) and the on-demand lookup cache (single hop, letting
    this create throwaway state). Idempotent against the unique edge constraint and
    additive on stubs — never commits; the caller owns the transaction.

    ``on_stub(cited)`` fires for every resolved reference (the BFS enqueues its frontier
    here); ``stop()`` short-circuits the loop once the caller has hit a size budget.
    """
    settings = settings or get_settings()
    if index is None:
        index = _Index(session)
        index.add(work)
    if result is None:
        result = SnowballResult(target_size=0)
    if edges_seen is None:
        edges_seen = set()

    s2_id = _s2_id(work)
    if s2_id is None:
        return result
    try:
        refs = s2.get_references(
            s2_id,
            _REFERENCE_FIELDS,
            max_records=refs_per_paper,
            settings=settings,
            use_cache=use_cache,
        )
    except s2.S2Error:
        return result
    result.expansions += 1

    for ref in refs:
        link = _link_from_reference(ref)
        if link is None:
            continue
        cited = _resolve_or_create_stub(session, index, link, result)
        if cited.work_id == work.work_id:
            continue
        pair = (work.work_id, cited.work_id)
        if pair not in edges_seen and not _edge_exists(session, work.work_id, cited.work_id):
            session.add(
                models.CitationEdge(
                    edge_id=new_id("CitationEdge"),
                    citing_work_id=work.work_id,
                    cited_work_id=cited.work_id,
                    source="semantic_scholar",
                    is_influential=link.get("is_influential"),
                    edge_metadata={"s2_intents": link.get("intents", [])},
                )
            )
            edges_seen.add(pair)
            result.edges_created += 1
        if on_stub is not None:
            on_stub(cited)
        if stop is not None and stop():
            break
    return result


def build_corpus(
    session: Session,
    seed_ids: list[str],
    *,
    target_size: int = DEFAULT_TARGET_SIZE,
    refs_per_paper: int = DEFAULT_REFS_PER_PAPER,
    settings: Settings | None = None,
    use_cache: bool = True,
    progress=None,
) -> SnowballResult:
    """Snowball a citation graph of ~``target_size`` papers from ``seed_ids``.

    ``seed_ids`` are Semantic Scholar ids (e.g. ``DOI:10.1038/nature14539``, ``PMID:…``,
    ``CorpusId:…`` — a bare DOI is accepted and prefixed). References are walked
    breadth-first, creating a ``PaperWork`` stub and a ``semantic_scholar``
    ``CitationEdge`` per resolved citation, until the corpus reaches ``target_size``.
    Idempotent: re-running never duplicates a work or an edge. Commits as it goes.
    """
    settings = settings or get_settings()
    target_size = max(1, min(target_size, MAX_TARGET_SIZE))
    result = SnowballResult(target_size=target_size)
    index = _Index(session)

    # Distinct corpus members seen this run (work_ids), and the BFS frontier to expand.
    corpus: dict[str, models.PaperWork] = {}
    frontier: deque[str] = deque()
    expanded: set[str] = set()
    # Edges added this run but not yet committed — the DB check alone can't see them, and
    # a paper can list the same reference twice, so dedupe against the unique constraint.
    edges_seen: set[tuple[str, str]] = set()

    def _note(work: models.PaperWork, *, expandable: bool) -> None:
        if work.work_id not in corpus:
            corpus[work.work_id] = work
            if expandable and _s2_id(work) is not None:
                frontier.append(work.work_id)

    # 1) Resolve seeds (a real fetch so seeds are rich and expandable).
    for raw in seed_ids:
        try:
            paper = s2.get_paper(
                raw, _PAPER_FIELDS, settings=settings, use_cache=use_cache
            )
        except s2.S2Error:
            result.seeds_missing.append(raw)
            continue
        if not paper or not (_external_ids(paper) or paper.get("title")):
            result.seeds_missing.append(raw)
            continue
        result.papers_fetched += 1
        work = _upsert_seed(session, index, paper, result)
        result.seeds_resolved += 1
        _note(work, expandable=True)
    session.commit()

    if progress:
        progress(f"resolved {result.seeds_resolved}/{len(seed_ids)} seeds")

    # 2) Breadth-first expansion until the corpus reaches the target size.
    since_commit = 0
    while frontier and len(corpus) < target_size:
        work_id = frontier.popleft()
        if work_id in expanded:
            continue
        expanded.add(work_id)
        work = session.get(models.PaperWork, work_id)
        if work is None or _s2_id(work) is None:
            continue
        materialize_references(
            session,
            work,
            index=index,
            result=result,
            edges_seen=edges_seen,
            refs_per_paper=refs_per_paper,
            settings=settings,
            use_cache=use_cache,
            on_stub=lambda cited: _note(cited, expandable=True),
            stop=lambda: len(corpus) >= target_size,
        )

        since_commit += 1
        if since_commit >= _COMMIT_EVERY:
            session.commit()
            since_commit = 0
            if progress:
                progress(
                    f"{len(corpus)}/{target_size} papers, "
                    f"{result.edges_created} edges, {result.expansions} expansions"
                )

    session.commit()

    result.works_total = len(corpus)
    result.corpus = [
        {
            "work_id": w.work_id,
            "corpus_id": w.s2_corpus_id,
            "doi": w.doi,
            "pmid": w.pmid,
            "title": w.title,
            "year": w.year,
        }
        for w in corpus.values()
    ]
    if progress:
        progress(
            f"done: {result.works_total} papers, {result.works_created} new, "
            f"{result.edges_created} edges"
        )
    return result
