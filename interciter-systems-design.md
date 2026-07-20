# InterCiter — Systems Design Overview

## Summary

InterCiter is a knowledge-graph system that extracts individual claims from scientific papers, traces those claims back to their original sources through citation chains, and classifies whether one source *mentions*, *supports*, or *dissents* from another. On top of this core it layers semantic search, citation-network visualization, trust weighting, and automated reference generation — all exposed through a single API.

The design philosophy throughout is **provenance-first and additive**: the system never destroys information. LLM output, human corrections, automated merges, and user opinions all coexist as distinct, traceable layers rather than overwriting one another. This makes the system auditable, lets multiple extraction models be compared on identical inputs, and produces a clean narrative for a grant proposal: the project builds on established infrastructure (BioLink, RoboKop, Semantic Scholar) rather than re-solving problems others have already solved.

---

## Design Principles

1. **Build smallest to largest.** A tight MVP proves the core loop; visualization, trust weighting, reference generation, and the review queue are phase-2 layers on the same foundation.
2. **Piggyback on existing infrastructure.** Extend BioLink's schema and RoboKop's plumbing rather than designing a parallel ontology; use Semantic Scholar as the paper and citation-graph substrate rather than building ingestion from scratch.
3. **Provenance-first / additive-only.** Every human or automated action creates new, traceable records. Edits supersede rather than overwrite; merges are reversible overlays; scores are separate entities.
4. **LLM as starting point, not source of truth.** Multiple models are swappable and their outputs stored separately, with human review as a correction mechanism rather than a gate.
5. **API-first.** Every feature — including InterCiter's own future frontends — routes through the API. Nothing assumes a specific frontend.
6. **Minimal storage footprint.** Ingest domain slices rather than entire corpora; inherit precomputed artifacts (embeddings, resolved citations) instead of regenerating them.

---

## Architecture — Three Layers

The system divides cleanly into three layers, which maps onto both the "smallest to largest" build order and the grant narrative.

### 1. Ingestion / Extraction Layer
Paper → claims. Stateless and pluggable so extraction models can be swapped without touching storage. This is where multi-LLM support and human-review hooks live.

### 2. Knowledge Graph Layer
Claims + relationships + provenance, built as an **extension of BioLink's schema** rather than a parallel ontology. This is where piggybacking saves the most: inherited entity types, relationship semantics, and existing RoboKop provenance infrastructure.

### 3. Access Layer
API plus everything built on it — semantic search, visualization, reference generation. Frontend-agnostic; visualization endpoints return data (nodes + edges), not rendered images.

---

## Data Model

### Core entity: the Claim (standalone node)

Claims are **standalone nodes**, not edges between papers. This is the more flexible choice — a claim can accumulate many relationships over time (to other claims, to its source paper, later to human annotations) without restructuring, and it supports the multi-hop citation-chain use case. It costs one extra hop per query, which is an acceptable tradeoff.

**Claim node fields:**

| Field | Purpose |
|---|---|
| `claim_id` | Unique identifier |
| `text` | The extracted / normalized claim statement |
| `source_paper_id` | Which paper it came from |
| `extraction_method` | Which LLM, or `"human"` |
| `extractor_version` / `model_id` | Enables comparing models (or a human) on the same paper |
| `confidence_score` | Extraction-time confidence |
| `global_confidence` | System-computed, read-only (see Scoring) |
| `human_reviewed` (bool) + `reviewer_id` + `review_timestamp` | Review provenance |
| `human_edit_of` | Pointer to the original LLM claim, if a human modified it — preserves provenance instead of overwriting |

### Relationship edges (Claim → Claim)

| Field | Purpose |
|---|---|
| `relationship_type` | `mention` / `support` / `dissent` |
| `source_claim_id` → `target_claim_id` | Direction of the relationship |
| `relationship_extraction_method` | Same LLM / human / model tracking as claims |
| `relationship_confidence` | Confidence in the classification |

### Graph shape

```
Paper --[has_claim]--> Claim --[supports/dissents/mentions]--> Claim
                         |
                         --[extracted_by]--> Model/Human
                         --[part_of]--> Paper (source)
```

Traversal for the citation-chain use case: start at a claim, walk `supports`/`dissents` edges outward, and at each hop pull in the source paper's trust weight to influence ranking or display.

### Paper node
Holds the trust-weight field plus standard metadata (authors, institution, venue, year). Kept close to unmodified **BioLink `Publication`**, which also aligns with Semantic Scholar's paper metadata and its `corpusId`/DOI/PMID identifier mappings.

---

## Mapping onto BioLink

