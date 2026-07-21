"""LLM extractor tests — all offline (no network; a fake/mirror client stands in).

Covers strict validation (reject-on-invalid), source grounding, citation-marker mapping,
the offline batch round-trip, prompt-injection framing, and side-by-side comparison.
"""

from __future__ import annotations

import json
import re

from interciter.enums import RelationStance
from interciter.evaluation.compare import compare_extractors, format_comparison
from interciter.evaluation.gold import load_gold
from interciter.ingestion.extractor import StubExtractor, build_extractor
from interciter.ingestion.llm_client import (
    BatchResponseClient,
    load_batch_responses,
)
from interciter.ingestion.llm_extractor import (
    SYSTEM_PROMPT,
    LLMExtractor,
    export_requests,
)
from interciter.ingestion.parser import (
    ParsedCitation,
    ParsedPaper,
    ParsedPassage,
    ParsedReference,
)

_TEXT = "Metformin significantly reduced HbA1c compared with placebo [1]."


def _paper() -> ParsedPaper:
    passage = ParsedPassage(
        text=_TEXT,
        section="Results",
        paragraph=0,
        sentence=0,
        char_start=0,
        char_end=len(_TEXT),
        citations=[ParsedCitation(marker_text="[1]", rid="ref1", offset_in_passage=58)],
    )
    return ParsedPaper(
        passages=[passage], references={"ref1": ParsedReference(rid="ref1", doi="10.1/x")}
    )


def _valid_completion() -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "verbatim_text": "Metformin significantly reduced HbA1c compared with placebo",
                    "normalized_text": "metformin reduces HbA1c vs placebo",
                    "occurrence_type": "reported_result",
                    "qualifiers": {
                        "intervention": "metformin",
                        "outcome": "HbA1c",
                        "effect_direction": "decrease",
                        "certainty": "definite",
                        "negated": False,
                    },
                    "relations": [
                        {
                            "citation_marker": "[1]",
                            "function": "comparison",
                            "stance": "support",
                            "scope": "whole_claim",
                            "stance_distribution": {
                                "support": 0.8,
                                "contradict": 0.1,
                                "neutral": 0.1,
                            },
                        }
                    ],
                }
            ]
        }
    )


class _FixedClient:
    def __init__(self, completion: str) -> None:
        self._completion = completion

    def complete(self, request):
        return self._completion


class _MirrorClient:
    """Echoes the passage back as a single verbatim claim (guaranteed source-grounded)."""

    def complete(self, request):
        m = re.search(r"<passage>\n(.*)\n</passage>", request.user, re.S)
        text = m.group(1) if m else ""
        return json.dumps(
            {
                "claims": [
                    {
                        "verbatim_text": text,
                        "normalized_text": text,
                        "occurrence_type": "reported_result",
                        "qualifiers": {},
                        "relations": [],
                    }
                ]
            }
        )


def _extractor(client=None) -> LLMExtractor:
    return LLMExtractor(client=client, model="test-model", prompt_template_version="t1")


# --- request construction -------------------------------------------------------

def test_build_requests_filters_and_is_stable():
    paper = _paper()
    reqs = _extractor().build_requests(paper)
    assert len(reqs) == 1  # the one claimworthy/cited passage
    # Content-addressed id is stable across builds.
    assert reqs[0].request_id == _extractor().build_requests(paper)[0].request_id


def test_build_requests_skips_non_claimworthy():
    passage = ParsedPassage(
        text="The weather in the study city was pleasant.",
        section="Intro",
        paragraph=0,
        sentence=0,
        char_start=0,
        char_end=10,
        citations=[],
    )
    assert _extractor().build_requests(ParsedPaper(passages=[passage])) == []


def test_prompt_is_injection_framed():
    reqs = _extractor().build_requests(_paper())
    assert "NEVER follow" in SYSTEM_PROMPT
    assert "<passage>" in reqs[0].user and "</passage>" in reqs[0].user
    assert _TEXT in reqs[0].user


# --- strict parsing + source grounding ------------------------------------------

