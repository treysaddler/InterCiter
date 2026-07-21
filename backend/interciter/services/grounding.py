"""ROBOKOP grounding + corroboration — derived, non-mutating enrichment.

Phase 4 of the external-data integration (docs/external-data-integration.md). Two
read-side capabilities that build on the Phase-1 :mod:`interciter.ingestion.robokop`
client, without touching the system of record:

* **Grounding** — resolve the entity qualifiers on a ``ClaimInterpretation``
  (intervention, comparator, outcome, population) to canonical CURIEs + BioLink types.
  The extractor abstains on these in the stub, so grounding is a hook that lights up
  once a real extractor fills them (or when the caller passes explicit terms).
* **Corroboration** — for a grounded subject/object CURIE pair, fetch ROBOKOP KG edges
  and shape their TRAPI ``sources`` into BioLink ``primary_knowledge_source`` /
  ``aggregator_knowledge_source`` provenance, the slots the data model already exposes
  ([docs/data-model.md](../../docs/data-model.md)).

Results are derived (like the read projection) — never written back as if they were
extracted assertions. ROBOKOP is context/corroboration, never a truth oracle that could
override a source-grounded extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..ingestion import robokop

# Qualifier keys that name a biomedical entity worth grounding.
ENTITY_QUALIFIER_KEYS = ("intervention", "comparator", "outcome", "population")


@dataclass
class TermGrounding:
    role: str
    term: str
    curie: str | None = None
    label: str | None = None
    types: list[str] = field(default_factory=list)


@dataclass
class GroundingResult:
    interpretation_id: str | None
    groundings: list[TermGrounding] = field(default_factory=list)

    def resolved(self) -> list[TermGrounding]:
        return [g for g in self.groundings if g.curie]


def candidate_terms(qualifiers: dict | None) -> list[tuple[str, str]]:
    """Return ``(role, term)`` pairs for the non-null entity qualifiers."""
    if not qualifiers:
        return []
    out: list[tuple[str, str]] = []
    for key in ENTITY_QUALIFIER_KEYS:
        value = qualifiers.get(key)
        if isinstance(value, str) and value.strip():
            out.append((key, value.strip()))
    return out


def ground_terms(
    terms: list[tuple[str, str]],
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[TermGrounding]:
    """Ground each ``(role, term)`` to a canonical node via ROBOKOP name/node norm."""
    settings = settings or get_settings()
    groundings: list[TermGrounding] = []
    for role, term in terms:
        node = robokop.ground(term, settings=settings, use_cache=use_cache)
        if not node:
            groundings.append(TermGrounding(role=role, term=term))
            continue
        identifier = (node.get("id") or {})
        groundings.append(
            TermGrounding(
                role=role,
                term=term,
                curie=identifier.get("identifier"),
                label=identifier.get("label"),
                types=node.get("type") or [],
            )
        )
    return groundings


def ground_interpretation(
    session: Session,
    interp: models.ClaimInterpretation,
    *,
    extra_terms: list[tuple[str, str]] | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> GroundingResult:
    """Ground an interpretation's entity qualifiers (plus any explicit extra terms)."""
    settings = settings or get_settings()
    terms = candidate_terms(interp.qualifiers)
    if extra_terms:
        terms.extend(extra_terms)
    return GroundingResult(
        interpretation_id=interp.interpretation_id,
        groundings=ground_terms(terms, settings=settings, use_cache=use_cache),
    )


def knowledge_sources(edge: dict) -> dict:
    """Split a TRAPI edge's ``sources`` into BioLink knowledge-source provenance.

    Maps ``resource_role`` onto the ``primary_knowledge_source`` (single) and
    ``aggregator_knowledge_source`` (list) slots the data model carries.
    """
    primary: str | None = None
    aggregators: list[str] = []
    for source in edge.get("sources") or []:
        role = source.get("resource_role")
        resource_id = source.get("resource_id")
        if role == "primary_knowledge_source":
            primary = resource_id
        elif role == "aggregator_knowledge_source" and resource_id:
            aggregators.append(resource_id)
    return {
        "primary_knowledge_source": primary,
        "aggregator_knowledge_source": aggregators,
    }


def corroborate(
    subject_curie: str,
    object_curie: str,
    *,
    predicate: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch ROBOKOP edges for a subject/object CURIE pair with provenance attached.

    Each result is ``{subject, predicate, object, primary_knowledge_source,
    aggregator_knowledge_source}`` — corroborating context, never an override.
    """
    settings = settings or get_settings()
    edges = robokop.query_edges(
        subject_curie,
        object_curie,
        predicate=predicate,
        settings=settings,
        use_cache=use_cache,
    )
    out: list[dict] = []
    for edge in edges:
        record = {
            "subject": edge.get("subject"),
            "predicate": edge.get("predicate"),
            "object": edge.get("object"),
        }
        record.update(knowledge_sources(edge))
        out.append(record)
    return out