BioLink already provides the structural pattern InterCiter needs:

- **Claim** → a subtype of BioLink `InformationContentEntity`.
- **Support / dissent / mention relationships** → a custom `Association` subclass with a predicate from a small controlled vocabulary. BioLink lacks "supports"/"dissents" out of the box, but its predicate-extension pattern is built for exactly this.
- **Provenance / LLM-tracking fields** → BioLink's existing `knowledge_source`, `primary_knowledge_source`, and `aggregator_knowledge_source` slots. RoboKop likely already has plumbing for provenance display here.
- **Paper** → BioLink `Publication`, largely unmodified.

---

## Scoring

Two distinct signals, deliberately kept separate so users never see them silently blended:

### Global confidence (system-computed, read-only)
A function of extraction confidence, human-review status, and corroboration — how many independent extractions or papers land on the same claim. Corroboration is where dedup and confidence intersect: if two claims are detectably "the same," the fact that they were extracted independently is itself evidence that boosts confidence. Dedup is therefore not just cleanup — it is a confidence signal.

### User scores (writable, separate entity)

```
UserScore --[scores]--> Claim (or Paper)
  - user_id
  - score_value
  - scope: private | public
  - created_at
```

Keeps the claim/paper's own data untouched by opinion. Public `UserScore`s can feed a separate aggregate ("community score") that stays distinct from system-computed global confidence.

Paper **trust weight** is the same underlying pattern applied at the paper level, and it feeds back into search ranking — a highly trusted paper supporting a claim boosts that claim's prominence in results. Trust and evidence quality thus shape discoverability, not just display.

---

## Deduplication

**Fully automated, with human overrides.** Keeps the pipeline from stalling on human review at merge time while still allowing reviewers to split a bad merge later.

- **First pass:** semantic similarity (embedding distance) between claim texts flags merge candidates. Semantic Scholar's precomputed SPECTER embeddings can seed this.
- **Merge as a reversible overlay**, never a destructive operation:

```
MergeEvent
  - merge_id
  - merged_claim_ids       (the originals)
  - resulting_claim_id
  - method: automated | human
  - confidence             (the similarity score that triggered it)
  - status: active | reverted
  - reverted_by / reverted_at
```

Reverting flips `status` and restores the original claim nodes rather than reconstructing them. This is precisely why fully-automated dedup is safe: the merge is always an overlay on top of preserved originals.

---

## Human-Review Workflow

Every human action is **additive, never destructive.**

| Operation | Behavior |
|---|---|
| **Claim edit** | Creates a new node with `human_edit_of` pointing to the original; original stays, flagged superseded. Enables model-vs-human comparison over time. |
| **Claim creation** | New node, `extraction_method = "human"`, no `human_edit_of`. |
| **Merge override** | Flip a `MergeEvent` to `reverted`; originals restored. |
| **Score override** | Just a `UserScore` from a user whose `user_id` carries reviewer privileges — no separate plumbing. |

### Review queue — *phase 2, low priority*
An explicit prioritization layer (e.g. lowest-confidence claims first, or high-trust papers first, or most-contested claims first). Deliberately deferred. Because global confidence and trust weight are already stored and queryable, the queue is essentially just a query over existing data — so the cost of leaving room for it now is effectively zero, and no schema changes are needed to add it later. The only open question (deferred) is the ranking policy that drives priority.

---

## Semantic Scholar Integration

Semantic Scholar becomes the **paper + citation-graph substrate**; InterCiter's novel layer (claim-level extraction, the support/dissent ontology, per-model provenance, trust weighting) sits on top. This turns ingestion from a *build* problem into an *integration* problem and reinforces the "standing on existing infrastructure" theme.

Delivered via the Datasets API as monthly gzipped JSON snapshots. Directly useful components:

- **Citations with intent/context** — Semantic Scholar already classifies citations. Not identical to the mention/support/dissent ontology, but provides a labeled corpus to bootstrap and *evaluate* the classifier against — a concrete evaluation story for the proposal.
- **Resolved citation links** — S2ORC resolves bibliographic references and ties citation links back to inline mentions in full text. InterCiter inherits the citation graph instead of parsing bibliographies, directly enabling the "trace claims through citation chains" loop.
- **SPECTER embeddings** — precomputed paper-level embeddings that seed both phase-2 semantic search and dedup candidate detection, saving compute and storage.
- **TLDRs** — *caveat:* limited to computer-science and biomedical domains. Useful but not load-bearing, given the domain-agnostic goal.
- **Identifier mappings** — `corpusId`/DOI/PMID give clean external identifiers for Paper nodes and reinforce keeping Paper close to unmodified BioLink `Publication`.

