# InterCiter — API Surface

Versioned from day one (`/v1/`). API-first: every feature, including InterCiter's own frontends, routes through it. Resources are immutable-by-default, matching the system of record; the default read representations are the **composed, reader-friendly views** described in [architecture.md](architecture.md), with the full audit structure behind explicit evidence endpoints.

## Ingestion, jobs, and runs (MVP)

One paper accumulates many jobs over time (parse, extract, re-extract, hydrate), so jobs and runs are first-class resources rather than a single `GET /papers/{id}/status`.

- `POST /v1/papers` — submit by DOI/PMID or open-access XML. Returns `202 Accepted` + a job resource. Supports an **idempotency key** so retries don't double-ingest.
- `GET /v1/papers` — list ingested papers (metadata + availability state), bounded by `limit`/`offset`. The reader UI's entry list; reads stay open.
- `GET /v1/jobs/{job_id}` — poll any async work (MVP notification model; webhooks on the same abstraction in phase 2).
- `GET /v1/papers/{paper_id}` — work-level metadata + **availability state** (`full_text_extracted` … `ingestion_failed`, see architecture.md). Also carries the additive integrity flags `is_retracted` / `integrity_notice` (both `null` until an integrity source is consulted; populated by the Crossref-backed `integrity-check` enrichment — scite WP5).
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

## Citation statistics — how a work/claim has been cited

A derived, non-mutating roll-up of the `RelationAssertion`s that *point at* a subject. Unlike scite's single supporting/contrasting/mentioning label, InterCiter keeps **function and stance as separate dimensions** and counts **abstention explicitly** (a relation that commits to neither) rather than folding it into "mentioning". Each response carries per-dimension tallies (`by_stance`, `by_function`, `by_resolution`, `by_section`) plus the underlying citing statements, each with its citing work, section facet, and evidence span.

- `GET /v1/papers/{work_id}/citation-stats` — every relation that cites the work, whether paper-level (`cited_work_id`) or claim-level (resolved to a claim in the work).
- `GET /v1/claims/{interpretation_id}/citation-stats` — every relation that resolved to that specific claim interpretation.

## Reports — per-paper citation dashboard

Scite-style report payload for one paper (scite F4), built as a derived, non-mutating
view on top of citation stats (WP1). The endpoint supports filtering the statement
list and recomputed tallies by section/function/stance/resolution/year while keeping
function and stance separate and abstention explicit.

- `GET /v1/papers/{work_id}/report` — query params `section`, `function`, `stance`,
  `resolution`, `min_year`, `max_year`. Returns `{work_id, total_statements,
  filtered_statements, facets, applied_filters, tallies, timeline,
  conflict_summary, statements[]}` where:
  - `timeline` is grouped by citing-work publication year (statement and unique-work
    counts),
  - `conflict_summary` highlights supporting vs contradicting mix and whether both
    are present,
  - `statements` are citation-stat rows with evidence spans.

## Search — full-text claim search

Search *inside* citation statements, not just titles and abstracts (scite F3). A derived, non-mutating read: a keyword is matched case-insensitively against both the normalized claim text **and** the verbatim source passage, and the unit returned is the current interpretation **head** of a claim occurrence. Function, stance, and resolution stay **separate** facet dimensions; every hit keeps its evidence span. Reads stay open (no auth).

- `GET /v1/search/claims` — query params `q` (keyword), `section`, `function`, `stance`, `resolution`, `min_year`, `max_year`, `limit` (1–100, default 25), `offset`. Returns `{query, total, limit, offset, hits[], facets}`. Each hit carries `claim_id`, `normalized_text`, `work_id`, `paper_title`, `year`, `section`, `function[]`, `stance[]`, `resolution[]`, and an `evidence` ref. `facets` gives counts per section/function/stance/resolution over the text/year-matched set (before the categorical facets are applied), so every narrowing option a query allows stays visible. A `function`/`stance`/`resolution` filter matches a claim with *at least one* relation of that value.

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
- `GET /v1/claims/{id}/clusters` — the clusters a claim belongs to, so clustering is reachable and reviewable from a claim (there is otherwise no discovery path to a cluster id).
- `DELETE /v1/clusters/{cluster_id}/members/{interpretation_id}` — reviewer removes a bad membership (sets `status: removed`; nothing is destroyed).
- `POST /v1/review-decisions` — per-dimension review of an occurrence / interpretation / assertion / membership, with rationale.

