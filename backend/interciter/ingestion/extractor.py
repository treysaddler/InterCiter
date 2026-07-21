"""Extraction interface and a deterministic stub implementation.

The design treats the LLM as a *starting point, not a source of truth*: extraction is
stateless, pluggable, and fully run-recorded, so a real model can be swapped in behind
the same interface without touching storage. This module ships a deterministic,
rule-based ``StubExtractor`` so the whole vertical slice runs with zero external
dependencies and reproducible output.

Every uncertain decision can **abstain**: a weak or conflicting stance signal yields
``unclear`` with a low score rather than a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from ..enums import (
    Certainty,
    EffectDirection,
    OccurrenceType,
    RelationFunction,
    RelationScope,
    RelationStance,
)
from .parser import ParsedCitation, ParsedPaper, ParsedPassage

# --- lexical cues (deliberately transparent; a real model replaces these) ---
_RESULT_CUES = re.compile(
    r"\b(significant(?:ly)?|increased?|decreased?|reduced?|elevated|higher|lower|"
    r"greater|fewer|associated with|correlat(?:ed|ion)|improved|risk|odds ratio|"
    r"hazard ratio|p\s*[<=]|more likely|less likely)\b",
    re.IGNORECASE,
)
_INCREASE_CUES = re.compile(
    r"\b(increased?|elevated|higher|greater|more likely|improved|rose|upregulat)\b",
    re.IGNORECASE,
)
_DECREASE_CUES = re.compile(
    r"\b(decreased?|reduced?|lower|fewer|less likely|declin|downregulat|suppress)\b",
    re.IGNORECASE,
)
_NEGATION_CUES = re.compile(
    r"\b(no significant|not significant|did not|no difference|no effect|failed to|"
    r"unable to|no association)\b",
    re.IGNORECASE,
)
_HYPOTHESIS_CUES = re.compile(
    r"\b(we hypothesi[sz]e|we propose|it is possible that|we predict)\b", re.IGNORECASE
)
_HEDGE_CUES = re.compile(
    r"\b(may|might|could|suggests?|possibly|potentially|appears? to)\b", re.IGNORECASE
)
_STRONG_CUES = re.compile(
    r"\b(demonstrate[sd]?|show(?:ed|s)?|establish(?:ed)?|confirm(?:ed|s)?)\b",
    re.IGNORECASE,
)

_METHOD_CUES = re.compile(
    r"\b(as described|using the|following the|protocol|method of|according to|"
    r"we used|were performed as)\b",
    re.IGNORECASE,
)
_CONTRAST_CUES = re.compile(
    r"\b(in contrast|however|unlike|contrary to|differs? from|whereas|"
    r"did not replicate|inconsistent with)\b",
    re.IGNORECASE,
)
_SUPPORT_CUES = re.compile(
    r"\b(consistent with|in agreement|agreement with|confirm(?:s|ed)?|corroborat|"
    r"support(?:s|ed|ing)?|in line with|as reported|as (?:previously )?shown|"
    r"replicat|similar to those|extends? (?:the )?finding)\b",
    re.IGNORECASE,
)
_COMPARISON_CUES = re.compile(
    r"\b(compared (?:to|with)|relative to|versus|vs\.?|than (?:in|those))\b",
    re.IGNORECASE,
)

_MARKER_STRIP = re.compile(r"\s*[\[(]?\b\d{1,3}\b[\])]?(?:\s*[-,]\s*\d{1,3})?\s*$")
_WS = re.compile(r"\s+")

_STANCE_ABSTAIN_THRESHOLD = 0.5


@dataclass
class ExtractedRelation:
    citation: ParsedCitation
    function: RelationFunction
    stance: RelationStance
    scope: RelationScope
    stance_distribution: dict[str, float]
    stance_score: float


@dataclass
class ExtractedClaim:
    passage_index: int
    occurrence_type: OccurrenceType
    span_start: int
    span_end: int
    normalized_text: str
    qualifiers: dict
    relations: list[ExtractedRelation] = field(default_factory=list)


class Extractor(Protocol):
    """A swappable extraction backend. Its identity is recorded on every ExtractionRun."""

    name: str
    provider: str
    version: str
    prompt_template_version: str

    def extract(self, paper: ParsedPaper) -> list[ExtractedClaim]: ...


class StubExtractor:
    """Deterministic, rule-based extractor. No network, fully reproducible."""

    name = "interciter-stub"
    provider = "local"
    version = "0.1.0"
    prompt_template_version = "stub-v1"

    def extract(self, paper: ParsedPaper) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        for index, passage in enumerate(paper.passages):
            is_result = bool(_RESULT_CUES.search(passage.text))
            has_citation = bool(passage.citations)
            # Emit an occurrence only if it is an empirical result claim or it makes a
            # citation we can turn into a relation. Everything else is skipped in the MVP.
            if not (is_result or has_citation):
                continue

            occ_type = self._occurrence_type(passage, is_result)
            claim = ExtractedClaim(
                passage_index=index,
                occurrence_type=occ_type,
                span_start=0,
                span_end=len(passage.text),
                normalized_text=self._normalize(passage.text),
                qualifiers=self._qualifiers(passage.text),
                relations=[self._classify_relation(passage, c) for c in passage.citations],
            )
            claims.append(claim)
        return claims

    # --- helpers -------------------------------------------------------------

    def _occurrence_type(self, passage: ParsedPassage, is_result: bool) -> OccurrenceType:
        text = passage.text
        section = (passage.section or "").lower()
        if _HYPOTHESIS_CUES.search(text):
            return OccurrenceType.hypothesis
        if "method" in section or _METHOD_CUES.search(text):
            return OccurrenceType.method_description
        if is_result and ("result" in section or "discussion" in section or True):
            return OccurrenceType.reported_result if is_result else OccurrenceType.background_assertion
        return OccurrenceType.background_assertion

    def _normalize(self, text: str) -> str:
        stripped = _MARKER_STRIP.sub("", text).strip()
        stripped = _WS.sub(" ", stripped)
        return stripped or text.strip()

    def _qualifiers(self, text: str) -> dict:
        negated = bool(_NEGATION_CUES.search(text))
        if negated:
            direction = EffectDirection.no_effect
        elif _INCREASE_CUES.search(text) and _DECREASE_CUES.search(text):
            direction = EffectDirection.mixed
        elif _INCREASE_CUES.search(text):
            direction = EffectDirection.increase
        elif _DECREASE_CUES.search(text):
            direction = EffectDirection.decrease
        else:
            direction = EffectDirection.unclear

        if _STRONG_CUES.search(text) or re.search(r"\bsignificant", text, re.IGNORECASE):
            certainty = Certainty.definite
        elif _HEDGE_CUES.search(text):
            certainty = Certainty.possible
        else:
            certainty = Certainty.probable

        return {
            "effect_direction": direction.value,
            "certainty": certainty.value,
            "negated": negated,
            # Population/intervention/comparator/outcome are abstained on in the stub.
            "population": None,
            "intervention": None,
            "comparator": None,
            "outcome": None,
        }

    def _classify_relation(
        self, passage: ParsedPassage, citation: ParsedCitation
    ) -> ExtractedRelation:
        text = passage.text
        section = (passage.section or "").lower()

        # Function.
        if "method" in section or _METHOD_CUES.search(text):
            function = RelationFunction.method
        elif _CONTRAST_CUES.search(text):
            function = RelationFunction.comparison
        elif _COMPARISON_CUES.search(text):
            function = RelationFunction.comparison
        elif _SUPPORT_CUES.search(text) or _RESULT_CUES.search(text):
            function = RelationFunction.direct_evidence
        else:
            function = RelationFunction.background

        # Stance distribution over support / contradict / neutral, then abstain if flat.
        support = 0.15
        contradict = 0.1
        neutral = 0.3
        if _SUPPORT_CUES.search(text):
            support += 0.6
        if _CONTRAST_CUES.search(text):
            contradict += 0.6
        if function is RelationFunction.method:
            neutral += 0.4  # citing a method is not an epistemic stance
        total = support + contradict + neutral
        dist = {
            "support": round(support / total, 3),
            "contradict": round(contradict / total, 3),
            "neutral": round(neutral / total, 3),
        }
        top_label = max(dist, key=dist.get)
        top_score = dist[top_label]
        if top_score < _STANCE_ABSTAIN_THRESHOLD:
            stance = RelationStance.unclear
        else:
            stance = RelationStance(top_label)

        scope = RelationScope.whole_claim
        return ExtractedRelation(
            citation=citation,
            function=function,
            stance=stance,
            scope=scope,
            stance_distribution=dist,
            stance_score=round(top_score, 3),
        )


def default_extractor() -> Extractor:
    return StubExtractor()