**Storage strategy:** load full snapshots for bulk backfill; use incremental release diffs to stay current. Ingest a domain slice rather than all 80M+ papers to keep the footprint controllable.

---

## API Surface

Organized by resource in build order. The first three groups are MVP-critical; the rest are phase-2 layers on the same foundation. Versioned from day one (`/v1/`).

### Ingestion (MVP)
- `POST /papers` — submit a paper (PDF/XML or DOI/PMID); kicks off async extraction, returns a job handle.
- `GET /papers/{id}/status` — poll async ingestion status.
- `GET /papers/{id}` — paper metadata + trust weight.

### Claims (MVP — core)
- `GET /claims/{id}` — text, source paper, extraction provenance, global confidence.
- `GET /papers/{id}/claims` — all claims for a paper.
- `GET /claims/{id}/relationships` — support/dissent/mention edges, with a `depth` parameter for walking citation chains. **The core "trace it back" endpoint.**
- `POST /claims` — create a claim manually (human-authored path).
- `PATCH /claims/{id}` — edit; creates the superseded-pointer node rather than overwriting.

### Provenance & extraction control (MVP — surfaces multi-LLM design)
- `POST /papers/{id}/extractions` — re-extract with a specific model (run Claude vs GPT vs another on the same paper, stored separately).
- `GET /papers/{id}/extractions` — see each model's output side by side.

### Scoring
- `GET /claims/{id}/scores` — system global confidence + aggregate public community score, as distinct signals.
- `POST /claims/{id}/scores` — submit a user score with `scope: public | private`.
- `PUT /papers/{id}/trust-weight` — set the user-supplied reliability weight that feeds ranking.

### Dedup / merges
- `GET /merges/{id}` — inspect a merge event.
- `POST /merges/{id}/revert` — the human override that splits a bad automated merge.

### Search (phase 2)
- `POST /search` — natural-language semantic query; ranking incorporates trust weight and confidence (the feedback loop). `POST` to accommodate complex filters (field, date, confidence threshold).

### Reference generation (phase 2)
- `POST /references` — takes draft text, returns relevant claims/papers formatted as citations.

### Visualization (phase 2 — returns *data*, not images)
- `GET /networks` — parameterized by granularity (author / institution / field / topic) and a root entity; returns nodes + edges. Rendering lives in the frontend.

---

## Cross-Cutting Concerns

### Async execution & notification
Separate *how work gets done internally* from *how the caller finds out*:

- **Internal execution:** a message queue (SQS / RabbitMQ / Redis) with worker pull — needed regardless, especially for bulk Semantic Scholar ingestion.
- **External notification (MVP):** **polling** on a `job_id`. Simplest to build, works with any client, forecloses nothing.
- **External notification (phase 2):** **webhooks** on the same `job_id` abstraction, added once there are programmatic partners. SSE is an option for progress-bar UIs but holds a connection, so it's not the default.

Polling and webhooks coexist on one `job_id` abstraction, so committing to polling now costs nothing later.

### Auth granularity
A **hybrid** of role-based and ownership-based checks, which is standard and appropriate here:

- **Role-based (coarse):** operational privileges cluster cleanly into roles. For the MVP this is minimal — essentially `reviewer` vs not (revert merges, supersede claims), plus `admin`.
- **Ownership / resource-scoped (fine):** public/private user scores are inherently per-user, per-resource — "I can see my own private scores, not yours" is not a role, it's ownership. Same for editing one's own authored claims.

**Decision to make now:** model *ownership* as a first-class concept on scores and human-authored claims from the start. Retrofitting per-resource ownership onto a pure-role system later is painful; the role layer itself can stay minimal for the MVP.

---

## MVP vs Phase 2 — At a Glance

**MVP (the core loop):**
1. Ingest a paper (via Semantic Scholar substrate + PDF/XML fallback).
2. Extract claims via a swappable LLM, tagged with source model + confidence.
3. Identify the citations each claim references (inheriting S2 resolved links).
4. Classify each citation relationship (mention / support / dissent).
5. Store claims + relationships + provenance in a BioLink-aligned graph.
6. Query: "show me what this paper claims and what it's built on."

Plus the supporting foundations: standalone claim nodes, global confidence + user scores, automated dedup via reversible MergeEvents, on-demand human review, polling-based async, minimal role + ownership auth.

**Phase 2 (layers on the same foundation):**
Semantic search · reference generation · citation-network visualization · prioritized review queue · webhook notifications · richer ranking policies.