## Network graph — papers, authors, citations, claims (MVP)

A derived, read-side projection (like the claim views): the immutable record is flattened into a generic node/edge envelope so the same shape serves the citation network today and a ROBOKOP claim graph later. Nodes carry an open `type` discriminator (`paper`, `author`, `claim`, …); edges are directed with a `type` (`cites`, `authored`, `relates`). `cites` edges union two sources — passage-grounded `CitationMention`s (full-text corpus) and bibliographic `CitationEdge`s (which can point at metadata-only stubs). Every view is bounded and reports `truncated` when a cap is hit.

Paper nodes also carry derived quantitative measures in `node.data` for client-side mapping (Litmaps-style `year × citations`): `year`, `cited_by_count` (global in-degree — how many distinct works cite it), and `references_count` (global out-degree). Degrees are computed over the whole citation network, so they are stable regardless of how the view is windowed.

- `GET /v1/graph/papers` — a bounded overview of the citation network (`limit`, `include_authors`). Reads stay open.
- `GET /v1/graph/papers/{work_id}` — the citation neighborhood centered on one paper, BFS to `depth` hops (both directions), `include_authors` optional.
- `POST /v1/graph/papers/{work_id}/expand` — grow the graph on demand from **Semantic Scholar**: pulls the paper's references, creates any missing cited works as metadata-only stubs, and persists each as a `semantic_scholar` `CitationEdge` (idempotent — re-expanding never duplicates). A write, so it requires an authenticated principal (+ CSRF for cookie auth). Returns counts plus the refreshed neighborhood.
- `GET /v1/graph/claims` — the in-corpus claim-relationship network (nodes are interpretations; edges are `claim_resolved` `RelationAssertion`s carrying function/stance).
- `POST /v1/graph/claims/{interpretation_id}/expand-robokop` — explore a claim in the **ROBOKOP knowledge graph**: grounds the claim's entity qualifiers (or explicit `terms` in the body) to canonical CURIEs, then draws the background-knowledge edges between them with `primary_knowledge_source` / `aggregator_knowledge_source` provenance. A write (persists additive `EntityGrounding` side rows; KG edges are derived context and are not stored), so it requires an authenticated principal (+ CSRF for cookie auth). Corroborating context, never a truth oracle that overrides a source-grounded extraction.

## Discovery — seed-based related work

Litmaps-style "dive deeper": given one or more seed works, rank the papers most connected to them by **co-reference degree** (how many seeds cite the same paper). Discovery reads the seeds' references from **Semantic Scholar** — a network call — so it is auth-gated like graph expansion, but it **persists nothing**: candidates are suggestions. In-corpus candidates carry a `work_id` for deep-linking; the rest carry a Semantic Scholar `external_id` a user could ingest.

- `POST /v1/discovery/seeds` — body `{seed_work_ids, limit?, min_year?}`. Returns ranked `candidates` (title, year, `connection_score`, `supporting_seed_ids`, `is_influential`, `in_corpus`) plus `seeds_resolved` / `skipped_seed_ids`. Requires an authenticated principal (+ CSRF for cookie auth); `404` if a seed work id is unknown, `502` on a Semantic Scholar error.

## Collections — curated user-owned sets of works

Scite-style collections (F5): persist named sets of papers and batch-add members by
internal work id, DOI/PMID arrays, or pasted CSV/plain-text identifiers. Collections
are additive and non-mutating: they only store membership rows and can register
metadata stubs for unknown identifiers through the existing ingest path.

- `POST /v1/collections` — create a collection (`{name, description?}`).
- `GET /v1/collections` — list the caller's collections.
- `GET /v1/collections/{id}` — collection detail with member list. Optional query
  `include_member_tallies=true` adds each member's WP1 citation tallies inline and
  `aggregate_citation_tallies` for the whole collection. Optional `member_sort`:
  `added_desc` (default), `added_asc`, `support_desc`, `contradict_desc`
  (unknown values are rejected with `422`). Each member also carries additive
  integrity flags `is_retracted` and `integrity_notice` (both `null` until an
  integrity source has been consulted — scite WP5 starter).
