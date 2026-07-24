"""Bulk offline LLM extraction — one corpus of prompts for an HPC run, then replay.

The single-paper seam (:func:`llm_extractor.export_requests` + :class:`BatchResponseClient`)
is enough for one document. For bulk extraction on the NIEHS SLURM cluster we consolidate
*many* papers into one prompt file plus a manifest, run them all on a GPU node with a
local model (see ``scripts/hpc/``), and replay the completions back through the *same*
strict, source-grounded extractor — extraction is byte-for-byte identical whether the
model ran live or in a batch job.

Layout written by :func:`export_corpus` under ``out_dir``::

    manifest.json          # model, template, and per-doc request-id lists
    prompts.jsonl          # consolidated OpenAI-shaped requests (the runner's input)
    sources/<doc_id>.xml   # each paper's JATS, so import is fully offline

The runner produces ``completions.jsonl`` (``{request_id, completion}`` rows, or the
OpenAI batch shape — :func:`load_batch_responses` accepts both). :func:`ingest_corpus`
reads the manifest, re-parses each stored source, and ingests with the replayed answers.

**Reproducibility:** ``request_id`` is content-addressed over
``prompt_template_version + model + passage_text`` (:func:`llm_client.request_id`), so the
manifest pins *both* the model and the template version and the import path reconstructs
the extractor with exactly those, guaranteeing responses map back to the right prompt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, get_settings
from .llm_client import BatchResponseClient, load_batch_responses
from .llm_extractor import LLMExtractor
from .parser import parse_jats
from .pipeline import IngestResult, ingest_paper

MANIFEST_NAME = "manifest.json"
PROMPTS_NAME = "prompts.jsonl"
SOURCES_DIR = "sources"

_SAFE_DOC_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_doc_id(doc_id: str) -> str:
    """A filesystem-safe stem for a document id (e.g. a PMCID or a file name)."""
    cleaned = _SAFE_DOC_ID.sub("_", doc_id.strip()).strip("._")
    return cleaned or "doc"


def _make_extractor(model: str, template_version: str, settings: Settings) -> LLMExtractor:
    """Construct the extractor pinned to a model + template so ids stay reproducible.

    ``client`` is ``None`` for export (only :meth:`build_requests` is used) and a
    :class:`BatchResponseClient` for import. Temperature and ``max_tokens`` do not enter
    the ``request_id`` hash, so taking them from settings is safe on both paths.
    """
    return LLMExtractor(
        client=None,
        model=model,
        prompt_template_version=template_version,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )


@dataclass
class BatchDoc:
    doc_id: str
    source_path: str  # relative to the batch dir, e.g. "sources/PMC123.xml"
    request_ids: list[str] = field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None

    def to_json(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "request_ids": self.request_ids,
            "doi": self.doi,
            "pmid": self.pmid,
        }

    @classmethod
    def from_json(cls, data: dict) -> "BatchDoc":
        return cls(
            doc_id=data["doc_id"],
            source_path=data["source_path"],
            request_ids=list(data.get("request_ids", [])),
            doi=data.get("doi"),
            pmid=data.get("pmid"),
        )


@dataclass
class BatchManifest:
    model: str
    prompt_template_version: str
    docs: list[BatchDoc] = field(default_factory=list)

    @property
    def prompt_count(self) -> int:
        return sum(len(doc.request_ids) for doc in self.docs)

    def to_json(self) -> dict:
        return {
            "model": self.model,
            "prompt_template_version": self.prompt_template_version,
            "doc_count": len(self.docs),
            "prompt_count": self.prompt_count,
            "docs": [doc.to_json() for doc in self.docs],
        }

    @classmethod
    def from_json(cls, data: dict) -> "BatchManifest":
        return cls(
            model=data["model"],
            prompt_template_version=data["prompt_template_version"],
            docs=[BatchDoc.from_json(d) for d in data.get("docs", [])],
        )


@dataclass
class BatchIngestResult:
    doc_id: str
    result: IngestResult


def export_corpus(
    docs: Iterable[tuple[str, str]],
    out_dir: str | Path,
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> BatchManifest:
    """Consolidate many papers into one HPC batch under ``out_dir``.

    ``docs`` yields ``(doc_id, jats_xml)`` pairs. Writes ``prompts.jsonl`` (the runner's
    input), a copy of each source under ``sources/`` (so import needs no network), and a
    ``manifest.json``. Returns the manifest.
    """
    settings = settings or get_settings()
    model = model or settings.llm_model
    template = settings.llm_prompt_template_version
    extractor = _make_extractor(model, template, settings)

    out = Path(out_dir)
    sources = out / SOURCES_DIR
    sources.mkdir(parents=True, exist_ok=True)

    manifest = BatchManifest(model=model, prompt_template_version=template)
    prompts_path = out / PROMPTS_NAME
    with prompts_path.open("w", encoding="utf-8") as prompts_fh:
        for doc_id, xml in docs:
            stem = _safe_doc_id(doc_id)
            source_rel = f"{SOURCES_DIR}/{stem}.xml"
            (out / source_rel).write_text(xml, encoding="utf-8")

            paper = parse_jats(xml)
            requests = extractor.build_requests(paper)
            for request in requests:
                prompts_fh.write(request.to_json_line() + "\n")

            manifest.docs.append(
                BatchDoc(
                    doc_id=doc_id,
                    source_path=source_rel,
                    request_ids=[r.request_id for r in requests],
                )
            )

    (out / MANIFEST_NAME).write_text(
        json.dumps(manifest.to_json(), indent=2), encoding="utf-8"
    )
    return manifest


def load_manifest(batch_dir: str | Path) -> BatchManifest:
    data = json.loads((Path(batch_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))
    return BatchManifest.from_json(data)


def ingest_corpus(
    batch_dir: str | Path,
    responses_path: str | Path,
    *,
    session,
    settings: Settings | None = None,
    model: str | None = None,
) -> list[BatchIngestResult]:
    """Replay ``completions.jsonl`` from an HPC run and ingest every doc in the manifest.

    The extractor is rebuilt from the manifest's pinned model + template so the
    content-addressed ``request_id``s line up with the exported prompts. Each stored
    source is re-parsed offline; missing responses simply abstain (the strict extractor's
    default), so a partial run still ingests what it can.
    """
    settings = settings or get_settings()
    batch_dir = Path(batch_dir)
    manifest = load_manifest(batch_dir)

    responses = load_batch_responses(str(responses_path))
    client = BatchResponseClient(responses)
    extractor = _make_extractor(
        model or manifest.model, manifest.prompt_template_version, settings
    )
    extractor.client = client

    results: list[BatchIngestResult] = []
    for doc in manifest.docs:
        xml = (batch_dir / doc.source_path).read_text(encoding="utf-8")
        result = ingest_paper(
            session,
            xml=xml,
            doi=doc.doi,
            pmid=doc.pmid,
            extractor=extractor,
            settings=settings,
        )
        results.append(BatchIngestResult(doc_id=doc.doc_id, result=result))
    return results
