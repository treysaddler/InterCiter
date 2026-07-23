# Litmaps Feature-Parity Plan

Status: DRAFT — planning artifact for subagent execution
Source: https://www.litmaps.com/features (+ docs.litmaps.com), captured 2026-07-21
Owner: (assign)

This document (1) catalogs the Litmaps features we want to replicate, (2) maps
each to InterCiter's existing capabilities, and (3) breaks the gap into discrete,
subagent-ready work packages (WPs). Companion to `plans/scite-feature-parity.md`
— shared work packages are cross-referenced to avoid duplication.

InterCiter differentiators to preserve while replicating Litmaps:
- Provenance-first (verbatim spans), decomposed scores, explicit abstention.
- Function and stance are SEPARATE dimensions.
- LinkML-first schema changes; reads open / writes require auth + CSRF.
- USWDS / Section-508 UI (a11y non-canvas fallbacks for any visualization).

Litmaps' core value prop = accelerate literature reviews via connection-based
discovery and interactive citation maps. InterCiter already ships a Cytoscape
network graph (papers/authors/citations/claims + S2/ROBOKOP expansion), so the
Visualize and citation-chaining pillars are substantially in place; the gaps are
seed-based discovery, saveable/shareable maps, map annotation, custom
layout axes/algorithms, monitoring, and Zotero sync.

---

## 1. Feature catalog & gap analysis

Legend: ✅ have · 🟡 partial · ⬜ missing

### L1. Search (connection-based article search)
Litmaps: search 270M+ papers; rank by connection using citations/references;
customizable search algorithms + advanced filters.

InterCiter mapping:
- ✅ External corpus reach: Semantic Scholar (`ingestion/semantic_scholar.py`,
  bulk datasets) + PMC; graph expansion by citation edges.
- 🟡 Local search only via `GET /v1/papers` list; scite-parity WP2 adds claim
  full-text search. No connection-ranked article discovery over the external
  corpus.
- ⬜ Connection-ranked search (rank candidate papers by citation/reference
  overlap with a seed set) + tunable algorithm + filters.

Gap: a connection-ranked discovery service over S2 (see L2, they share code).

### L2. Dive deeper / Discover (seed-based discovery)
Litmaps: start from a seed article (or a whole library) and find the most
important connected work; "find research gaps"; custom filters.

InterCiter mapping:
- ✅ Seed substrate: `services/graph.paper_neighborhood` (BFS over CitationEdge)
  + `expand_from_semantic_scholar` already pulls S2 references and creates stub
  works. This is the discovery engine's foundation.
- 🟡 Expansion is one-hop/manual, not a ranked "here are the N most-connected
  papers you're missing" recommendation.
- ⬜ Seed-set discovery: given seed work(s), fetch their references + citations
  from S2, score candidates by connection strength (in/out-degree to the seed
  set, optionally SPECTER2 similarity), return a ranked candidate list.

Gap: `services/discovery.py` producing ranked candidates from a seed set.

### L3. Visualize (interactive, annotatable citation map)
Litmaps: interactive citation map; dynamically change how papers are mapped
using traditional + unique measures (e.g. year × citations); annotate articles.

InterCiter mapping:
- ✅ `components/NetworkGraph.tsx` (Cytoscape) + `GraphPage` with modes, hops,
  authors toggle, S2/ROBOKOP expansion, a11y table fallback, legend.
- 🟡 Layout is fixed (cose). No axis-based layouts (e.g. x=year, y=citation
  count), no per-node annotations, no styling by metric.
- ⬜ Configurable layout axes / node sizing by measure; per-node user
  annotations/notes; saved map state.

Gap: axis-layout + node-metric styling in NetworkGraph; annotation model;
map persistence (see L4).

### L4. Share / Save maps (Litmaps + Workspaces)
Litmaps: save named "Litmaps" and Workspaces; share with colleagues/students;
collaborate.

InterCiter mapping:
- ⬜ No saved-map / workspace concept. Graph state is ephemeral (URL params only).
- ✅ Auth + ownership primitives (principal, roles) ready to own saved maps.

Gap: `Map`/`Workspace` domain (LinkML), persistence of seed set + layout +
annotations, and a share mechanism (shareable read-only link/token).