- `PATCH /v1/collections/{id}` — update `{name?, description?}`. An explicitly
  `null` description clears the stored value; an omitted field is left unchanged.
- `DELETE /v1/collections/{id}` — delete a collection (and memberships).
- `POST /v1/collections/{id}/members` — batch add members (`{work_ids[], dois[],
  pmids[], csv_text?}`) and returns `{added_count, skipped_identifiers,
  created_stub_work_ids, members[]}` where `created_stub_work_ids` are works that
  were registered as metadata stubs during identifier ingestion. Identifier
  handling: DOIs are canonicalized to lowercase and may be given as bare DOIs,
  `doi:`-prefixed, or doi.org / dx.doi.org URLs; pasted `csv_text` is split on
  whitespace and commas only (semicolons occur inside legacy Wiley/SICI DOIs);
  PMIDs may be `pmid:`-prefixed, and bare 4-digit numbers in the
  publication-year range are treated as ambiguous and reported in
  `skipped_identifiers` rather than imported. Batches are capped at 500
  identifiers per request (`400` beyond that). Stub registration commits per
  identifier; membership rows are written in a single transaction at the end.
- `DELETE /v1/collections/{id}/members/{work_id}` — remove one member.
- `POST /v1/collections/{id}/members/bulk-delete` — remove several members at once
  (`{work_ids[]}`, 1–500 ids; `422` on an empty list). Unknown work ids are
  ignored; returns `{removed_count, removed_work_ids[]}`. The UI wires this to a
  filter-aware "remove filtered members" action behind a confirmation.
- `POST /v1/collections/{id}/watch` — toggle monitoring (`{watch: bool}`, scite
  WP4→WP8 bridge). Enabling (or re-enabling) captures a per-member
  support/contradict baseline snapshot and stamps `watch_snapshot_at`. State only —
  no delivery channel yet. Returns the updated `CollectionView` (`is_watched`,
  `watch_snapshot_at`).
- `GET /v1/collections/{id}/new-citations` — derived read comparing current member
  support/contradict tallies against the last watch snapshot. Returns
  `{has_snapshot, snapshot_at, new_support_total, new_contradict_total, members[]}`
  where each member row lists only newly observed `new_support` / `new_contradict`
  signals (clamped at zero; members added after the snapshot contribute their full
  counts). Re-enabling the watch re-baselines and clears the delta.

All collection endpoints are auth-scoped to the caller's own resources; a
collection owned by another user is indistinguishable from a missing one (`404`).
Writes require CSRF when using cookie auth.

## Saved maps — persisted citation-map seed sets + layout

Litmaps-style saved maps (WP-L2): a named seed set of works plus the visualization
`layout_config` (layout mode, axis/size measures, author toggle, center work) used to
render it. Additive and non-mutating — maps only store membership rows and UI state.
Members carry an optional `note` (per-node annotation) and `position` (pinned `{x, y}`).
All map endpoints are owner-scoped; a map owned by another user is reported as missing
(`404`). Writes require CSRF when using cookie auth.

- `POST /v1/maps` — create a map (`{name, description?, layout_config?, work_ids?}`);
  an optional `work_ids` seed set is populated from existing works. Returns the detail
  view (with members).
- `GET /v1/maps` — list the caller's maps.
- `GET /v1/maps/{id}` — map detail with members.
- `GET /v1/maps/{id}/graph` — render the map's seed set as a citation `GraphView`
  (nodes = the surviving members, `cites` edges between them, with node-degree
  measures). `include_authors` optional.
- `PATCH /v1/maps/{id}` — update `name` / `description` / `layout_config`.
- `DELETE /v1/maps/{id}` — delete the map (cascades memberships).
- `POST /v1/maps/{id}/members` — add existing works (`{work_ids}`), idempotent.
- `DELETE /v1/maps/{id}/members/{work_id}` — remove a member (`404` if not a member).
- `PATCH /v1/maps/{id}/members/{work_id}` — annotate a member (`{note?, position?}`).

## Monitoring — saved searches & alerts

