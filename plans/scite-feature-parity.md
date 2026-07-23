# Scite Feature-Parity Plan

Status: DRAFT — planning artifact for subagent execution
Source: https://scite.ai/features (captured 2026-07-21)
Owner: (assign)

This document (1) catalogs the scite.ai features we want to replicate, (2) maps
each to InterCiter's existing capabilities, and (3) breaks the gap into discrete,
subagent-ready work packages (WPs). Each WP is scoped to be handed to an
independent subagent with minimal cross-dependencies.

InterCiter's differentiators we must preserve while replicating scite:
- Provenance-first: every assertion traces to a verbatim span (char offsets).
- Decomposed scores, NO blended scalar; explicit abstention / unresolved state.
- Function and stance are SEPARATE dimensions (not scite's single 3-way label).
- LinkML-first schema changes (edit `schema/interciter.yaml`, regenerate).
- Reads open; writes require auth + CSRF. USWDS / Section-508 UI.

---

## 0. Cross-plan status snapshot (all parity plans · updated 2026-07-23)

Three parity plans (`scite`, `litmaps`, `bibliometrix`) share one codebase; check
all three before starting a WP so shared work is built once.

Shipped to origin/main:
- scite: WP1 citation tallies · WP2 claim search · WP3 paper report · WP4
  collections (+ watch / delta / integrity / bulk) · WP5 retraction+integrity
  signal · WP8 saved searches + alerts.
- litmaps: WP-L1 discovery · WP-L2 saved maps · WP-L3a/b/c D3 renderer + axis
  layouts + annotations · WP-L4 read-only map sharing.
- bibliometrix: none yet (plan drafted 2026-07-23).

Not yet built:
- scite: WP6 grounded Assistant (RAG QA) · WP7 Reference Check · WP9
  Zotero/Mendeley import.
- litmaps: WP-L5 map monitoring (extends scite WP8 — now unblocked) · WP-L6
  Zotero seed import (extends scite WP9).
- bibliometrix: WP-B1 … WP-B10 (all).

Build-once shared WPs (one implementation serves several plans):
- Import connectors — scite WP9 ⊇ litmaps WP-L6 ⊇ bibliometrix WP-B6. One
  RIS/BibTeX/CSV (+ later OpenAlex/WoS/Scopus) importer targeting Collections,
  Maps, and Corpora.
- Alerts / monitoring — scite WP8 (DONE) ⊇ litmaps WP-L5 (add a "map" source).
  One subsystem, never two.
- Grounded LLM — scite WP6 ⊇ bibliometrix WP-B10 (Biblio-AI narration).
- Graph rendering — the litmaps WP-L3 D3 `NetworkGraph` is the ONE renderer;
  bibliometrix WP-B3/B5/B7 reuse it (no second graph library).
- Saved-set membership — scite `Collection`, litmaps `Map`, bibliometrix `Corpus`
  are siblings; unify the membership base before adding the third (open question
  in every plan).

Recommended next steps (highest cross-plan leverage first):
1. scite WP9 import connectors — self-contained file parsing (no network) that
   simultaneously unblocks litmaps WP-L6 and bibliometrix WP-B6.
2. litmaps WP-L5 map monitoring — small; every dependency (WP-L1/L2/WP8) is
   shipped; completes the litmaps monitoring story.
3. bibliometrix WP-B1 corpus descriptive analytics — opens the science-mapping
   surface with no schema/NLP/deps; foundation for WP-B2…B10.
4. scite WP6 grounded Assistant — high value; WP2 retrieval + LLM client already
   exist; later extended by bibliometrix WP-B10.

---

## 1. Feature catalog & gap analysis

Legend: ✅ have · 🟡 partial · ⬜ missing

### F1. Smart Citations (classify how a paper is cited)
scite: deep-learning model classifies each citation statement as supporting /
contrasting / mentioning, with the citing text, a classification, and the
section where the citation occurred.

InterCiter mapping:
- ✅ Citation statements w/ verbatim text + char offsets (ClaimOccurrence / passages).
- ✅ Classification richer than scite: RelationAssertion has `function`
  (direct_evidence/…) AND `stance` (support/contrast/neutral) as separate tags,
  plus resolution state + decomposed scores. Stub extractor is deterministic;
  LLMExtractor exists for real classification.
- 🟡 Section label: parser captures nearest `<title>`; not surfaced as a
  first-class "citation section" facet on the citing statement everywhere.
- ⬜ Aggregate per-target roll-up counts (supporting/contrasting/mentioning tallies).

Gap: surface section as a facet; add aggregate stance/function tallies per cited
work / per claim (drives F4 Reports).

### F2. Assistant (evidence-grounded research Q&A)
scite: AI answers drawn only from indexed literature, every answer linked to
source. Used for lit review, fact-checking, discovery.

InterCiter mapping:
- 🟡 LLM plumbing exists (`ingestion/llm_client.py`, model/endpoint-agnostic:
  NIEHS LiteLLM proxy + Biowulf vLLM, batch replay, ssl/retry). No RAG/Q&A layer.
- ✅ Retrieval substrate: claims, occurrences, embeddings (SPECTER2 sidecar),
  graph, grounding.
- ⬜ Retrieval-augmented Q&A endpoint + citation-linked answer objects.
- ⬜ UI chat surface with inline source cards linking to claim/paper detail.

Gap: build a grounded QA service that retrieves InterCiter claims/passages and
returns answers with mandatory verbatim citations + abstention when unsupported.

### F3. Search inside citation statements (full-text claim search)
scite: match on citation statements extracted from full text (not just
title/abstract), citation chaining, filter by section/type/journal, alerts.

InterCiter mapping:
- 🟡 `GET /v1/papers` list only; no full-text/claim search endpoint.
- ✅ Citation chaining substrate: graph neighborhood + CitationEdge + S2 expand.
- ⬜ Search over claim/occurrence verbatim text (keyword + optional embedding).
- ⬜ Faceted filters (section, function, stance, resolution, year, source type).
- ⬜ Saved searches / alerts.

Gap: add a search service + endpoint + UI; alerts are a later WP.

### F4. Reports (per-paper citation dashboard)
scite: quantitative + qualitative view of every citation a paper received;
filter by classification/section/year/source; retraction / editorial notice
detection; "trust" summary.

InterCiter mapping:
- 🟡 PaperDetailPage shows claims; projection composes views + decomposed scores.
- ⬜ Per-paper aggregate report object (tallies + timeline + filterable citing
  statements + conflicting-stance summary).
- ⬜ Retraction / editorial-notice signal (needs external source; S2 has flags).

Gap: build a Report aggregation service + endpoint + UI page; retraction signal
is a dependent WP requiring an external feed.

### F5. Collections (curated, monitored sets)
scite: build collections from Zotero/Mendeley/CSV of DOIs/search results;
monitor citation accumulation; alert on new supporting/contrasting + retractions.

InterCiter mapping:
- ⬜ No Collection concept.
- ✅ Ingestion by DOI/PMID exists; CSV/DOI batch is a thin wrapper.
- ⬜ Zotero/Mendeley import; monitoring/alerts.

Gap: new Collection domain (LinkML class), membership, batch import, and a
monitoring/alert job. Zotero/Mendeley connectors are optional later WPs.

### F6. Reference Check (evaluate a manuscript's references)
scite: upload a manuscript PDF; see how each reference has been cited, including
retractions / editorial notices / contrasting findings.

InterCiter mapping:
- 🟡 JATS-XML ingest exists; reference extraction from arbitrary PDF does not.
- ✅ Once references resolve to works, F4 Report tallies power the evaluation.
- ⬜ PDF reference-list parsing + per-reference report roll-up view.

Gap: reference-list extraction (start with DOIs/identifiers, PDF later) + a
"reference check" view reusing F4 aggregates.

### Cross-cutting: Retraction / editorial-notice signal
Feeds F4, F5, F6. External source (S2 flags, Retraction Watch / Crossref).
Model additively; non-mutating enrichment like existing S2 backfill.

---

## 2. Priority & sequencing

Wave A (foundation, mostly backend, high leverage, low external dependency):
- WP1 Aggregate citation tallies + section facet (F1/F4 core)
- WP2 Claim/citation full-text search endpoint + UI (F3)
- WP3 Paper Report aggregation endpoint + UI page (F4)

Wave B (builds on Wave A):
- WP4 Collections domain + batch DOI/CSV import + UI (F5)
- WP5 Retraction / editorial-notice enrichment signal (cross-cutting)
- WP6 Grounded Assistant QA service + chat UI (F2)

Wave C (dependent / heavier):
- WP7 Reference Check (identifier list first, PDF later) (F6)
- WP8 Saved searches & monitoring alerts (F3/F5)
- WP9 Zotero/Mendeley import connectors (F5)

Rationale: WP1 unlocks the aggregate tallies that Reports (WP3), Reference Check
(WP7), and Collection monitoring (WP4/WP8) all consume, so it must land first.

---

## 3. Subagent-ready work packages

Each WP is written so a subagent can execute it independently. Follow repo
conventions: LinkML-first schema edits, `services/` for derived/non-mutating
reads, projection pattern, reads-open/writes-CSRF, USWDS UI, tests both sides,
update `docs/api.md`. Verify: `make be-test` + `make fe-typecheck && make fe-test`.

### WP1 — Aggregate citation tallies + section facet  (F1/F4)   ✅ DONE
Goal: expose, per cited work AND per claim, tallies of citing statements by
stance / function / resolution, plus the citing section as a facet.
Backend:
- `services/` new aggregation (e.g. `citation_stats.py`), derived/non-mutating.
  Roll up RelationAssertion + ClaimOccurrence by function, stance, resolution,
  and section; return counts + the underlying citing statements.
- Endpoints: `GET /v1/papers/{work_id}/citation-stats`,
  `GET /v1/claims/{interp_id}/citation-stats`.
- Ensure section is captured on the occurrence/passage and surfaced.
Frontend: reusable `CitationTallies` component (stance/function chips w/ counts),
shown on PaperDetail + ClaimDetail. types.ts DTOs.
Tests: backend aggregation (support/contrast/mention counts, section grouping,
abstention excluded/labeled); frontend component render.
Deps: none. Unlocks WP3, WP4, WP7.

### WP2 — Claim/citation full-text search  (F3)   ✅ DONE
Goal: search verbatim claim/occurrence text with facets.
Backend:
- `services/search.py`: keyword search over ClaimInterpretation.normalized_text +
  ClaimOccurrence.verbatim_text (SQL LIKE/`ILIKE`; keep Postgres+SQLite compat).
  Optional embedding rerank behind a flag (SPECTER2 sidecar). Facets: section,
  function, stance, resolution, year, source type. Pagination.
- Endpoint: `GET /v1/search/claims?q=&section=&function=&stance=&…`.
Frontend: new `SearchPage` + route + nav entry; query box, facet controls,
result cards linking to claim/paper. Debounced.
Tests: backend query + facet filters + pagination; frontend page basic render.
Deps: none (embedding rerank optional, degrade gracefully).

> Implemented: `services/search.py` + `GET /v1/search/claims` (keyword over
> normalized claim text AND the verbatim source passage, case-insensitive
> `lower() LIKE` for SQLite+PG; facets section/function/stance/resolution +
> min_year/max_year; facet counts over the text/year set before categorical
> filters; head-interpretation unit; pagination). Frontend: search-first
> `HomePage` hero + reusable `SearchBox` + `SearchPage` (facet panel from live
> counts, provenance-anchored result cards, curated example queries in
> `data/exampleQueries.ts`) + `/search` route + "Search" nav entry. Tests:
> `tests/test_search.py` (9) + `SearchPage.test.tsx` (3). Deferred (optional):
> SPECTER2 embedding rerank and a `source type` facet.

### WP3 — Paper Report page  (F4)   ✅ DONE
Goal: scite-style per-paper report.
Backend: `services/report.py` composing WP1 tallies + a citations-over-time
timeline (group citing works by year) + conflicting-stance summary + filterable
citing-statement list. Endpoint `GET /v1/papers/{work_id}/report`.
Frontend: `ReportPage` (route `/papers/:workId/report`, linked from
PaperDetail): tally header, timeline (reuse a lightweight chart or a11y table),
filter controls, statement list. Retraction banner placeholder consumes WP5.
Tests: backend report shape + timeline bucketing; frontend render.
Deps: WP1. Soft-deps WP5 (retraction banner optional until WP5 lands).

> Implemented: `services/report.py` + `GET /v1/papers/{work_id}/report`
> (faceted filters section/function/stance/resolution/min_year/max_year,
> unfiltered facet counts, recomputed tallies, timeline buckets by citing-work
> year with unique-work counts, conflicting-stance summary, filterable statement
> list). Frontend: new `ReportPage` + route `/papers/:workId/report`, linked
> from `PaperDetailPage`, with USWDS filter controls + timeline a11y table.
> Tests: `backend/tests/test_report.py` (3) + `frontend/src/pages/ReportPage.test.tsx` (2).

### WP4 — Collections  (F5)   ✅ DONE
Goal: curated, monitored sets of works.
Schema (LinkML-first): add `Collection` + `CollectionMembership` classes to
`schema/interciter.yaml`; regenerate (`make pydantic sqlddl jsonschema`; note
`schema/generated/` is gitignored). Mirror in `models.py` (id prefixes in
ids.py, e.g. `coll_`, `cmem_`), add `relationship()` on FK cols (Postgres
insert-ordering rule).
Backend: `services/collections.py` (CRUD + membership, non-mutating reads via
projection). Batch import: accept CSV / list of DOIs/PMIDs, resolve/ingest via
existing pipeline (reuse jobs + idempotency key). Endpoints:
`POST/GET /v1/collections`, `GET/PATCH/DELETE /v1/collections/{id}`,
`POST /v1/collections/{id}/members` (batch), `DELETE …/members/{work_id}`.
Writes require auth + CSRF; ownership via principal.
Frontend: `CollectionsPage` (list/create) + `CollectionDetailPage` (members +
per-member WP1 tallies), batch-import form (paste DOIs / upload CSV). Nav entry.
Tests: backend CRUD + batch import + ownership; frontend pages.
Deps: WP1 (tallies on members). Monitoring/alerts split to WP8.

> Implemented: LinkML `Collection` + `CollectionMembership` (id prefixes `coll_` /
> `cmem_`), `services/collections.py` CRUD + membership, router `/v1/collections*`
> (ownership + auth), and `GET /v1/collections/{id}?include_member_tallies=true`
> surfacing per-member WP1 tallies. Batch import resolves pasted or uploaded
> CSV/TXT DOIs/PMIDs (parsed preview chips, added/skipped/stub feedback). Frontend
> `CollectionsPage` + `CollectionDetailPage` (member tallies, aggregate tallies,
> rename/describe/delete, member filter + sort, quick links to Report/Graph, CSV +
> filter-aware identifiers-TXT export). Monitoring (watch / new-citation delta /
> integrity badges / bulk-remove) landed via §5 — see below. Tests
> `tests/test_collections.py` + `CollectionDetailPage.test.tsx`. COMMITTED+PUSHED.

### WP5 — Retraction / editorial-notice signal  (cross-cutting)   ✅ DONE
Goal: non-mutating enrichment flagging retracted / noticed works.
Backend: extend `services/enrichment.py` (or new `services/integrity.py`) to
pull integrity flags from an external source (S2 paper flags first; optionally
Crossref / Retraction Watch). Persist additively (LinkML: add integrity fields
to PaperWork or a side `WorkIntegrityFlag` class — prefer side table). CLI verb
`integrity-check <work_id>|--all`. Net-gated live test (`INTERCITER_NET_TESTS=1`).
Frontend: retraction/notice badge component surfaced on PaperDetail, Report
(WP3), Reference Check (WP7), Collection members (WP4).
Tests: backend enrichment (offline via monkeypatched client) + badge render.
Deps: none hard; consumed by WP3/WP4/WP7.

> Implemented: source = **Crossref** (its Retraction Watch integration). New
> `ingestion/crossref.py` client (polite-pool `mailto`, rate-limit, disk cache,
> `net.ssl_context`+retry, 404→None). New `services/integrity.py`:
> `integrity_from_message` reads a work's `update-to` block (retraction/removal/
> withdrawal → `is_retracted`; expression-of-concern/correction/… → notice) with a
> `RETRACTED:`-title fallback; `check_work` writes the additive nullable
> `PaperWork.is_retracted` / `integrity_notice` (a definite `False` once checked,
> distinct from unchecked `null`); `check_all(only_unchecked=)`. Persisted on
> `PaperWork` (nullable columns, LinkML-mirrored) rather than a side table — the
> flags are 1:1 with a work and read on every paper view. Config
> `crossref_base`/`crossref_mailto`/`crossref_cache_dir`. CLI
> `integrity-check <work_id>|--all [--only-unchecked] [--limit]`. Surfaced via
> `PaperView.is_retracted`/`integrity_notice` (projection). Frontend: reusable
> `components/IntegrityBadges.tsx` (retracted + humanized notice tags) on
> collection members (WP4) + a retraction alert banner + badge on PaperDetail.
> Tests: `backend/tests/test_integrity.py` (11 offline + 1 net-gated live against
> the Wakefield 1998 retraction); frontend `IntegrityBadges.test.tsx` (3) +
> `PaperDetailPage.test.tsx` (1). Coverage caveat: absence of a flag means "no
> signal found" (depends on publisher deposits), not a guarantee of integrity.
> Deferred: Reference Check surfacing (WP7 not built yet); optional second source.

