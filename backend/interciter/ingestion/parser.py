"""Hardened JATS/PMC XML parser.

Ingestion eats untrusted documents, so parsing is defensive (docs/architecture.md):

* XML is parsed with ``defusedxml`` — external entities and entity-expansion (billion
  laughs) attacks are refused.
* A byte-size limit is enforced by the caller *before* this module is reached.
* Paper text is treated strictly as **data**. This parser only extracts text and
  structure; it never interprets document content as instructions.

Output is a plain ``ParsedPaper`` with document-relative character offsets, so every
passage and citation marker can be anchored exactly to the ``PaperVersion``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from defusedxml.ElementTree import fromstring
from xml.etree.ElementTree import Element

# Sentence boundary: end punctuation followed by whitespace + capital/opening.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


class XMLParseError(ValueError):
    """Raised when the document is not well-formed or not recognizably JATS."""


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


@dataclass
class ParsedReference:
    rid: str
    label: str | None = None
    title: str | None = None
    doi: str | None = None
    pmid: str | None = None
    year: int | None = None


@dataclass
class ParsedCitation:
    marker_text: str
    rid: str | None
    offset_in_passage: int


@dataclass
class ParsedPassage:
    text: str
    section: str | None
    paragraph: int
    sentence: int
    char_start: int
    char_end: int
    citations: list[ParsedCitation] = field(default_factory=list)


@dataclass
class ParsedPaper:
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    passages: list[ParsedPassage] = field(default_factory=list)
    references: dict[str, ParsedReference] = field(default_factory=dict)


class _ParagraphRenderer:
    """Flattens a JATS paragraph to plain text, recording citation-marker offsets."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0
        self.citations: list[ParsedCitation] = []

    def _append(self, text: str) -> None:
        if text:
            self.parts.append(text)
            self.length += len(text)

    def walk(self, elem: Element) -> None:
        name = _localname(elem.tag)
        if name == "xref" and elem.get("ref-type") == "bibr":
            marker = (elem.text or "").strip() or "?"
            self.citations.append(
                ParsedCitation(
                    marker_text=marker,
                    rid=elem.get("rid"),
                    offset_in_passage=self.length,
                )
            )
            self._append(marker)
        else:
            self._append(elem.text or "")
            for child in elem:
                self.walk(child)
        self._append(elem.tail or "")

    def render(self, elem: Element) -> str:
        self._append(elem.text or "")
        for child in elem:
            self.walk(child)
        return "".join(self.parts)


def _find_meta(root: Element) -> Element | None:
    for el in root.iter():
        if _localname(el.tag) == "article-meta":
            return el
    return None


def _text_of(elem: Element | None) -> str | None:
    if elem is None:
        return None
    text = "".join(elem.itertext()).strip()
    return text or None


def _parse_metadata(paper: ParsedPaper, root: Element) -> None:
    meta = _find_meta(root)
    if meta is None:
        return
    for el in meta.iter():
        name = _localname(el.tag)
        if name == "article-title" and paper.title is None:
            paper.title = _text_of(el)
        elif name == "journal-title" and paper.venue is None:
            paper.venue = _text_of(el)
        elif name == "article-id" or name == "pub-id":
            id_type = el.get("pub-id-type") or el.get("article-id-type")
            value = _text_of(el)
            if id_type == "doi" and paper.doi is None:
                paper.doi = value
            elif id_type == "pmid" and paper.pmid is None:
                paper.pmid = value
    # Journal title can also live outside article-meta.
    if paper.venue is None:
        for el in root.iter():
            if _localname(el.tag) == "journal-title":
                paper.venue = _text_of(el)
                break
    # Authors: contrib/name -> "given surname".
    for contrib in meta.iter():
        if _localname(contrib.tag) != "contrib":
            continue
        surname = given = None
        for sub in contrib.iter():
            if _localname(sub.tag) == "surname":
                surname = _text_of(sub)
            elif _localname(sub.tag) == "given-names":
                given = _text_of(sub)
        full = " ".join(p for p in (given, surname) if p)
        if full:
            paper.authors.append(full)
    # Publication year.
    for el in meta.iter():
        if _localname(el.tag) == "year":
            raw = _text_of(el)
            if raw and raw.isdigit():
                paper.year = int(raw)
                break


