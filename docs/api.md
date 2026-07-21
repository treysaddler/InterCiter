# InterCiter — API Surface

Versioned from day one (`/v1/`). API-first: every feature, including InterCiter's own frontends, routes through it. Resources are immutable-by-default, matching the system of record; the default read representations are the **composed, reader-friendly views** described in [architecture.md](architecture.md), with the full audit structure behind explicit evidence endpoints.

## Ingestion, jobs, and runs (MVP)

One paper accumulates many jobs over time (parse, extract, re-extract, hydrate), so jobs and runs are first-class resources rather than a single `GET /papers/{id}/status`.

- `POST /v1/papers` — submit by DOI/PMID or open-access XML. Returns `202 Accepted` + a job resource. Supports an **idempotency key** so retries don't double-ingest.
- `GET /v1/jobs/{job_id}` — poll any async work (MVP notification model; webhooks on the same abstraction in phase 2).
- `GET /v1/papers/{paper_id}` — work-level metadata + **availability state** (`full_text_extracted` … `ingestion_failed`, see architecture.md).
- `GET /v1/papers/{paper_id}/versions` — the paper's `PaperVersion`s (preprint vs published vs correction).
- `GET /v1/extraction-runs/{run_id}` — full run provenance (model, prompt version, parameters, code revision).
- `POST /v1/papers/{paper_id}/extractions` — trigger a re-extraction with a specified model (evaluation workflows; not a production multi-model feature in MVP).

## Claims and evidence (MVP — core)

- `GET /v1/claims/{id}` — the composed default view: normalized text, source snippet, paper, provenance link, per-component scores. ("Claim" here is the projected read-side object; the audit trail sits behind it.)
- `GET /v1/papers/{id}/claims` — claims for a paper.
- `GET /v1/claim-occurrences/{id}` — exact span, passage, extraction run.
- `GET /v1/claim-interpretations/{id}` — normalized proposition, qualifiers, revision parents.
- `GET /v1/passages/{id}` — verbatim source text + locators.
- `POST /v1/claims` — human-authored claim (creates occurrence + interpretation as appropriate).

Every claim and relation response **embeds or links its evidence**. There is no representation of a claim that can't be traced to a passage in one request.

## Revisions (MVP)

Revising is creating, so it's a `POST`, not a `PATCH`:

- `POST /v1/claim-interpretations/{id}/revisions` — creates a new interpretation with the old as parent. The response identifies both versions **and lists any `RelationAssertion`s that became `stale_pending_review`**. Restricted to the original author or `reviewer`/`admin`.

## Relations and traversal (MVP: one hop)

- `GET /v1/relation-assertions/{id}` — the full evidence-bearing record: function, stance, scope, resolution, both scores, stance distribution, evidence passage, run, review state.
- `GET /v1/claims/{id}/relationships` — one-hop relations for a claim, filterable by stance/function/resolution/status.

Deep traversal (phase 2) is **bounded, never free-depth** — a bare `depth` parameter invites explosive queries and hides uncertainty:

```text
GET /v1/traces
  ?root_claim_id=...
  &max_depth=2          (required)
  &max_nodes=100        (required)
  &min_target_link_score=...
  &min_stance_score=...
  &include_unresolved=true
  &cursor=...
```

The response reports cycles, truncated branches, evidence for every hop, and separate confidence components per hop — and it **never presents a `paper_resolved` hop as a claim-level continuation**.

## Clusters and review (MVP)

- `GET /v1/clusters/{id}` — memberships with method + confidence; conflicting stances within a cluster surfaced explicitly.
- `DELETE /v1/clusters/{cluster_id}/members/{interpretation_id}` — reviewer removes a bad membership (sets `status: removed`; nothing is destroyed).
- `POST /v1/review-decisions` — per-dimension review of an occurrence / interpretation / assertion / membership, with rationale.

## Scores

- `GET /v1/claims/{id}/scores` — the decomposed signal set ([scoring-and-review.md](scoring-and-review.md)) as separate named components with `Assessment` provenance. No blended scalar.
- User scores and paper trust endpoints — **phase 2**, retaining the overlay pattern (`POST` adds one user's entry; aggregates are computed and read-only).

## Phase 2

- `POST /v1/search` — semantic query; ranking inputs are explicit, component-level, and documented.
- `POST /v1/references` — draft text → relevant claims/papers as citations (depends on validated high-precision retrieval).
- `GET /v1/networks` — visualization data (nodes + edges) by granularity; rendering is the frontend's job.
- Webhooks on the existing job abstraction.