Persist claim searches and turn watched collections + saved searches into an in-app
alert feed (scite-parity WP8, F3/F5). No email/SMTP yet — delivery is in-app only.
All endpoints are auth-scoped to the caller; another user's records are `404`.

- `POST /v1/saved-searches` — create (`{name, query:{q?, section?, function?, stance?,
  resolution?, min_year?, max_year?}}`). Creation seeds a baseline of the current
  matching claims so the first run only surfaces claims added afterwards.
- `GET /v1/saved-searches` / `GET /v1/saved-searches/{id}` — list / fetch.
- `PATCH /v1/saved-searches/{id}` — update `{name?, query?}` (changing the query
  re-baselines).
- `DELETE /v1/saved-searches/{id}` — delete.
- `POST /v1/saved-searches/{id}/run` — re-run one search, diff against last-seen,
  emit `new_claim` alerts, and advance the baseline. Returns
  `{created_count, alerts[]}`.
- `POST /v1/alerts/run` — run every saved search **and** watched collection the
  caller owns. Collections emit `new_support` / `new_contradict` (vs the watch
  snapshot) and `retraction` (a member newly flagged retracted) alerts, then
  re-baseline. Returns `{created_count, alerts[]}`.
- `GET /v1/alerts` — the alert feed, newest first; `?unread_only=true` filters.
- `POST /v1/alerts/{id}/read` — mark one read. `POST /v1/alerts/read-all` — mark all
  read (`{marked_read}`).

Each `AlertView` carries `{alert_type, source_type, source_id, work_id?, claim_id?,
summary, is_read, created_at}`. Baselines advance whenever a check runs, so the same
signal is never alerted twice.


## Identity, sessions, and accounts (MVP)

Every request resolves to a `Principal` from **either** an `Authorization: Bearer <token>` header (API/CLI clients) **or** a browser session cookie. Reads stay open; only writes require a principal, and some require `reviewer`/`admin` or ownership. The raw token is stored only as a SHA-256 hash.

**Sessions (Backend-for-Frontend).** So the browser never holds the raw token ([ui-design.md](ui-design.md) §11), the SPA exchanges it once for a server-side session:

- `POST /v1/auth/login` — body `{api_token}`; sets an `HttpOnly; Secure; SameSite=Strict` session cookie plus a readable CSRF cookie; returns the CSRF token + expiry.
- `POST /v1/auth/logout` — revokes the server-side session and clears cookies.
- `GET /v1/auth/csrf` — returns the current session's CSRF token (lets the SPA recover it after a reload).

Unsafe cookie-authenticated methods require a matching `X-CSRF-Token` header (double-submit). Bearer-authenticated requests need no CSRF (no ambient credential to forge). Sessions carry sliding-idle and absolute-lifetime timeouts (NIST SP 800-63B).

**Accounts.** Manual account management for the MVP (all admin-only except `me`):

- `GET /v1/users/me` — the identity/role the server resolved for the caller.
- `GET /v1/users` — list accounts (id, name, role, active state).
- `POST /v1/users` — create a user; the raw token is returned **exactly once**.
- `PATCH /v1/users/{id}` — change role and/or activation. Deactivation revokes the user's sessions; a guard refuses to remove the last active admin (`409`).
- `POST /v1/users/{id}/rotate-token` — issue a fresh token (old token + sessions invalidated); returned once.

Long-term, token-paste is replaced by agency SSO / login.gov (OIDC + PIV/CAC) behind the same session boundary.

## Scores

- `GET /v1/claims/{id}/scores` — the decomposed signal set ([scoring-and-review.md](scoring-and-review.md)) as separate named components with `Assessment` provenance. No blended scalar.
- User scores and paper trust endpoints — **phase 2**, retaining the overlay pattern (`POST` adds one user's entry; aggregates are computed and read-only).

## Phase 2

- `POST /v1/search` — semantic query; ranking inputs are explicit, component-level, and documented.
- `POST /v1/references` — draft text → relevant claims/papers as citations (depends on validated high-precision retrieval).
- `GET /v1/networks` — visualization data (nodes + edges) by granularity; rendering is the frontend's job.
- Webhooks on the existing job abstraction.