### L5. Monitor (alerts on new papers)
Litmaps: automatic (weekly) email alerts when new papers on your topic appear;
works off your existing maps.

InterCiter mapping:
- ⬜ No alerting. Shares design with scite-parity WP8 (saved searches & alerts).
- ✅ Jobs pattern (`services/jobs.py`) to run periodic re-checks.

Gap: monitor a saved map / seed set; diff new connected papers vs last-seen.
CONSOLIDATE with scite-parity WP8 (single alerts subsystem for searches, maps,
and collections). Email delivery out of scope initially (in-app notifications).

### L6. Zotero sync
Litmaps: sync a Zotero library/collection; keep it updated.

InterCiter mapping:
- ⬜ No reference-manager import. Overlaps scite-parity WP9 (Zotero/Mendeley
  import). CONSOLIDATE: one connector feeds both Collections (scite WP4) and
  seed sets/maps (Litmaps L2/L4).

Gap: covered by scite-parity WP9; extend it to seed a Map, not just a Collection.

---

## 2. Overlap with the scite parity plan (do NOT duplicate)
- Local full-text search → scite-parity **WP2** (claim search). Litmaps L1 adds
  external connection-ranked discovery on top (new, WP-L1 below).
- Alerts / monitoring → scite-parity **WP8**. Litmaps L5 is a consumer; fold map
  monitoring into WP8 rather than building a second alerts system.
- Zotero/Mendeley import → scite-parity **WP9**. Litmaps L6 = extend WP9 to also
  seed a Map/seed-set.
- Collections (scite WP4) and Maps/Workspaces (Litmaps L4) are siblings; consider
  a shared "saved set of works" base so Collections and Maps reuse membership.

---

## 3. Priority & sequencing (Litmaps-specific WPs)

These are NEW packages beyond the scite plan. Prereqs reference scite WPs where
shared.

Wave A:
- WP-L1 Seed-based discovery service (ranked candidates from a seed set) (L1/L2)
- WP-L2 Saved Maps / seed-set persistence (L4)

Wave B:
- WP-L3 Map visualization upgrades — migrate the renderer to custom D3 and add
  axis layouts + node-metric styling + annotations (L3). Split into WP-L3a (D3
  render-core swap), WP-L3b (axis layouts + metric styling), WP-L3c (annotations,
  needs WP-L2). WP-L3a/b need no persistence; WP-L3c depends on WP-L2.
- WP-L4 Map sharing (read-only share token/link) (L4)   ✅ DONE

Wave C (consolidated with scite plan):
- WP-L5 Map monitoring → extend scite-parity WP8 (L5)
- WP-L6 Zotero seed import → extend scite-parity WP9 (L6)

Rationale: WP-L2 (persistence) unblocks sharing (WP-L4) and monitoring (WP-L5);
WP-L1 (discovery) is independent and immediately useful via the existing graph UI.

---

## 4. Subagent-ready work packages

Follow repo conventions (see §5 checklist). Verify with `make be-test` +
`make fe-typecheck && make fe-test`. Update `docs/api.md`.

### WP-L1 — Seed-based discovery (ranked candidates)  (L1/L2)   ✅ DONE
Goal: given seed work(s), return a ranked list of the most-connected papers the
user is likely missing.
Backend: `services/discovery.py` (derived/non-mutating). Input: list of seed
work_ids (+ optional filters year/venue). Gather references + citations of the
seeds via `ingestion/semantic_scholar.py` (reuse enrichment.reference_links /
S2 client; respect rate-limit + cache). Score each candidate by connection
strength = count of links to the seed set (in + out degree), optionally boosted
by SPECTER2 cosine to seed centroid (Phase-2 sidecar; degrade gracefully).
Return ranked candidates {work_id-or-external-id, title, year, connection_score,
supporting_seed_ids}. Do NOT auto-persist candidates as full works (may create
metadata-stub PaperWorks like existing expand flow — keep idempotent).
Endpoint: `POST /v1/discovery/seeds` (body {seed_work_ids, filters}). Read-ish
but performs S2 fetch → require_user (network write) + CSRF, consistent with
`expand_from_semantic_scholar`.
Frontend: on GraphPage / PaperDetail add "Find related work" → results panel of
ranked candidates with "add to map" / open paper actions.
Tests: backend scoring with monkeypatched S2 client (ranking order, degrade
without embeddings, filter application); frontend panel render.
Deps: none hard (S2 client + graph exist). Net-gated live test optional.

