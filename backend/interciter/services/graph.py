"""Network-graph projections — papers, authors, citations (and, later, claims).

A derived, read-side view (like :mod:`interciter.services.projection`): it turns the
immutable system of record into node/edge sets a client can explore as a network graph.
Nothing here mutates a scientific assertion.

Two citation sources are unioned into ``cites`` edges:

* **extracted** — a :class:`~interciter.models.CitationMention` anchored in a passage
  (we hold full text and resolved the marker to a cited work); and
* **bibliographic** — a :class:`~interciter.models.CitationEdge` (work → work), which can
  exist for metadata-only stubs and is how the network grows past our full-text corpus
  when a user expands a node from Semantic Scholar.

Author nodes are derived from ``PaperWork.authors`` and connected to their papers with
``authored`` edges. The node/edge envelope is intentionally generic (an open ``type``
discriminator) so the same shape carries a ROBOKOP claim graph later.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..enums import AvailabilityState, RelationResolution
from ..ids import new_id
from ..schemas import ClaimExpansion, GraphEdge, GraphExpansion, GraphNode, GraphView
from . import enrichment, grounding

# Bounds so a single request can never materialize an unbounded graph.
DEFAULT_PAPER_LIMIT = 100
MAX_PAPER_LIMIT = 500
MAX_NEIGHBORHOOD_NODES = 250
DEFAULT_EXPAND_LIMIT = 50
MAX_EXPAND_LIMIT = 200


# ---------------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------------


def _author_id(name: str) -> str:
    """Stable, opaque id for an author derived from the normalized display name.

    Authors are strings on ``PaperWork`` (no author table yet), so equality is by
    normalized name. Good enough to co-locate a person's papers; not identity resolution.
    """
    digest = hashlib.sha1(name.strip().casefold().encode("utf-8")).hexdigest()
    return f"author_{digest[:16]}"


def _paper_node(work: models.PaperWork) -> GraphNode:
    return GraphNode(
        id=work.work_id,
        type="paper",
        label=work.title or work.work_id,
        data={
            "year": work.year,
            "venue": work.venue,
            "authors": work.authors or [],
            "doi": work.doi,
            "pmid": work.pmid,
            "s2_corpus_id": work.s2_corpus_id,
            "availability_state": work.availability_state.value
            if work.availability_state
            else None,
        },
    )


def _author_node(name: str) -> GraphNode:
    return GraphNode(id=_author_id(name), type="author", label=name, data={"name": name})


# ---------------------------------------------------------------------------------
# Citation edges (extracted mentions ∪ bibliographic edges)
# ---------------------------------------------------------------------------------


@dataclass
class _CitePair:
    citing: str
    cited: str
    sources: set[str] = field(default_factory=set)
    is_influential: bool | None = None


def _citation_pairs(session: Session) -> dict[tuple[str, str], _CitePair]:
    """All directed (citing → cited) work pairs, unioned across both edge sources."""
    pairs: dict[tuple[str, str], _CitePair] = {}

    def _add(citing: str, cited: str, source: str, influential: bool | None = None) -> None:
        if not citing or not cited or citing == cited:
            return
        key = (citing, cited)
        pair = pairs.get(key)
        if pair is None:
            pair = _CitePair(citing=citing, cited=cited)
            pairs[key] = pair
        pair.sources.add(source)
        if influential is not None:
            pair.is_influential = bool(pair.is_influential) or influential

    # Extracted, passage-grounded mentions: citing work resolved via passage → version.
    mention_stmt = (
        select(models.PaperVersion.work_id, models.CitationMention.cited_work_id)
        .join(
            models.Passage,
            models.CitationMention.passage_id == models.Passage.passage_id,
        )
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .where(models.CitationMention.cited_work_id.is_not(None))
    )
    for citing, cited in session.execute(mention_stmt):
        _add(citing, cited, "extracted")

    # Bibliographic edges (e.g. Semantic Scholar references).
    for edge in session.scalars(select(models.CitationEdge)):
        _add(edge.citing_work_id, edge.cited_work_id, edge.source, edge.is_influential)

    return pairs


def _cite_edge(pair: _CitePair) -> GraphEdge:
    return GraphEdge(
        id=f"cites:{pair.citing}->{pair.cited}",
        source=pair.citing,
        target=pair.cited,
        type="cites",
        data={
            "sources": sorted(pair.sources),
            "is_influential": pair.is_influential,
        },
    )


def _attach_citation_counts(
    nodes: dict[str, GraphNode], pairs: dict[tuple[str, str], _CitePair]
) -> None:
    """Annotate each paper node with global citation-degree measures, in place.

    Two derived measures a client can map/size by (Litmaps-style ``year × citations``):

    * ``cited_by_count`` — in-degree, how many distinct works cite this one; and
    * ``references_count`` — out-degree, how many distinct works this one cites.

    Degrees are computed over the *whole* citation network (every edge source), not just
    the current view, so the measure is stable no matter how the graph is windowed.
    """
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for citing, cited in pairs:
        out_deg[citing] = out_deg.get(citing, 0) + 1
        in_deg[cited] = in_deg.get(cited, 0) + 1
    for node_id, node in nodes.items():
        if node.type == "paper":
            node.data["cited_by_count"] = in_deg.get(node_id, 0)
            node.data["references_count"] = out_deg.get(node_id, 0)


def _attach_authors(
    nodes: dict[str, GraphNode], edges: list[GraphEdge], works: list[models.PaperWork]
) -> None:
    """Add author nodes and ``authored`` edges for the given papers, in place."""
    for work in works:
        for name in work.authors or []:
            author = _author_node(name)
            nodes.setdefault(author.id, author)
            edge_id = f"authored:{author.id}->{work.work_id}"
            edges.append(
                GraphEdge(
                    id=edge_id,
                    source=author.id,
                    target=work.work_id,
                    type="authored",
                )
            )


# ---------------------------------------------------------------------------------
# Public graph builders
# ---------------------------------------------------------------------------------


def build_paper_graph(
    session: Session,
    *,
    limit: int = DEFAULT_PAPER_LIMIT,
    include_authors: bool = False,
) -> GraphView:
    """A bounded overview of the whole citation network.

    Seeds with up to ``limit`` works (ordered by title then id) and includes every
    ``cites`` edge whose *both* endpoints fall in that seed set, so the view is always
    connected and bounded. ``truncated`` reports whether the cap hid additional works.
    """
    limit = max(1, min(limit, MAX_PAPER_LIMIT))
    total = session.scalar(select(func.count()).select_from(models.PaperWork)) or 0
    works = list(
        session.scalars(
            select(models.PaperWork)
            .order_by(models.PaperWork.title, models.PaperWork.work_id)
            .limit(limit)
        )
    )
    seed_ids = {w.work_id for w in works}
    pairs = _citation_pairs(session)
    nodes: dict[str, GraphNode] = {w.work_id: _paper_node(w) for w in works}
    edges: list[GraphEdge] = [
        _cite_edge(pair)
        for pair in pairs.values()
        if pair.citing in seed_ids and pair.cited in seed_ids
    ]
    _attach_citation_counts(nodes, pairs)
    if include_authors:
        _attach_authors(nodes, edges, works)
    return GraphView(
        nodes=list(nodes.values()), edges=edges, truncated=total > len(works)
    )


def paper_neighborhood(
    session: Session,
    work_id: str,
    *,
    depth: int = 1,
    include_authors: bool = False,
) -> GraphView:
    """The citation neighborhood around a work, BFS to ``depth`` hops (both directions).

    Raises :class:`KeyError` if the center work does not exist.
    """
    if session.get(models.PaperWork, work_id) is None:
        raise KeyError(work_id)
    depth = max(1, min(depth, 3))

    pairs = _citation_pairs(session)
    adjacency: dict[str, set[str]] = {}
    for citing, cited in pairs:
        adjacency.setdefault(citing, set()).add(cited)
        adjacency.setdefault(cited, set()).add(citing)

    visited = {work_id}
    frontier = {work_id}
    truncated = False
    for _ in range(depth):
        nxt: set[str] = set()
        for node in frontier:
            for neighbor in adjacency.get(node, ()):
                if neighbor not in visited:
                    if len(visited) >= MAX_NEIGHBORHOOD_NODES:
                        truncated = True
                        break
                    nxt.add(neighbor)
                    visited.add(neighbor)
            if truncated:
                break
        frontier = nxt
        if truncated or not frontier:
            break

    works = list(
        session.scalars(
            select(models.PaperWork).where(models.PaperWork.work_id.in_(visited))
        )
    )
    nodes: dict[str, GraphNode] = {w.work_id: _paper_node(w) for w in works}
    edges = [
        _cite_edge(pair)
        for pair in pairs.values()
        if pair.citing in visited and pair.cited in visited
    ]
    _attach_citation_counts(nodes, pairs)
    if include_authors:
        _attach_authors(nodes, edges, works)
    return GraphView(
        nodes=list(nodes.values()),
        edges=edges,
        center_id=work_id,
        truncated=truncated,
    )


def claim_graph(session: Session, *, limit: int = DEFAULT_PAPER_LIMIT) -> GraphView:
    """A claim-relationship network from resolved cross-claim assertions.

    Nodes are claim interpretations; edges are ``RelationAssertion``s that resolved to a
    target interpretation (``claim_resolved``), carrying the function/stance tags. This
    is the in-corpus claim network today and the seam ROBOKOP claim expansion will extend
    (see :func:`expand_claim_robokop`).
    """
    limit = max(1, min(limit, MAX_PAPER_LIMIT))
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    stmt = select(models.RelationAssertion).where(
        models.RelationAssertion.resolution == RelationResolution.claim_resolved,
        models.RelationAssertion.target_interpretation_id.is_not(None),
    )
    for assertion in session.scalars(stmt):
        source_interp = _head_interpretation(session, assertion.citing_occurrence_id)
        target_interp = session.get(
            models.ClaimInterpretation, assertion.target_interpretation_id
        )
        if source_interp is None or target_interp is None:
            continue
        for interp in (source_interp, target_interp):
            node = _claim_node(interp)
            nodes.setdefault(node.id, node)
        edges.append(
            GraphEdge(
                id=assertion.assertion_id,
                source=source_interp.interpretation_id,
                target=target_interp.interpretation_id,
                type="relates",
                label=assertion.function.value if assertion.function else None,
                data={
                    "function": assertion.function.value if assertion.function else None,
                    "stance": assertion.stance.value if assertion.stance else None,
                    "resolution": assertion.resolution.value,
                    "status": assertion.status.value,
                },
            )
        )
        if len(nodes) >= limit:
            return GraphView(nodes=list(nodes.values()), edges=edges, truncated=True)
    return GraphView(nodes=list(nodes.values()), edges=edges)


def _claim_node(interp: models.ClaimInterpretation) -> GraphNode:
    return GraphNode(
        id=interp.interpretation_id,
        type="claim",
        label=interp.normalized_text,
        data={"qualifiers": interp.qualifiers or {}},
    )


def _head_interpretation(
    session: Session, occurrence_id: str
) -> models.ClaimInterpretation | None:
    """The current head interpretation of an occurrence (none lists it as a parent)."""
    interps = list(
        session.scalars(
            select(models.ClaimInterpretation).where(
                models.ClaimInterpretation.claim_occurrence_id == occurrence_id
            )
        )
    )
    if not interps:
        return None
    parents: set[str] = set()
    for interp in interps:
        parents.update(interp.parent_interpretation_ids or [])
    for interp in interps:
        if interp.interpretation_id not in parents:
            return interp
    return interps[-1]


# ---------------------------------------------------------------------------------
# On-demand expansion — Semantic Scholar references
# ---------------------------------------------------------------------------------


def _resolve_work(session: Session, link: dict) -> models.PaperWork | None:
    """Find an existing work matching a reference link by DOI, PMID, or corpusId."""
    conditions = []
    if link.get("cited_doi"):
        conditions.append(models.PaperWork.doi == link["cited_doi"])
    if link.get("cited_pmid"):
        conditions.append(models.PaperWork.pmid == link["cited_pmid"])
    if link.get("cited_corpus_id"):
        conditions.append(models.PaperWork.s2_corpus_id == link["cited_corpus_id"])
    if not conditions:
        return None
    return session.scalars(
        select(models.PaperWork).where(or_(*conditions))
    ).first()


def expand_from_semantic_scholar(
    session: Session,
    work: models.PaperWork,
    *,
    limit: int = DEFAULT_EXPAND_LIMIT,
    include_authors: bool = False,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> GraphExpansion:
    """Pull a work's references from Semantic Scholar and persist them as the graph.

    Non-destructive: cited works missing from the store are created as metadata-only
    stubs, and each reference becomes a ``semantic_scholar`` :class:`CitationEdge`
    (idempotent — re-expanding never duplicates an edge). Returns counts plus the
    refreshed neighborhood. Commits on success.
    """
    settings = settings or get_settings()
    limit = max(1, min(limit, MAX_EXPAND_LIMIT))

    s2_id = enrichment.s2_id_for_work(work)
    if s2_id is None:
        return GraphExpansion(
            work_id=work.work_id,
            skipped_reason="no DOI/PMID/corpusId to resolve on Semantic Scholar",
            graph=paper_neighborhood(
                session, work.work_id, include_authors=include_authors
            ),
        )

    links = enrichment.reference_links(
        s2_id, max_records=limit, settings=settings, use_cache=use_cache
    )

    works_created = 0
    edges_created = 0
    for link in links:
        cited = _resolve_work(session, link)
        if cited is None:
            cited = models.PaperWork(
                work_id=new_id("PaperWork"),
                title=link.get("cited_title"),
                authors=[],
                doi=link.get("cited_doi"),
                pmid=link.get("cited_pmid"),
                s2_corpus_id=link.get("cited_corpus_id"),
                availability_state=AvailabilityState.metadata_stub,
            )
            session.add(cited)
            session.flush()
            works_created += 1
        if cited.work_id == work.work_id:
            continue
        exists = session.scalars(
            select(models.CitationEdge).where(
                models.CitationEdge.citing_work_id == work.work_id,
                models.CitationEdge.cited_work_id == cited.work_id,
                models.CitationEdge.source == "semantic_scholar",
            )
        ).first()
        if exists is not None:
            continue
        session.add(
            models.CitationEdge(
                edge_id=new_id("CitationEdge"),
                citing_work_id=work.work_id,
                cited_work_id=cited.work_id,
                source="semantic_scholar",
                is_influential=link.get("is_influential"),
                edge_metadata={
                    "s2_intents": link.get("intents", []),
                    "contexts": link.get("contexts", []),
                },
            )
        )
        edges_created += 1

    session.commit()
    return GraphExpansion(
        work_id=work.work_id,
        references_fetched=len(links),
        works_created=works_created,
        edges_created=edges_created,
        graph=paper_neighborhood(session, work.work_id, include_authors=include_authors),
    )


# ---------------------------------------------------------------------------------
# On-demand expansion — ROBOKOP claim neighborhood
# ---------------------------------------------------------------------------------


def _short_predicate(predicate: str | None) -> str | None:
    """Human-readable edge label from a BioLink predicate CURIE (drop the prefix)."""
    if not predicate:
        return None
    return predicate.split(":", 1)[-1].replace("_", " ")


def expand_claim_robokop(
    session: Session,
    interp: models.ClaimInterpretation,
    *,
    extra_terms: list[tuple[str, str]] | None = None,
    persist: bool = True,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> ClaimExpansion:
    """Explore a claim in the ROBOKOP knowledge graph.

    Grounds the claim's entity qualifiers (plus any explicit ``extra_terms``) to
    canonical CURIEs, then corroborates each pair of grounded entities against the
    ROBOKOP KG. The returned graph places the claim at the center, connects it to each
    grounded entity, and draws the background-knowledge edges between those entities —
    with knowledge-source provenance on every KG edge. ROBOKOP is *context*, never a
    truth oracle that overrides the source-grounded extraction.

    Grounded entities are persisted as additive ``EntityGrounding`` side rows (idempotent
    when ``persist``); KG edges are derived context and are not stored. Commits when it
    persists.
    """
    settings = settings or get_settings()

    result = grounding.ground_interpretation(
        session, interp, extra_terms=extra_terms, settings=settings, use_cache=use_cache
    )
    if persist:
        grounding.persist_grounding(session, result)
        session.commit()

    nodes: dict[str, GraphNode] = {
        interp.interpretation_id: _claim_node(interp),
    }
    edges: list[GraphEdge] = []

    resolved = result.resolved()
    for term in resolved:
        curie = term.curie
        if curie is None:
            continue
        nodes.setdefault(
            curie,
            GraphNode(
                id=curie,
                type="entity",
                label=term.label or term.term,
                data={"role": term.role, "term": term.term, "types": term.types},
            ),
        )
        edges.append(
            GraphEdge(
                id=f"grounds:{interp.interpretation_id}->{curie}",
                source=interp.interpretation_id,
                target=curie,
                type="grounds",
                label=term.role,
            )
        )

    seen_edges: set[tuple[str, str, str]] = set()
    corroborating = 0
    for left, right in itertools.combinations(resolved, 2):
        if left.curie is None or right.curie is None:
            continue
        for kg in grounding.corroborate(
            left.curie, right.curie, settings=settings, use_cache=use_cache
        ):
            subject = kg.get("subject")
            obj = kg.get("object")
            predicate = kg.get("predicate") or "biolink:related_to"
            if not subject or not obj:
                continue
            key = (subject, predicate, obj)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            for endpoint in (subject, obj):
                nodes.setdefault(
                    endpoint,
                    GraphNode(id=endpoint, type="entity", label=endpoint, data={}),
                )
            edges.append(
                GraphEdge(
                    id=f"kg:{subject}|{predicate}|{obj}",
                    source=subject,
                    target=obj,
                    type="kg",
                    label=_short_predicate(predicate),
                    data={
                        "predicate": predicate,
                        "primary_knowledge_source": kg.get("primary_knowledge_source"),
                        "aggregator_knowledge_source": kg.get(
                            "aggregator_knowledge_source", []
                        ),
                    },
                )
            )
            corroborating += 1

    return ClaimExpansion(
        interpretation_id=interp.interpretation_id,
        grounded_terms=len(result.groundings),
        resolved_terms=len(resolved),
        corroborating_edges=corroborating,
        graph=GraphView(
            nodes=list(nodes.values()),
            edges=edges,
            center_id=interp.interpretation_id,
        ),
    )
