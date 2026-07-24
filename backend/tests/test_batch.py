"""Bulk HPC batch export/import round-trip — all offline (no cluster, no network).

Mirrors what the vLLM runner does on the cluster by echoing each passage back as a
verbatim claim, so the strict extractor produces grounded occurrences on import.
"""

from __future__ import annotations

import json
import re

from helpers import load_sample

from interciter.ingestion.batch import (
    MANIFEST_NAME,
    PROMPTS_NAME,
    export_corpus,
    ingest_corpus,
    load_manifest,
)

_PASSAGE = re.compile(r"<passage>\n(.*)\n</passage>", re.S)


def _mirror_responses(batch_dir, out_path) -> int:
    """Turn each exported prompt into a completion that echoes its passage verbatim."""
    count = 0
    with (batch_dir / PROMPTS_NAME).open(encoding="utf-8") as prompts, out_path.open(
        "w", encoding="utf-8"
    ) as out:
        for line in prompts:
            row = json.loads(line)
            user = row["messages"][1]["content"]
            m = _PASSAGE.search(user)
            text = m.group(1) if m else ""
            completion = json.dumps(
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
            out.write(
                json.dumps({"request_id": row["request_id"], "completion": completion})
                + "\n"
            )
            count += 1
    return count


def _export(tmp_path):
    docs = [("PMC1", load_sample("paper_a.xml")), ("PMC2", load_sample("paper_b.xml"))]
    return export_corpus(docs, tmp_path, model="test-model")


def test_export_writes_manifest_prompts_and_sources(tmp_path):
    manifest = _export(tmp_path)

    assert (tmp_path / MANIFEST_NAME).exists()
    assert (tmp_path / PROMPTS_NAME).exists()
    assert (tmp_path / "sources" / "PMC1.xml").exists()
    assert (tmp_path / "sources" / "PMC2.xml").exists()

    assert manifest.model == "test-model"
    assert len(manifest.docs) == 2
    assert manifest.prompt_count > 0
    # Every prompt line's request_id is accounted for in the manifest.
    prompt_ids = {
        json.loads(line)["request_id"]
        for line in (tmp_path / PROMPTS_NAME).read_text().splitlines()
        if line.strip()
    }
    manifest_ids = {rid for doc in manifest.docs for rid in doc.request_ids}
    assert prompt_ids == manifest_ids
    assert len(prompt_ids) == manifest.prompt_count


def test_round_trip_ingests_every_doc(tmp_path, session):
    _export(tmp_path)
    responses = tmp_path / "completions.jsonl"
    n = _mirror_responses(tmp_path, responses)
    assert n > 0

    results = ingest_corpus(tmp_path, responses, session=session)

    assert [r.doc_id for r in results] == ["PMC1", "PMC2"]
    # Mirrored passages are grounded, so every doc yields occurrences + interpretations.
    assert sum(r.result.occurrences for r in results) > 0
    assert sum(r.result.interpretations for r in results) > 0


def test_import_pins_model_and_template_from_manifest(tmp_path, session):
    _export(tmp_path)
    manifest = load_manifest(tmp_path)
    assert manifest.model == "test-model"
    assert manifest.prompt_template_version  # recorded for reproducible request ids

    responses = tmp_path / "completions.jsonl"
    _mirror_responses(tmp_path, responses)
    # No --model override: the manifest's pinned model must line the ids up.
    results = ingest_corpus(tmp_path, responses, session=session)
    assert sum(r.result.occurrences for r in results) > 0


def test_missing_responses_still_ingests_partial(tmp_path, session):
    _export(tmp_path)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    # A run that produced nothing still ingests each doc (claims simply abstain).
    results = ingest_corpus(tmp_path, empty, session=session)
    assert len(results) == 2
    assert sum(r.result.occurrences for r in results) == 0
