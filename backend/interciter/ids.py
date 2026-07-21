"""Stable, prefixed identifier generation.

Every entity gets an opaque, URL-safe id with a short type prefix so ids are
self-describing in logs and API responses (e.g. ``occ_1f3a...``). Ids are random
(uuid4) — never derived from content — so re-ingestion always produces new records
rather than silently overwriting the immutable system of record.
"""

from __future__ import annotations

import uuid

_PREFIXES = {
    "PaperWork": "work",
    "PaperVersion": "ver",
    "Passage": "pas",
    "CitationMention": "cite",
    "ExtractionRun": "run",
    "ClaimOccurrence": "occ",
    "ClaimInterpretation": "interp",
    "ClaimCluster": "clus",
    "ClusterMembership": "mem",
    "RelationAssertion": "rel",
    "ReviewDecision": "rev",
    "Assessment": "asmt",
    "Job": "job",
    "User": "user",
}


def new_id(entity: str) -> str:
    prefix = _PREFIXES.get(entity, "id")
    return f"{prefix}_{uuid.uuid4().hex}"