### WP-L2 — Saved Maps / seed-set persistence  (L4)   ✅ DONE
Goal: persist a named map = seed set + layout config + (later) annotations.
Schema (LinkML-first): add `Map` (aka SavedMap) + `MapMembership` classes to
`schema/interciter.yaml`; regenerate. Consider a shared base with scite-parity
Collection so membership is reused. Mirror in `models.py`, ids.py prefixes
(e.g. `map_`, `mmem_`); `relationship()` on FK cols (Postgres insert-ordering).
Fields: name, description, owner_id, layout_config JSON (mode/hops/axis/etc.),
created/updated. Membership: map_id, work_id, optional note (annotation),
position JSON (for pinned layout).
Backend: `services/maps.py` CRUD + membership; reads via projection. Endpoints:
`POST/GET /v1/maps`, `GET/PATCH/DELETE /v1/maps/{id}`,
`POST /v1/maps/{id}/members`, `DELETE /v1/maps/{id}/members/{work_id}`,
`PATCH /v1/maps/{id}/members/{work_id}` (note/position). Writes auth+CSRF,
ownership from principal.
Frontend: `MapsPage` (list/create) + load a saved map into GraphPage (hydrate
seed set + layout_config); "Save map" from GraphPage.
Tests: backend CRUD + membership + ownership; frontend save/load round-trip.
Deps: none. Unblocks WP-L3, WP-L4, WP-L5.

### WP-L3 — Map visualization upgrades (D3 migration)  (L3)
Goal: Litmaps-style dynamic mapping + annotation, on a custom D3 renderer.

DECISION: replace the Cytoscape renderer with a custom **D3 (SVG)** visualization.
Rationale: the Litmaps-defining interactions — mapping papers by a measure
(e.g. x = year, y = citation count), sizing/coloring nodes by a metric, and
smooth zoom/pan/transitions — are first-class in D3 and awkward in Cytoscape.
Modular d3 (`d3-selection` + `d3-scale` + `d3-zoom` + `d3-force`) is ~50–80 KB vs
the current ~447 KB Cytoscape chunk, so this is a bundle *win*. Use **SVG** (not
canvas): neighborhoods are capped at 250 nodes and the global graph is bounded, so
SVG stays performant and keeps the DOM inspectable for a11y. Only revisit canvas if
we later render the full ~1000-paper snowball corpus at once.

Hard constraints (unchanged):
- Section-508: the SVG canvas stays `aria-hidden`, wrapped in try/catch for jsdom;
  the `<details>` node/edge table + legend remains the accessible representation and
  MUST stay in sync with whatever measure/layout is shown (tests assert on it).
- Same component contract: keep `NetworkGraph.tsx`'s existing props/interface so the
  two consumers (`GraphPage`, `SearchNetwork`) keep working; migrate internals only.

Split into three independently-shippable steps:

**WP-L3a — D3 render core (no backend change).**   ✅ DONE
Replace `NetworkGraph.tsx` internals with a d3 SVG renderer behind the SAME
props/interface. Keep a force layout (`d3-force`) as the default, node-select
buttons, legend, and the a11y table/fallback + jsdom try/catch. Add `d3` (modular)
dep; drop `cytoscape`/`@types/cytoscape` once no consumer references them. Update the
existing `NetworkGraph.test.tsx` (mock d3 or assert on the a11y table, not the SVG).
A pure swap that de-risks the rest.
Tests: a11y table renders, node-select fires, truncation summary, legend scoped.
Deps: none.

**WP-L3b — Axis layouts + node-metric styling (mostly frontend).**   ✅ DONE
Add layout modes to `NetworkGraph` + controls on `GraphPage`:
- Axis layouts via `d3-scale` (+ rendered axes/gridlines): e.g. x = year,
  y = citation count or in-degree; keep `force` as a mode.