def _parse_references(paper: ParsedPaper, root: Element) -> None:
    for ref in root.iter():
        if _localname(ref.tag) != "ref":
            continue
        rid = ref.get("id")
        if not rid:
            continue
        parsed = ParsedReference(rid=rid)
        for el in ref.iter():
            name = _localname(el.tag)
            if name == "label":
                parsed.label = _text_of(el)
            elif name == "article-title" and parsed.title is None:
                parsed.title = _text_of(el)
            elif name == "pub-id":
                id_type = el.get("pub-id-type")
                value = _text_of(el)
                if id_type == "doi":
                    parsed.doi = value
                elif id_type == "pmid":
                    parsed.pmid = value
            elif name == "year":
                raw = _text_of(el)
                if raw and raw.isdigit():
                    parsed.year = int(raw)
        paper.references[rid] = parsed


def _split_sentences(text: str) -> list[tuple[int, str]]:
    """Split paragraph text into (offset, sentence) pairs, offsets paragraph-relative."""
    sentences: list[tuple[int, str]] = []
    cursor = 0
    for chunk in _SENTENCE_BOUNDARY.split(text):
        idx = text.find(chunk, cursor)
        if idx < 0:
            idx = cursor
        stripped = chunk.strip()
        if stripped:
            lead = len(chunk) - len(chunk.lstrip())
            sentences.append((idx + lead, stripped))
        cursor = idx + len(chunk)
    return sentences


def _parse_body(paper: ParsedPaper, root: Element) -> None:
    body = None
    for el in root.iter():
        if _localname(el.tag) == "body":
            body = el
            break
    if body is None:
        return

    doc_cursor = 0
    para_index = 0

    def current_section(sec: Element) -> str | None:
        for child in sec:
            if _localname(child.tag) == "title":
                return _text_of(child)
        return None

    def handle_paragraph(p_elem: Element, section: str | None) -> None:
        nonlocal doc_cursor, para_index
        renderer = _ParagraphRenderer()
        para_text = renderer.render(p_elem).strip()
        if not para_text:
            return
        para_index += 1
        # Assign each citation to the sentence containing its offset.
        for s_index, (s_offset, sentence_text) in enumerate(
            _split_sentences(para_text), start=1
        ):
            s_end = s_offset + len(sentence_text)
            char_start = doc_cursor + s_offset
            passage = ParsedPassage(
                text=sentence_text,
                section=section,
                paragraph=para_index,
                sentence=s_index,
                char_start=char_start,
                char_end=char_start + len(sentence_text),
            )
            for cit in renderer.citations:
                if s_offset <= cit.offset_in_passage < s_end:
                    passage.citations.append(
                        ParsedCitation(
                            marker_text=cit.marker_text,
                            rid=cit.rid,
                            offset_in_passage=cit.offset_in_passage - s_offset,
                        )
                    )
            paper.passages.append(passage)
        doc_cursor += len(para_text) + 1  # +1 for a normalized paragraph separator

    def walk_section(sec: Element, inherited: str | None) -> None:
        section_name = current_section(sec) or inherited
        for child in sec:
            name = _localname(child.tag)
            if name == "p":
                handle_paragraph(child, section_name)
            elif name == "sec":
                walk_section(child, section_name)

    for child in body:
        name = _localname(child.tag)
        if name == "sec":
            walk_section(child, None)
        elif name == "p":
            handle_paragraph(child, None)


def parse_jats(xml: str | bytes) -> ParsedPaper:
    """Parse JATS/PMC XML into a ``ParsedPaper``. Raises ``XMLParseError`` on bad input."""
    try:
        root = fromstring(xml)
    except Exception as exc:  # defusedxml raises on entity attacks and malformed XML
        raise XMLParseError(f"could not parse XML: {exc}") from exc

    paper = ParsedPaper()
    _parse_metadata(paper, root)
    _parse_references(paper, root)
    _parse_body(paper, root)

    if not paper.passages and paper.title is None:
        raise XMLParseError("document is not recognizably JATS (no metadata or body)")
    return paper
