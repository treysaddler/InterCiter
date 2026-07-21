"""Parser tests: anchoring, citation-to-sentence mapping, and XML hardening."""

from __future__ import annotations

import pytest

from interciter.ingestion.parser import XMLParseError, parse_jats

from helpers import load_sample


def test_metadata_and_offsets():
    paper = parse_jats(load_sample("paper_a.xml"))
    assert paper.doi == "10.1234/interciter.a"
    assert paper.pmid == "31000002"
    assert paper.year == 2021
    assert paper.authors == ["Ada Okafor"]
    assert paper.passages, "expected at least one passage"
    # Offsets are monotonically non-decreasing across the document.
    starts = [p.char_start for p in paper.passages]
    assert starts == sorted(starts)


def test_citations_attach_to_sentences():
    paper = parse_jats(load_sample("paper_a.xml"))
    rids = {c.rid for p in paper.passages for c in p.citations}
    assert {"B1", "B2", "B3"} <= rids
    # The sentence citing B1 mentions metformin.
    b1_passages = [p for p in paper.passages if any(c.rid == "B1" for c in p.citations)]
    assert b1_passages
    assert "metformin" in b1_passages[0].text.lower()


def test_references_parsed():
    paper = parse_jats(load_sample("paper_a.xml"))
    assert paper.references["B1"].doi == "10.1234/interciter.b"
    assert paper.references["B2"].doi == "10.1234/external.assay2"


def test_rejects_entity_expansion_attack():
    # Billion-laughs style payload must be refused by defusedxml, not expanded.
    payload = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;">
    ]>
    <article><body><sec><p>&lol2;</p></sec></body></article>"""
    with pytest.raises(XMLParseError):
        parse_jats(payload)


def test_rejects_garbage():
    with pytest.raises(XMLParseError):
        parse_jats("not xml at all")
