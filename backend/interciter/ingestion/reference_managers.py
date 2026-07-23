"""Reference-manager export parsers (scite-parity WP9, F5).

Extract DOIs / PMIDs from reference-manager exports (Zotero, Mendeley, EndNote)
so a Collection — and later a litmaps Map / bibliometrix Corpus — can be seeded
from a reference library without OAuth. Pure and offline: it maps export *text*
to identifier lists; resolution to works (and metadata-stub creation) is left to
the existing `services/collections.add_members` path.

Supported formats:
- ``ris``    — RIS (Zotero/Mendeley/EndNote "Export → RIS").
- ``bibtex`` — BibTeX (Zotero/Mendeley "Export → BibTeX").
- ``csv``    — handled upstream by the identifier parser in ``collections``;
  ``detect_format`` may return it, but ``parse_references`` does not (callers
  route CSV/plain text through ``add_members(csv_text=...)``).

Only identifiers are extracted; titles/authors are intentionally ignored (the
ingest path re-derives metadata from the DOI/PMID). This keeps the importer a
thin, deterministic mapping with no network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMATS = ("ris", "bibtex", "csv")

# A DOI body: 10.<registrant>/<suffix>, stopping at whitespace or the delimiters
# that wrap values in RIS/BibTeX (quotes, braces, angle brackets, list commas).
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'{}<>,;]+", re.IGNORECASE)
# A PubMed id embedded in a URL (pubmed.ncbi.nlm.nih.gov/<id> or …/pubmed/<id>).
_PUBMED_URL_RE = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|/pubmed/)(\d{1,8})", re.IGNORECASE
)
# RIS tag line: two alnum chars, two spaces, hyphen, space, value.
_RIS_LINE_RE = re.compile(r"^([A-Z][A-Z0-9])  - (.*)$")
# A hint that a RIS accession number (AN) is a PubMed id rather than some other
# database key.
_PUBMED_HINT_RE = re.compile(r"pubmed|medline|\bnlm\b", re.IGNORECASE)
_BIBTEX_DOI_RE = re.compile(r"doi\s*=\s*[{\"]?\s*([^}\"\n]+)", re.IGNORECASE)
_BIBTEX_PMID_RE = re.compile(r"pmid\s*=\s*[{\"]?\s*(\d{1,8})", re.IGNORECASE)
_BIBTEX_ENTRY_RE = re.compile(r"@(\w+)\s*\{")
_BIBTEX_SKIP_TYPES = {"comment", "string", "preamble"}


@dataclass
class ParsedReferences:
    """Identifiers extracted from a reference-manager export.

    ``entry_count`` is the number of bibliographic entries seen; ``matched_count``
    is how many yielded at least one identifier (the rest cannot be imported and
    are reflected in the difference).
    """

    dois: list[str]
    pmids: list[str]
    entry_count: int
    matched_count: int


def detect_format(text: str, filename: str | None = None) -> str:
    """Best-effort format detection from a filename extension, then content."""
    if filename:
        low = filename.lower()
        if low.endswith(".ris"):
            return "ris"
        if low.endswith((".bib", ".bibtex")):
            return "bibtex"
        if low.endswith((".csv", ".txt")):
            return "csv"
    head = text.lstrip()
    if head.startswith("TY  - ") or re.search(r"^ER  -", text, re.MULTILINE):
        return "ris"
    if _BIBTEX_ENTRY_RE.match(head):
        return "bibtex"
    return "csv"


def _doi_in(text: str) -> str | None:
    match = _DOI_RE.search(text)
    if match is None:
        return None
    # Trailing prose/list punctuation is never part of a DOI suffix.
    return match.group(0).rstrip(".,;:").lower()


def _dedup(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _ris_entries(text: str) -> list[str]:
    """Split an RIS document into per-reference blocks (TY … ER)."""
    entries: list[str] = []
    current: list[str] = []
    started = False
    for line in text.splitlines():
        if line.startswith("TY  - "):
            if current:
                entries.append("\n".join(current))
            current = [line]
            started = True
        elif line.startswith("ER  -"):
            current.append(line)
            entries.append("\n".join(current))
            current = []
            started = False
        elif started:
            current.append(line)
    if current:
        entries.append("\n".join(current))
    # A malformed file with no TY/ER markers is treated as a single entry so a
    # stray DOI is still recoverable.
    return entries or ([text] if text.strip() else [])


def _ris_ids(entry: str) -> tuple[str | None, str | None]:
    doi: str | None = None
    pmid: str | None = None
    accession: str | None = None
    pubmed_hint = bool(_PUBMED_HINT_RE.search(entry))
    for line in entry.splitlines():
        match = _RIS_LINE_RE.match(line)
        if match is None:
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag in ("DO", "DI") and doi is None:
            doi = _doi_in(value)
        if tag == "AN" and value.isdigit():
            accession = value
        if pmid is None:
            url_pmid = _PUBMED_URL_RE.search(value)
            if url_pmid is not None:
                pmid = url_pmid.group(1)
    if doi is None:
        doi = _doi_in(entry)
    if pmid is None and accession is not None and pubmed_hint:
        pmid = accession
    return doi, pmid


def _bibtex_entries(text: str) -> list[str]:
    """Split a BibTeX document into per-entry bodies via brace matching."""
    entries: list[str] = []
    for match in _BIBTEX_ENTRY_RE.finditer(text):
        if match.group(1).lower() in _BIBTEX_SKIP_TYPES:
            continue
        depth = 1
        j = match.end()
        while j < len(text) and depth:
            char = text[j]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            j += 1
        entries.append(text[match.end() : j])
    return entries


def _bibtex_ids(entry: str) -> tuple[str | None, str | None]:
    doi: str | None = None
    pmid: str | None = None
    doi_field = _BIBTEX_DOI_RE.search(entry)
    if doi_field is not None:
        doi = _doi_in(doi_field.group(1))
    pmid_field = _BIBTEX_PMID_RE.search(entry)
    if pmid_field is not None:
        pmid = pmid_field.group(1)
    if pmid is None:
        url_pmid = _PUBMED_URL_RE.search(entry)
        if url_pmid is not None:
            pmid = url_pmid.group(1)
    if doi is None:
        doi = _doi_in(entry)
    return doi, pmid


def parse_references(text: str, fmt: str) -> ParsedReferences:
    """Parse ``ris`` or ``bibtex`` text into deduplicated identifier lists."""
    if fmt == "ris":
        entries = _ris_entries(text)
        extract = _ris_ids
    elif fmt == "bibtex":
        entries = _bibtex_entries(text)
        extract = _bibtex_ids
    else:
        raise ValueError(
            f"parse_references supports 'ris' or 'bibtex', not {fmt!r} "
            "(route CSV/plain text through add_members)"
        )

    dois: list[str] = []
    pmids: list[str] = []
    matched = 0
    for entry in entries:
        doi, pmid = extract(entry)
        if doi or pmid:
            matched += 1
        if doi:
            dois.append(doi)
        if pmid:
            pmids.append(pmid)
    return ParsedReferences(
        dois=_dedup(dois),
        pmids=_dedup(pmids),
        entry_count=len(entries),
        matched_count=matched,
    )
