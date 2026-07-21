"""Gold-corpus schema and loader.

The gold corpus is a manually adjudicated set of labels over the MVP domain slice. In
production, ``ReviewDecision`` records double as ongoing annotation (docs/evaluation.md);
this bundled corpus is a small, self-contained stand-in that exercises the hard cases the
design calls for: multiple citations per paragraph, a contrasting (contradicting)
citation, a method citation, negation/hedging vocabulary, and a cited paper containing
several similar claims.
"""

from __future__ import annotations

import json
from importlib import resources

from pydantic import BaseModel, Field

from ..enums import (
    Certainty,
    EffectDirection,
    OccurrenceType,
    RelationFunction,
    RelationResolution,
    RelationScope,
    RelationStance,
)


class GoldRelation(BaseModel):
    cited_doi: str
    function: RelationFunction
    stance: RelationStance
    scope: RelationScope
    resolution: RelationResolution
    target_gold_id: str | None = Field(
        default=None,
        description="For claim_resolved relations, the gold id of the target claim.",
    )


class GoldClaim(BaseModel):
    gold_id: str
    text: str
    occurrence_type: OccurrenceType
    section: str | None = None
    effect_direction: EffectDirection | None = None
    negated: bool | None = None
    certainty: Certainty | None = None
    relations: list[GoldRelation] = []


class GoldCitation(BaseModel):
    marker: str
    resolved_doi: str | None = None


class GoldPaper(BaseModel):
    doi: str
    order: int = Field(description="Ingestion order; antecedents must precede citers.")
    xml_resource: str = Field(description="Filename under interciter/data/sample/.")
    citations: list[GoldCitation] = []
    claims: list[GoldClaim] = []


class GoldCorpus(BaseModel):
    domain: str
    corpus_version: str
    papers: list[GoldPaper]
    equivalences: list[list[str]] = Field(
        default_factory=list,
        description="Groups of gold_ids adjudicated as semantically equivalent.",
    )

    def all_claims(self) -> list[GoldClaim]:
        return [c for p in self.papers for c in p.claims]


def load_gold(path: str | None = None) -> GoldCorpus:
    """Load a gold corpus from ``path``, or the bundled sample corpus when omitted."""
    if path is None:
        raw = (
            resources.files("interciter.data.gold")
            .joinpath("sample_gold.json")
            .read_text(encoding="utf-8")
        )
    else:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    return GoldCorpus.model_validate(json.loads(raw))