- Node sizing/coloring by a measure (citation count, in/out-degree, stance mix).
- Keep the a11y table in sync — surface the active measure as table columns.
Backend: reuse scite-parity WP1 tallies / graph degree for measures; avoid new
endpoints (add node.data measures in `services/graph.py` only if not already there).
Tests: layout/style props reflect in the a11y table; axis mode positions nodes.
Deps: WP-L3a.

**WP-L3c — Per-node annotations (needs persistence).**   ✅ DONE
When a saved Map is loaded (WP-L2), allow editing a per-node note; persist via the
WP-L2 membership `note`. Show the note in the node summary box + a11y table.
Tests: annotation edit calls the WP-L2 endpoint; note appears in the a11y table.
Deps: WP-L2, WP-L3a.


### WP-L4 — Map sharing (read-only link)  (L4)   ✅ DONE
Goal: share a saved map with others via a link, read-only.
Schema: add a `share_token` (nullable, unique) + `visibility` enum to Map, or a
`MapShare` side class (token, map_id, created_at, revoked). LinkML-first.
Backend: `POST /v1/maps/{id}/share` (owner, auth+CSRF) mints a token;
`DELETE …/share` revokes; `GET /v1/shared-maps/{token}` returns a read-only map
projection WITHOUT requiring auth (token is the capability). Rate-limit + do not
leak owner PII. Reads open by token only.
Frontend: "Share" button → copyable link; a public `/shared/:token` viewer route
that loads GraphPage in read-only mode.
Tests: token mint/revoke, token access returns map, revoked token 404, no writes
via shared route.
Deps: WP-L2.

### WP-L5 — Map monitoring  (L5) → EXTEND scite-parity WP8
Goal: alert when new papers connect to a saved map's seed set.
Do NOT build a separate alerts system. In scite-parity WP8's alerts subsystem,
add a "map" alert source: periodically re-run WP-L1 discovery for the map's seed
set, diff candidates against last-seen, surface new connected papers as alert
rows. In-app notifications first; email later/out of scope.
Deps: WP-L1, WP-L2, scite-parity WP8.

### WP-L6 — Zotero seed import  (L6) → EXTEND scite-parity WP9
Goal: import a Zotero library/collection as a seed set / Map.
Extend scite-parity WP9's Zotero/Mendeley connector so an imported set can target
a Map (WP-L2) in addition to a Collection (scite WP4). Start with exported
RIS/BibTeX/CSV (no OAuth); map to DOIs/PMIDs; create Map membership.
Deps: WP9 (scite plan), WP-L2.

---

## 5. Conventions checklist for every WP
- [ ] LinkML-first: edit `schema/interciter.yaml`, regenerate, mirror in
      `models.py` + `ids.py` (`relationship()` on insert-ordered FK cols).
- [ ] Derived reads via `services/` (non-mutating, projection style).
- [ ] Reads open; writes (and S2/network-triggering reads) require `require_user`
      + CSRF; ownership from principal. Share-by-token is a scoped exception.
- [ ] DTOs in `schemas.py` + `frontend/src/api/types.ts`; router in `api/app.py`.
- [ ] USWDS + Section-508: every visualization keeps the a11y table/legend
      fallback in sync (canvas is aria-hidden, wrapped in try/catch for jsdom).
- [ ] Tests both sides; external/live tests gated by `INTERCITER_NET_TESTS=1`.
- [ ] Preserve decomposed scores + explicit abstention; no blended scalar.
- [ ] Reuse existing graph + S2 code; keep S2 stub-work creation idempotent.

## 6. Notes / open questions
- Shared base for Collection (scite WP4) vs Map (WP-L2) membership — decide before
  building the second one to avoid divergence.
- Discovery ranking: pure connection-degree vs SPECTER2-boosted — start with
  degree, make the embedding boost a config flag (embeddings already sidecar).
- Renderer: WP-L3 migrates from Cytoscape to custom **D3 (SVG)** — modular d3 is a
  net bundle *reduction* vs the ~447 KB Cytoscape chunk, and axis/metric layouts are
  first-class in D3. SVG is sufficient at the current node caps (≤250/neighborhood);
  revisit canvas only for full-corpus rendering. The Section-508 a11y table/legend
  fallback stays the source of truth and must track the active measure/layout.
- Sharing PII: shared-map projection must exclude owner identity/tokens.
- Email alert delivery deferred (no SMTP infra); in-app notifications only.