### WP6 — Grounded Assistant (RAG Q&A)  (F2)   → also serves bibliometrix WP-B10
Goal: evidence-grounded Q&A over InterCiter claims, answers cite verbatim spans.
Cross-plan: bibliometrix WP-B10 (Biblio-AI narration) EXTENDS this one assistant
with bibliometric rollups as an extra grounded source — do not build a second.
Backend: `services/assistant.py` — retrieve relevant claims/occurrences
(reuse WP2 search + embedding rerank), build a source-grounded prompt (reuse
`ingestion/llm_client.py`; injection-safe framing like LLMExtractor), require
the model to cite retrieved passage ids, ABSTAIN when unsupported. Return an
answer object: {answer_text, citations:[{claim/occurrence id, verbatim,
work_id}], abstained}. Endpoint `POST /v1/assistant/query`. Never fabricate
citations — validate every cited id exists in the retrieved set.
Frontend: `AssistantPage` chat surface; each answer renders inline source cards
linking to claim/paper detail; abstention shown explicitly.
Tests: backend with a BatchResponseClient / stub LLM (offline): citation
validation, abstention path, retrieval wiring; frontend render.
Deps: WP2 (retrieval). LLM client already exists.

### WP7 — Reference Check  (F6)
Goal: evaluate a manuscript's reference list.
Backend: reference-list intake — Phase 1 accept a list of DOIs/PMIDs (or parse a
JATS reference list); Phase 2 PDF reference extraction (add a PDF parser dep;
scope carefully). For each reference resolve to a work (ingest stub if unknown),
then roll up WP1 tallies + WP5 integrity flags. Endpoint
`POST /v1/reference-check` -> per-reference report rows. Runs via jobs pattern.
Frontend: `ReferenceCheckPage`: paste identifiers / upload, results table
(reference, stance/function tallies, retraction flag, link to Report).
Tests: backend identifier intake + roll-up (offline); frontend render.
Deps: WP1, WP5, WP3 (report aggregates). PDF parsing is a later sub-task.

