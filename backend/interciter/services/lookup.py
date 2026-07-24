"""On-demand Semantic Scholar lookup with read-through caching into the database.

When the UI/API asks for a paper we don't already hold, this fetches it from the
Academic Graph API and *persists* it into Postgres — core metadata, abstract, TLDR, and
(optionally) its resolved references as ``semantic_scholar`` citation edges to
metadata-stub works. Every subsequent request for that paper is then served entirely
from the local database, so browsing organically bootstraps the corpus without the full
bulk-dataset download.

Read-through and idempotent: a paper we already hold (and that is display-complete) is
returned as a cache hit with no network call; a partially-populated work has only its
null gaps filled; re-running never duplicates a work or an edge. It mirrors the
licensing posture of the rest of the project — the raw JSON is cached on disk by the
client and only identifiers, edges, and the additive display fields the schema already
carries (``abstract`` / ``tldr``) are persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..enums import AvailabilityState
from ..ids import new_id
from ..ingestion import semantic_scholar as s2
from ..ingestion import snowball

# Rich per-paper fields for an on-demand fetch: everything we can persist locally
# (including abstract + TLDR) so a cached paper is display-complete without a second
# round-trip.
_PAPER_FIELDS = (
    "externalIds",
    "title",
    "year",
    "venue",
    "authors",
    "abstract",
    "tldr",
    "publicationTypes",
    "fieldsOfStudy",
)

DEFAULT_REFS_LIMIT = 100

# Academic-Graph id prefixes that map onto a column we can query locally.
_COLUMN_FOR_PREFIX = {
    "DOI": models.PaperWork.doi,
    "PMID": models.PaperWork.pmid,
    "CorpusId": models.PaperWork.s2_corpus_id,
}


class LookupError(RuntimeError):
    """Raised when an external id cannot be resolved to a paper."""


@dataclass
class LookupResult:
    """Outcome of one read-through lookup."""

    work_id: str
    cache_hit: bool
    created: bool
    fields_filled: list[str] = field(default_factory=list)
    stubs_created: int = 0
    edges_created: int = 0


def _resolve_local_by_pid(session: Session, pid: str) -> models.PaperWork | None:
    """Find an existing work by a single normalized id, or ``None``.

    A raw 40-char ``paperId`` hash carries no prefix and maps to no local column, so it
    can only be resolved after a fetch (via the returned ``externalIds``).
    """
    prefix, _, rest = pid.partition(":")
    if not rest:
        return None
    column = _COLUMN_FOR_PREFIX.get(prefix)
    if column is None:
        return None
    return session.scalars(select(models.PaperWork).where(column == rest)).first()


def _author_names(paper: dict) -> list[str]:
    return [a["name"] for a in paper.get("authors") or [] if a.get("name")]


def _apply_metadata(work: models.PaperWork, paper: dict, result: LookupResult) -> None:
    """Additively fill null metadata gaps (incl. abstract + TLDR) from an S2 payload."""
    ext = paper.get("externalIds") or {}
    corpus_id = ext.get("CorpusId")
    if corpus_id is not None and not work.s2_corpus_id:
        work.s2_corpus_id = str(corpus_id)
        result.fields_filled.append("s2_corpus_id")
    if not work.doi and ext.get("DOI"):
        work.doi = ext["DOI"]
        result.fields_filled.append("doi")
    if not work.pmid and ext.get("PubMed"):
        work.pmid = ext["PubMed"]
        result.fields_filled.append("pmid")
    if not work.title and paper.get("title"):
        work.title = paper["title"]
        result.fields_filled.append("title")
    if not work.authors and _author_names(paper):
        work.authors = _author_names(paper)
        result.fields_filled.append("authors")
    if not work.venue and paper.get("venue"):
        work.venue = paper["venue"]
        result.fields_filled.append("venue")
    if not work.year and paper.get("year"):
        work.year = paper["year"]
        result.fields_filled.append("year")
    if not work.abstract and paper.get("abstract"):
        work.abstract = paper["abstract"]
        result.fields_filled.append("abstract")
    tldr = paper.get("tldr") or {}
    if not work.tldr and tldr.get("text"):
        work.tldr = tldr["text"]
        result.fields_filled.append("tldr")


def _resolve_local_by_externals(
    session: Session, ext: dict
) -> models.PaperWork | None:
    """Resolve an existing work by any of a payload's external identifiers."""
    for prefix, value in (
        ("CorpusId", ext.get("CorpusId")),
        ("DOI", ext.get("DOI")),
        ("PMID", ext.get("PubMed")),
    ):
        if value is None:
            continue
        work = _resolve_local_by_pid(session, f"{prefix}:{value}")
        if work is not None:
            return work
    return None


def fetch_and_cache_paper(
    session: Session,
    external_id: str,
    *,
    with_references: bool = True,
    refs_limit: int = DEFAULT_REFS_LIMIT,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> LookupResult:
    """Return a paper by external id, fetching + persisting it on a cache miss.

    ``external_id`` is a Semantic Scholar id (``DOI:…``, ``PMID:…``, ``CorpusId:…``, a
    raw ``paperId`` hash, or a bare DOI). A paper we already hold and that is
    display-complete is returned straight from the database; otherwise it is fetched
    from the Academic Graph, persisted (metadata + abstract + TLDR, and — when
    ``with_references`` — its references as citation edges to stub works), and returned.
    Commits once on success.
    """
    settings = settings or get_settings()
    try:
        pid = s2.normalize_paper_id(external_id)
    except s2.S2Error as exc:
        raise LookupError(str(exc)) from exc

    # 1) Serve from the DB when the paper is already cached and display-complete.
    local = _resolve_local_by_pid(session, pid)
    if local is not None and local.abstract:
        return LookupResult(work_id=local.work_id, cache_hit=True, created=False)

    # 2) Cache miss (or a partially-populated work): fetch from the Academic Graph.
    try:
        paper = s2.get_paper(pid, _PAPER_FIELDS, settings=settings, use_cache=use_cache)
    except s2.S2Error as exc:
        raise LookupError(str(exc)) from exc
    ext = paper.get("externalIds") or {}
    if not paper or not (ext or paper.get("title")):
        raise LookupError(f"no paper found for {external_id!r}")

    # Re-resolve now that every identifier is known (the caller may have passed a DOI
    # for a work we already hold under its corpusId, etc.).
    work = local or _resolve_local_by_externals(session, ext)
    result = LookupResult(work_id="", cache_hit=work is not None, created=work is None)
    if work is None:
        work = models.PaperWork(
            work_id=new_id("PaperWork"),
            authors=[],
            availability_state=AvailabilityState.metadata_stub,
        )
        session.add(work)
    _apply_metadata(work, paper, result)
    session.flush()
    result.work_id = work.work_id

    # 3) Optionally materialize the paper's references as stubs + citation edges.
    if with_references:
        snow = snowball.materialize_references(
            session,
            work,
            refs_per_paper=refs_limit,
            settings=settings,
            use_cache=use_cache,
        )
        result.stubs_created = snow.works_created
        result.edges_created = snow.edges_created

    session.commit()
    return result
