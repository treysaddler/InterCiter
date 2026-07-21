# InterCiter — Architecture

## Three layers (unchanged)

1. **Ingestion / Extraction** — paper → occurrences, interpretations, relation assertions. Stateless and pluggable; extraction models are swappable without touching storage. Every run is recorded as an `ExtractionRun`.
2. **Knowledge Graph** — the immutable system of record plus its projections, BioLink-aligned.
3. **Access** — the API and everything on it. Frontend-agnostic; visualization endpoints return data, not images.

## Logical model vs physical schema

The single most important architectural decision added in this revision: **the rich immutable model is the system of record; queries traverse a derived projection.** Implementing the full entity catalog as the graph schema would put 5–7 hops between any two claims (`Cluster → Interpretation → Occurrence → RelationAssertion → Occurrence → Interpretation → Cluster`) — a constant-factor increase in size but a real traversal-depth problem for interactive exploration.

### Write model — system of record

A normalized relational store (PostgreSQL) holding every entity in [data-model.md](data-model.md), append-only in semantics: occurrences, interpretations, revision graphs, relation assertions, cluster memberships, review decisions, assessments. This is where provenance and auditability live. Nothing here is ever silently rewritten.

### Read model — materialized graph projection

A periodically rebuilt projection into the graph database (e.g. Neo4j) flattens the chain for traversal: one projected **Claim node** per current interpretation head (or cluster representative), with relation assertions projected as typed edges carrying `stance`, `function`, `resolution`, and both confidence scores.

Guardrails, so the projection never reintroduces the conflation the logical model exists to prevent:

- The projection is **derived, versioned, and rebuildable from the system of record at any time**. It is a cache, not a source of truth.
- A projected "consensus claim" node **carries its cluster provenance** — which memberships and which interpretation heads produced it — and every edge links back to its `RelationAssertion` id. Users (and downstream code) can always drill to evidence.
- Nothing writes to the projection except the projector. Human review, revisions, and scores land in the system of record and flow forward on rebuild.

### UX projection

The same principle applies one layer up: end users must not need to understand occurrence-vs-interpretation to read a result. The API serves **composed, reader-friendly views** (claim text + source snippet + provenance link) as the default representation, with the full audit structure available behind explicit endpoints ([api.md](api.md)). The audit model is for machines and reviewers; the default read path is for researchers. This is acknowledged frontend/API design work, not an afterthought.

## Semantic Scholar integration

Semantic Scholar remains the **paper + citation-graph substrate** (Datasets API, monthly snapshots + incremental diffs); InterCiter's novel layer sits on top. Revisions to the original plan:

- **Resolved citation links** — still the headline inheritance: S2ORC ties bibliography entries to inline mentions, feeding `CitationMention` directly.
- **SPECTER embeddings are paper-level and are used only for paper-level candidate narrowing.** The original plan wrongly proposed seeding claim-level dedup and target-claim alignment with them. Claim-level comparison requires a sentence/claim encoder, and confident equivalence or alignment requires a cross-encoder or entailment model on top ([data-model.md](data-model.md)).
- **Citation intent labels are weak supervision, not ground truth.** Their label set differs from InterCiter's function/stance ontology; using them requires an explicit mapping study ([evaluation.md](evaluation.md)).
- **Identifier mappings** (`corpusId`/DOI/PMID) → `PaperWork`. A DOI or PMID does **not** guarantee accessible full text; metadata, citation context, full text, and embeddings all have different coverage and licensing, tracked per `PaperVersion`.

### Domain slice, defined reproducibly

Ingest a domain slice, not the full corpus — but the slice must be **reproducible**: pinned corpus release version + explicit inclusion criteria, recorded so the corpus can be reconstructed and cited in the evaluation.

### Paper availability states

"Stub paper" was too coarse. Every paper the graph can reach carries an explicit availability state:

| State | Meaning |
|---|---|
| `full_text_extracted` | Parsed full text; claims extracted or extractable |
| `full_text_unavailable` | Known paper, no licensed/accessible full text |
| `metadata_stub` | Out-of-slice; identifiers + minimal metadata only |
| `hydration_queued` | Stub queued for on-demand full ingestion |
| `ingestion_failed` | Attempted and failed; error retained |

A stub is walkable *bibliographically* but provides no validated claim-level continuation, and the API says so rather than letting a paper-level hop masquerade as a claim-level one. On-demand hydration (user drills into a stub) gets caching, retry/backoff, rate-limit handling, and degraded states — it calls an external API on a user-facing path.

## Async execution and jobs

- **Internal:** message queue (SQS / RabbitMQ / Redis) with worker pull — required for bulk ingestion regardless.
- **External:** polling on a **job resource** for the MVP; webhooks on the same abstraction in phase 2. One paper can have many jobs over time (parse, extract, re-extract, hydrate), so jobs are first-class resources, not a single per-paper status field ([api.md](api.md)).

## Ingestion security

The pipeline processes untrusted documents and feeds them to LLMs. Minimum hardening, in-scope for the MVP:

- file-size limits and format validation before parsing;
- parser sandboxing and malware scanning;
- strict schema validation of all model output (an extraction that doesn't parse is rejected, not patched);
- prompt-injection defenses: paper text is data, never instructions — extraction prompts must be robust to instruction-like content embedded in papers.

## Auth

Unchanged: hybrid role-based (minimal — `reviewer`, `admin`) + ownership-based (per-user resources, own-authored interpretations). Ownership is modeled first-class from day one because retrofitting it is painful; the role layer stays minimal. Deferring public scoring ([scoring-and-review.md](scoring-and-review.md)) removes most identity/abuse surface from the MVP.