### WP8 — Saved searches & monitoring alerts  (F3/F5)   ✅ DONE
Goal: persist searches / collections and notify on new supporting/contrasting
citations or retractions.
Schema: `SavedSearch` / `Alert` LinkML classes (additive). Backend: a scheduled
/ on-demand job (`services/jobs.py` pattern) that re-runs a saved search or
re-checks a collection and diffs against last-seen; surface new hits. Delivery =
in-app notification list first (email later, out of scope). Endpoints for CRUD +
`GET /v1/alerts`. Frontend: alerts panel + "save this search" / "watch this
collection" affordances.
Tests: diffing logic (new supporting citation appears -> alert row).
Deps: WP2, WP4, WP5.

> Implemented: additive LinkML `SavedSearch` (id `ssch_`, `search_query` JSON +
> `last_seen_ids` + `last_checked_at`) and `Alert` (id `alrt_`,
> `alert_source_type`/`alert_source_id`/`alert_type`/`work_id`/`claim_id`/`summary`/
> `is_read`), mirrored in `models.py`. `services/alerts.py`: SavedSearch CRUD
> (baseline seeded on create so pre-existing hits don't alert); `_run_saved_search`
> diffs current `search_claims` hits vs `last_seen_ids` → `new_claim` alerts;
> `_run_collection` diffs member support/contradict vs the WP4 watch snapshot →
> `new_support`/`new_contradict` alerts and emits `retraction` when a member is
> newly WP5-flagged (snapshot extended with a `retracted` bool). Both advance their
> baseline so a signal is never alerted twice. `run_all` covers all of a caller's
> saved searches + watched collections. Router `api/routers/alerts.py`
> (`/v1/saved-searches*`, `/v1/alerts*`, all `require_user` + ownership 404).
> Frontend: `AlertsPage` (saved-search list w/ run+delete, alert feed w/ mark-read +
> mark-all-read + "Check now"), `/alerts` route + nav entry (authOnly), and a
> "Save this search" affordance on `SearchPage` (auth-gated). Tests:
> `backend/tests/test_alerts.py` (8: CRUD, new-match diffing, create-baselines,
> read flow, run_all collection support + retraction, ownership/auth) + frontend
> `AlertsPage.test.tsx` (3) + a SearchPage save test. Consolidates Litmaps L5
> monitoring into this one subsystem. Deferred: email/SMTP delivery; a scheduled
> (vs on-demand) runner.

### WP9 — Zotero / Mendeley import connectors  (F5)   → also serves litmaps WP-L6 + bibliometrix WP-B6
Goal: import collections from reference managers.
Cross-plan: this is the ONE import layer. litmaps WP-L6 extends it to seed a Map,
and bibliometrix WP-B6 extends it to WoS/Scopus/Lens/Dimensions/OpenAlex + a
completeness report. Build the RIS/BibTeX/CSV core here; the others layer on.
Backend: connector(s) reading Zotero/Mendeley export (start with exported
RIS/BibTeX/CSV files — no OAuth), map to DOIs/PMIDs, feed WP4 batch import.
Endpoint `POST /v1/collections/{id}/import` (multipart). OAuth API sync is a
later, optional sub-task.
Frontend: import form on CollectionDetail. Tests: parser round-trip.
Deps: WP4.

---

## 4. Conventions checklist for every WP
- [ ] LinkML-first: edit `schema/interciter.yaml`, regenerate, mirror in
      `models.py` + `ids.py` (add `relationship()` on insert-ordered FK cols).
- [ ] Derived reads via `services/` (non-mutating, projection style). Never
      mutate scientific assertions.
- [ ] Reads open; writes require `require_user` + CSRF; ownership from principal.
- [ ] DTOs in `schemas.py` (backend) + `frontend/src/api/types.ts`.
- [ ] Router registered in `api/app.py`; update `docs/api.md`.
- [ ] USWDS components, Section-508 a11y (aria, keyboard, non-canvas fallback).
- [ ] Tests both sides. Backend: `make be-test`. Frontend: `make fe-typecheck &&
      make fe-test`. Live/external tests gated by `INTERCITER_NET_TESTS=1`.
- [ ] Preserve decomposed scores + explicit abstention; no blended scalar.

## 5. Immediate next execution order

Status: ✅ all five items below implemented (backend + frontend + tests + docs).

1. Collection-level watch setup (WP4 to WP8 bridge)  ✅ DONE
- Add a simple "Watch this collection" toggle in collection detail.
- Persist watch metadata backend-side first (state only, no delivery channel yet).
- Implemented: `Collection.is_watched` + `watch_snapshot` (per-member
  support/contradict baseline) + `watch_snapshot_at` (LinkML + ORM). Service
  `collections.set_watch` (enabling re-captures the baseline). Endpoint
  `POST /v1/collections/{id}/watch` ({watch}). UI: Monitoring summary box with a
  watch/stop-watch toggle.

2. New-citation delta endpoint for collections  ✅ DONE
- Add a backend derived read that compares current member citation tallies against
  a last-seen snapshot.
- Return only newly observed support/contradict signals per member and aggregate.
- Implemented: `collections.citation_delta` (clamped at zero; members added after
  the snapshot contribute full counts). Endpoint
  `GET /v1/collections/{id}/new-citations` returns
  `{has_snapshot, snapshot_at, new_support_total, new_contradict_total, members[]}`.
  UI renders the delta list inline in the Monitoring box.

3. Retraction/integrity badges on collection members (WP5 starter)  ✅ DONE
- Add nullable integrity flags to collection member views.
- Render badges in collection detail and include integrity signal in exports.
- Implemented: additive nullable `PaperWork.is_retracted` + `integrity_notice`
  (LinkML + ORM), surfaced on `CollectionMemberView`. UI `IntegrityBadges`
  (retracted + notice tags) on member rows; CSV export gains `is_retracted` /
  `integrity_notice` columns. No integrity feed yet (WP5 proper) — flags stay
  null until an enrichment source populates them.

4. Bulk actions on filtered members  ✅ DONE
- Add a bulk remove action for current filtered members with explicit confirmation.
- Make CSV export filter-aware to align with the identifiers TXT export behavior.
- Implemented: `collections.bulk_remove_members` + endpoint
  `POST /v1/collections/{id}/members/bulk-delete` ({work_ids}, 1–500, unknown ids
  ignored). UI "Remove N filtered member(s)" button (confirmation) operating on the
  current filter; CSV + identifiers TXT exports were already filter-aware.

5. Collection regression coverage expansion  ✅ DONE
- Add backend tests for delta calculation and ownership/authorization rules.
- Add frontend tests for watch toggle, bulk remove flow, and integrity badge render.
- Implemented: backend `tests/test_collections.py` +9 (watch toggle+snapshot,
  delta after snapshot + re-baseline, delta without snapshot, bulk remove +
  empty-list 422, integrity flag surfacing, watch/delta/bulk ownership 404 +
  auth 401). Frontend `CollectionDetailPage.test.tsx` +3 (integrity badges, watch
  toggle+baseline delta panel, bulk-remove filtered flow). Full backend suite
  green (5 pre-existing skips); 44 frontend vitest pass; build clean.

## 6. Notes / open questions
- Retraction feed choice (S2 vs Crossref vs Retraction Watch) — DECIDED in WP5:
  Crossref (its Retraction Watch integration), via a work's `update-to` block.
  A second source can be layered later if coverage gaps warrant it.
- Assistant model target: NIEHS LiteLLM proxy vs Biowulf vLLM — both supported by
  `llm_client.py`; pick per-deployment via config.
- PDF reference extraction (WP7) adds a dependency; confirm before implementing.
- Alerts delivery is in-app only for now (no email/SMTP infra).