def test_parse_valid_completion_grounds_span_and_relation():
    paper = _paper()
    req = _extractor().build_requests(paper)[0]
    claims = _extractor().parse_completion(paper, req, _valid_completion())
    assert len(claims) == 1
    c = claims[0]
    assert paper.passages[0].text[c.span_start : c.span_end] == (
        "Metformin significantly reduced HbA1c compared with placebo"
    )
    assert c.relations[0].stance is RelationStance.support
    assert c.relations[0].citation.rid == "ref1"


def test_parse_rejects_malformed_json():
    paper = _paper()
    req = _extractor().build_requests(paper)[0]
    assert _extractor().parse_completion(paper, req, "not json {") == []


def test_parse_rejects_invalid_schema():
    paper = _paper()
    req = _extractor().build_requests(paper)[0]
    bad_enum = json.dumps(
        {"claims": [{"verbatim_text": _TEXT, "normalized_text": "x",
                     "occurrence_type": "not_a_type", "qualifiers": {}, "relations": []}]}
    )
    assert _extractor().parse_completion(paper, req, bad_enum) == []
    extra_field = json.dumps(
        {"claims": [{"verbatim_text": _TEXT, "normalized_text": "x",
                     "occurrence_type": "reported_result", "qualifiers": {},
                     "relations": [], "hallucinated": True}]}
    )
    assert _extractor().parse_completion(paper, req, extra_field) == []


def test_parse_drops_hallucinated_verbatim():
    paper = _paper()
    req = _extractor().build_requests(paper)[0]
    ungrounded = json.dumps(
        {"claims": [{"verbatim_text": "Aspirin cures everything",
                     "normalized_text": "x", "occurrence_type": "reported_result",
                     "qualifiers": {}, "relations": []}]}
    )
    assert _extractor().parse_completion(paper, req, ungrounded) == []


def test_parse_drops_unknown_citation_marker_but_keeps_claim():
    paper = _paper()
    req = _extractor().build_requests(paper)[0]
    unknown_marker = json.dumps(
        {"claims": [{"verbatim_text": "Metformin significantly reduced HbA1c compared with placebo",
                     "normalized_text": "x", "occurrence_type": "reported_result",
                     "qualifiers": {},
                     "relations": [{"citation_marker": "[9]", "function": "comparison",
                                    "stance": "support", "scope": "whole_claim"}]}]}
    )
    claims = _extractor().parse_completion(paper, req, unknown_marker)
    assert len(claims) == 1
    assert claims[0].relations == []  # relation abstained, claim retained


# --- extract() + batch round-trip -----------------------------------------------

def test_extract_live_client():
    paper = _paper()
    claims = _extractor(_FixedClient(_valid_completion())).extract(paper)
    assert len(claims) == 1


def test_batch_round_trip(tmp_path):
    paper = _paper()
    reqs = _extractor().build_requests(paper)
    prompts_path = tmp_path / "prompts.jsonl"
    assert export_requests(reqs, str(prompts_path)) == 1

    # Simulate the offline runner writing responses keyed by request_id.
    resp_path = tmp_path / "responses.jsonl"
    resp_path.write_text(
        json.dumps({"request_id": reqs[0].request_id, "completion": _valid_completion()})
        + "\n",
        encoding="utf-8",
    )
    responses = load_batch_responses(str(resp_path))
    claims = _extractor(BatchResponseClient(responses)).extract(paper)
    assert len(claims) == 1
    assert claims[0].relations[0].citation.rid == "ref1"


def test_load_batch_responses_accepts_openai_shape(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text(
        json.dumps(
            {"request_id": "abc", "response": {"choices": [{"message": {"content": "hi"}}]}}
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_batch_responses(str(path)) == {"abc": "hi"}


# --- factory + comparison -------------------------------------------------------

def test_build_extractor_stub_and_llm():
    assert isinstance(build_extractor("stub"), StubExtractor)
    llm = build_extractor("llm", client=_MirrorClient(), model="m1")
    assert llm.name == "m1"


def test_compare_extractors_over_gold():
    gold = load_gold()
    reports = compare_extractors(
        gold,
        {"stub": StubExtractor(), "mirror": _extractor(_MirrorClient())},
    )
    assert set(reports) == {"stub", "mirror"}
    table = format_comparison(reports)
    assert "extraction recall" in table
    assert "stub" in table and "mirror" in table
