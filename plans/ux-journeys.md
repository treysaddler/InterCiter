# InterCiter — User Journeys & Information-Architecture Redesign

Status: DRAFT — planning artifact (no code changes)
Created: 2026-07-23
Owner: (assign)
Companions: [`docs/ui-design.md`](../docs/ui-design.md) (personas + user stories §8),
`plans/scite-feature-parity.md`, `plans/litmaps-feature-parity.md`,
`plans/bibliometrix-feature-parity.md`.

## 0. Why this document exists

InterCiter shipped a large second wave of features one work-package at a time
(Search, Analytics, Collections, Maps, Alerts, Graph/Explore, Discovery, Reports,
Citation stats, Integrity, Bibliometrics). Each WP added a page and — where it
needed one — a top-nav entry. The result is **information-architecture debt**: the
navigation grew *additively per feature* instead of *around user goals*, and the
original user-story doc ([`docs/ui-design.md` §8](../docs/ui-design.md)) only covers
the first MVP wave (Reader / Ingest / Review / Identity / a11y).

This document adds the two layers that are missing:

1. **User journeys** — narrative, screen-by-screen walkthroughs of how each persona
   accomplishes a real goal. (User *stories* are the atomic "As a … I want …"
   statements we already have; *journeys* stitch them into flows and are what
   surface dead-ends and orphaned pages.)
2. **A proposed IA / navigation redesign** organized around those journeys.

It is a planning artifact only. No code is changed here; §6 lists the follow-up
implementation WPs.

---

## 1. Current state (inventory)

### 1.1 Routes live in the SPA today

Source: [`frontend/src/App.tsx`](../frontend/src/App.tsx).

| Route | Screen | Auth | Reachable from top nav? |
| --- | --- | --- | --- |
| `/` | Home (search hero) | open | logo |
| `/search` | Search claims + facets + result network | open | ✅ Search |
| `/analytics` | Corpus bibliometrics (Overview/Authors/Sources/Countries tabs) | open | ✅ Analytics |
| `/papers` | Papers list | open | ❌ deep-link only |
| `/papers/:id` | Paper detail (claims, citation tallies, integrity, related work) | open | ❌ from search/list |
| `/papers/:id/report` | Paper citation report (timeline, facets) | open | ❌ from paper detail |
| `/papers/:id/claims/:claimId`, `/claims/:claimId` | Claim detail (core screen) | open | ❌ from paper/search |
| `/graph`, `/graph/papers/:id` | Network explorer (papers/claims, axis layouts, ROBOKOP) | open | ❌ **no nav entry** |
| `/shared/:token` | Public read-only shared map | open (token) | ❌ external link |
| `/ingest` → `/jobs/:id` → `/runs/:id` | Submit a paper + job/run | auth | ✅ Submit a paper |
| `/review`, `/clusters/:id` | Reviewer queue + cluster detail | reviewer | ✅ Review |
| `/collections`, `/collections/:id` | Collections (watch, import, integrity, CSV) | auth | ✅ Collections |
| `/maps` | Saved maps (open in graph, share, monitor) | auth | ✅ Maps |
| `/alerts` | Saved searches + alert feed | auth | ✅ Alerts |
| `/account` | Self view + admin user management | auth | ✅ Account |

### 1.2 Current top nav

Source: [`frontend/src/components/AppShell.tsx`](../frontend/src/components/AppShell.tsx#L14).

`Search · Analytics · Collections · Maps · Alerts · Submit a paper · Review · Account · Sign in/out`

Eight primary items in a flat list, four of them auth-gated, ordered by build date.

### 1.3 Problems this creates

- **Orphaned power features.** The **Network Explorer** (`/graph`) — one of the most
  differentiating screens — has **no nav entry at all**; it is reachable only via a
  "Explore citation network →" link on paper detail or by opening a saved map.
  Similarly **Discovery** ("Find related work") is buried inside paper detail, and
  **Reports** only exist as a link inside a single paper.
- **Flat nav mixes verbs and nouns.** "Submit a paper" (an action) sits beside
  "Collections" (an object) beside "Analytics" (a workspace). There is no grouping,
  so the nav reads as a pile of features rather than a set of goals.
- **No home for "explore the corpus."** Search, Analytics, Graph, Discovery and Maps
  are all facets of the same journey (understand a body of literature) but are
  scattered across three nav slots plus two orphaned deep-links.
- **Personas are stale.** The doc names Reader, Reviewer, Operator — but the
  analytics/maps/discovery wave implies a fourth persona (below) that has no journey.
- **Growth pressure.** ~10 more parity WPs are planned (Assistant, Reference Check,
  bibliometric networks, thematic maps, historiograph, PRISMA, multi-db import). A
  flat nav cannot absorb them; we need groups now.

---

## 2. Refreshed personas

Keeps the three existing personas ([`docs/ui-design.md` §2](../docs/ui-design.md))
and adds a fourth that the second feature-wave created.

### Persona A — Reader / Evidence checker (primary, unchanged)
Wants a single paper's claims, the exact sentence behind each, who it cites, whether
the cited work supports it, decomposed confidence, and full provenance. Mostly reads.

### Persona B — Reviewer / Curator (primary, unchanged)
Audits model output: triages, revises interpretations (additive), records
per-dimension decisions, manages clusters. `reviewer`/`admin`.

### Persona C — Ingestion operator (secondary, unchanged)
Submits a paper, watches the job, compares extractors. Thin.

### Persona D — Research strategist / Bibliometric analyst (NEW, primary — DECIDED target)
A researcher, librarian, or evidence-synthesis lead working at the **corpus** level,
not a single paper. They want to: assemble a body of literature (search → collect →
snowball/discover), understand its shape (Analytics: production over time, top
authors/sources/countries, Bradford/Lotka), map its structure (network graph,
co-citation/coupling, thematic maps), and monitor it over time (watched
collections/maps, alerts). This persona is the consumer of nearly the entire second
wave (Search, Analytics, Discovery, Maps, Graph, Collections, Alerts) and of the
planned bibliometrix WPs — yet has **zero journeys** in the current doc. Reads are
open; saving/monitoring requires auth.

> **Decision (2026-07-23): Persona D is a first-class target user we optimize for**,
> not a power-user side effect. Consequences we accept: Analytics and the Network
> Explorer become *primary* surfaces (promoted in the nav, §4.1); the entire
> bibliometrix parity track (WP-B1…B10) is in-scope product work, not a side quest;
> and every corpus surface must still offer a path **down** to claim-level
> provenance so D's aggregate metrics never become an unaccountable blended score.

> Design tension to hold: Persona D speaks the language of *aggregate metadata
> metrics*, but InterCiter's differentiator is *claim-level provenance*. Journeys for
> D must always offer a path **down** to a claim's evidence, so metrics never become
> an unaccountable blended score (see `bibliometrix-feature-parity.md` §0).

---

## 3. User journeys

Format per journey: **Goal**, **Persona**, **Entry**, **Flow** (numbered screen
steps with routes), **Exits/branches**, and **Gaps** (friction found while tracing).

### J1 — "Does this paper's claim actually hold up?" (Persona A)
- **Goal:** verify a specific empirical claim and its citation support.
- **Entry:** Home search hero, or a shared link to a claim.
- **Flow:**
  1. `/` → type a term → `/search?q=…`.
  2. Scan result cards (claim text + verbatim + separate function/stance tags);
     the focused result's citation neighborhood renders above the list.
  3. Open a claim → `/claims/:id` (core screen): pinned evidence pane highlights the
     occurrence span, one-hop relations show function + stance separately, decomposed
     score chips, explicit abstention state, provenance accordion.
  4. Follow one hop → cited `/papers/:id` or matched `/claims/:id`.
  5. On the paper → "How this paper has been cited" tallies + integrity badges.
- **Exits:** open the paper report; jump to the citation network.
- **Gaps:** none blocking — this is the best-supported journey. Minor: getting from a
  claim back to *"show me everything citing this claim"* relies on the citation-stats
  panel, which is easy to miss below the fold.

### J2 — "Assemble and understand a body of literature" (Persona D) ⬅ weakest today
- **Goal:** build a corpus around a topic and understand its shape.
- **Entry:** Search, or an existing Collection.
- **Flow (as currently possible):**
  1. `/search` to find seed papers → open `/papers/:id`.
  2. On paper detail, "Find related work" (Discovery) → ranked related papers.
  3. Add papers to a Collection (`/collections`, `/collections/:id`) — or import a
     RIS/BibTeX/CSV library.
  4. Separately, go to `/analytics` to see corpus-level metrics — **but Analytics
     runs over the whole DB or an explicit `work_ids` set, and there is no UI to say
     "analyze *this* collection."**
  5. Separately, open `/graph` (if you can find it) to see the citation network — but
     it is **not linked from Collections**, so you cannot go "network of this
     collection" without building a Map first.
- **Gaps (this journey is fragmented):**
  - **G1:** No "Analyze this collection" button. Collections and Analytics don't talk;
    the `work_ids` filter exists in the API but has no UI entry from a collection.
  - **G2:** Network Explorer has no nav entry and is not launchable from a collection.
  - **G3:** Discovery is hidden inside one paper; there's no corpus-level "grow this
    collection" (snowball) action in the UI even though `snowball.py` exists in the
    backend/CLI.
  - **G4:** The relationship Collection → Map → Graph → Analytics is a diamond of the
    same underlying work-set, but the UI treats them as four unrelated destinations.

### J3 — "Map and visually explore citation structure" (Persona D)
- **Goal:** explore how papers/authors/claims connect; save and share a map.
- **Entry:** paper detail "Explore citation network →", or a saved Map.
- **Flow:**
  1. `/graph` → toggle papers/claims, show authors, choose hops, axis layout
     (x=year, y=cited-by), node sizing.
  2. Select a node → open paper / center here / expand from Semantic Scholar /
     Explore in ROBOKOP (claims).
  3. Save as Map → `/maps` → open, share (read-only token), or watch for new
     connections.
- **Exits:** `/shared/:token` public viewer; alerts when watched.
- **Gaps:** entry discoverability (G2). Once inside, the flow is strong.

### J4 — "Bibliometric analysis of a field" (Persona D)
- **Goal:** production trends, top authors/sources/countries, Lotka/Bradford.
- **Entry:** `/analytics`.
- **Flow:** tabs Overview → Authors → Sources → Countries; year filter.
- **Gaps:** **cohort selection is invisible** — a user can only analyze "everything"
  unless a caller passes `work_ids`. No way to pick a Collection/Map/search-result-set
  as the cohort. Country metrics are empty until affiliations exist (WP-B6). Planned
  bibliometrix WPs (networks, thematic maps, historiograph, PRISMA, corpus report)
  all need a home — currently Analytics is a flat 4-tab page with nowhere to grow.

### J5 — "Submit a paper and read its extraction" (Persona C → A)
- **Goal:** ingest, watch the job, land on results.
- **Flow:** `/ingest` → `/jobs/:id` (poll) → paper + run links → `/papers/:id`.
- **Gaps:** none blocking. Extractor comparison is CLI-only (acceptable for MVP).

### J6 — "Review and correct extractions" (Persona B)
- **Goal:** triage, revise, decide, curate clusters.
- **Flow:** `/review` queue → `/claims/:id` reviewer panel (revise / record decision /
  clusters) → `/clusters/:id`.
- **Gaps:** none blocking. The reviewer panel is only surfaced on claim detail; a
  reviewer arriving via search sees it contextually, which is fine.

### J7 — "Monitor a topic / collection / map over time" (Persona B/D)
- **Goal:** get told when new evidence or connections appear.
- **Flow:** save a search (`/search` → Save) or watch a collection/map → `/alerts`
  feed → "Check now" → drill into the new claim/paper.
- **Gaps:** three different "watch" affordances (saved search, watched collection,
  watched map) all feed one `/alerts` page — good — but the *creation* of each lives
  on a different screen, so the mental model "I want to monitor X" has three doors.

### J8 — "Account & administration" (all)
- **Flow:** `/account` self view; admin user management.
- **Gaps:** none.

---

## 4. Proposed information architecture

Reorganize the flat 8-item nav into **goal-oriented groups**. The guiding split:
*Explore* (understand literature — Persona A/D, mostly open reads) vs. *Curate &
monitor* (own something over time — Persona B/D, auth) vs. *Contribute* (Persona C)
vs. *account*. Primary nav stays small; secondary destinations move **into** the
workspace they belong to.

### 4.1 Recommended top-level nav

> **Decision (2026-07-23): dropdown top-nav, NOT a sidebar.** Implement the two
> grouped items (Explore, Workspaces) as USWDS `PrimaryNav` dropdowns
> (`NavDropDownButton` + `Menu` from `@trussworks/react-uswds`), keeping the existing
> `Header` + hamburger (`NavMenuButton`) shell in
> [`AppShell.tsx`](../frontend/src/components/AppShell.tsx). Rationale: only two
> groups need nesting, each with 3–4 items — well within what a top-nav dropdown
> handles cleanly; the component is USWDS-native and Section-508 tested (keyboard +
> ARIA menu semantics come for free); it preserves the current search-first header
> and mobile hamburger with minimal refactor; and a persistent left sidebar would
> consume horizontal space and force a layout change better suited to deep,
> docs-style hierarchies than to a 4-group primary nav. Revisit the sidebar only if a
> group ever exceeds ~7 items.

```
Search   Explore ▾   Workspaces ▾   Submit   Review*   Account / Sign in
```

- **Search** — unchanged, stays first (search-first product).
- **Explore ▾** (open, no auth) groups the "understand the literature" surfaces that
  are currently scattered/orphaned:
  - Papers (list)
  - Network explorer  ← *fixes G2: gives `/graph` a home*
  - Analytics / Bibliometrics  ← future home for WP-B3/B4/B5/B8 sub-tabs
  - (later) Discover related work as a standalone entry ← *fixes G3 discoverability*
  - (later) **Ask** — grounded Assistant (scite WP6, own page — see §5.1)
- **Workspaces ▾** (auth) groups the things a user *owns and monitors* — the
  Collection/Map/Alerts diamond that is really one journey:
  - Collections
  - Maps
  - Alerts / Monitoring
  - Saved searches (currently folded into Alerts)
- **Submit** (auth) — ingestion.
- **Review** (reviewer/admin only) — stays a top-level peer because it is a distinct
  role-gated job.
- **Account** / **Sign in** — unchanged.

Rationale: this collapses 8 flat items into 4 stable groups that each map to a
persona goal, leaves room for ~10 planned WPs to slot **inside** a group instead of
adding nav entries, and finally gives the Network Explorer and Discovery real homes.

### 4.2 Cross-links to fix the fragmentation gaps

These are cheap wiring changes (buttons/links), independent of the nav restructure:

- **G1 — "Analyze this collection":** on `/collections/:id`, add "View analytics for
  this collection" → `/analytics?work_ids=…` (API already accepts `work_ids`). Same
  for Maps.
- **G2 — Network from a collection/map/search:** add "Explore as network" on
  `/collections/:id` and on the search results header (the search page already
  renders a neighborhood component — promote it to a full-explorer link).
- **G3 — Grow a collection:** surface `snowball`/Discovery as a "Find & add related
  work" action *inside* a collection, not only inside one paper.
- **G4 — Unify the work-set:** treat Search-results / Collection / Map as
  interchangeable "cohorts" that can each be sent to Analytics or the Graph. (Longer
  term this argues for a shared saved-set base — see the open question in all three
  parity plans about unifying Collection/Map/Corpus membership.)

### 4.3 DECISION: "cohort" is a first-class connective concept

The single biggest IA insight: **Search results, Collections, Maps, and the snowball
Corpus are all the same thing — a set of works** — and every analysis surface
(Analytics, Graph, Discovery, Reports-rolled-up-to-corpus, future bibliometric
networks) operates on a set of works.

> **Decision (2026-07-23): we commit to "cohort" as a first-class, routable concept
> NOW**, before layering on the heavier bibliometric network/thematic WPs. Every
> analysis screen accepts an interchangeable cohort source — `?collection=…` /
> `?map=…` / `?search=…` (or explicit `work_ids=…`) — and resolves it to a work-set.
> This turns today's disconnected pages into one coherent journey and is the
> structural fix behind gaps G1–G4.

Why now rather than retrofit: every planned Persona-D WP (bibliometric networks,
thematic maps, historiograph, corpus report, PRISMA) will independently need "run
this analysis over *these* works." Building the cohort seam once (UX-3) means those
WPs inherit cohort selection for free; retrofitting later means re-plumbing each
screen. It also front-runs the shared saved-set data question (§6, item 5): the
routing seam can ship over the existing `work_ids` API immediately, while the
deeper Collection/Map/Corpus table unification follows without changing the UI
contract.

**Naming note:** "cohort" is the internal/route concept; the UI should use plain
language per surface ("these results", "this collection", "this map") rather than
exposing the word "cohort" to users.

---

## 5. Where the near-term planned WPs land

Mapping planned parity work (see the three parity plans) to the proposed IA so nav
does not regrow flat:

| Planned WP | Persona | Lands under | Notes |
| --- | --- | --- | --- |
| scite WP6 — grounded Assistant (RAG QA) | A/D | **Explore ▸ Ask** (own page) | DECIDED §5.1: own destination + "Ask about these results" bridge from Search. Reuses WP2 retrieval + `llm_client`; extended by biblio WP-B10. |
| scite WP7 — Reference Check | A/B | Paper detail action | Per-paper; lives on `/papers/:id`, not nav. |
| bibliometrix WP-B3 — network matrices (co-citation/coupling/co-word) | D | Explore ▸ Network (new tabs) | Reuses D3 renderer + `discovery.py` coupling. |
| bibliometrix WP-B4 — conceptual structure / thematic map | D | Explore ▸ Analytics (new tab) | Heaviest (NLP). |
| bibliometrix WP-B5 — historiograph + RPYS | D | Explore ▸ Network/Analytics | a11y table fallback required. |
| bibliometrix WP-B6 — multi-db import + completeness | C/D | Submit / Collections import | Extends scite WP9 import (+OpenAlex); unblocks country metrics (J4 gap). |
| bibliometrix WP-B7 — PRISMA / cohort provenance | D | Workspaces ▸ Collection | Provenance of a review cohort. |
| bibliometrix WP-B8 — corpus report + Three-Field Sankey | D | Explore ▸ Analytics (report tab) | Corpus-level lift of scite WP3. |
| bibliometrix WP-B9 — life-cycle logistic model | D | Explore ▸ Analytics | |
| bibliometrix WP-B10 — Biblio-AI narration | D | Assistant | Extends scite WP6. |
| litmaps WP-L6 — Zotero import | C/D | Submit / Collections import | Extends scite WP9. |

Takeaway: with the grouped IA, **none** of these need a new top-nav slot — they slot
into Explore/Workspaces/Submit or a paper action.

### 5.1 DECISION ANALYSIS: Assistant (scite WP6) — search mode vs. own page

The grounded Q&A Assistant reuses WP2 retrieval + `llm_client`. Two placements:

**Option A — a mode of Search** (a toggle on `/search`, e.g. "Keyword | Ask"):

- Pros:
  - Reinforces the search-first product identity; one obvious place to "ask the
    corpus a question," no new nav slot.
  - Shares state with search: the same cohort (§4.3), facets, and result cards; an
    answer can cite the very claims the user is already filtering.
  - Lower discovery cost — users already start at Search (Home hero → `/search`).
  - Cheaper to build: reuses `SearchPage` layout, facet panel, and result-card
    provenance rendering.
- Cons:
  - Conflates two interaction models (deterministic keyword retrieval vs. generative
    answer) on one screen; risk of users trusting a generated answer as if it were a
    keyword result.
  - `/search` is already dense (facets + result network + cards); adding a
    conversational surface strains the layout and a11y focus order.
  - Harder to give a conversation its own shareable URL / history.

**Option B — its own destination** (e.g. Explore ▸ Ask, route `/ask`):

- Pros:
  - Clean separation: a purpose-built surface for question → grounded answer with
    inline citations, abstention, and "show the evidence" drill-down — the exact
    place to enforce provenance-first framing.
  - Room to grow into WP-B10 (Biblio-AI narration) and multi-turn history without
    crowding Search.
  - Each answer/conversation can own a URL for sharing and monitoring.
  - Clearer trust boundary: users know they are in "generated, cite-checked" mode,
    not "literal keyword matches."
- Cons:
  - Another destination to discover and maintain; risks fragmenting "find things"
    into two doors (Search vs. Ask).
  - Must re-plumb cohort/facet context so an Ask can be scoped to the same work-set
    the user was searching (mitigated once §4.3 cohort routing exists).
  - Slightly more build (its own page, empty state, history).

**Recommendation:** **Option B (own destination under Explore ▾), with a bridge from
Search.** The provenance-first, abstention-capable Assistant deserves a surface that
makes its trust boundary explicit and has room for WP-B10 — but add an "Ask about
these results" button on `/search` that opens `/ask` pre-scoped to the current
cohort, so we keep the search-first entry point without conflating deterministic and
generative results on one screen. This is only clean once §4.3 cohort routing exists,
reinforcing the decision to build cohort first. (Not scheduled here; captured for
when scite WP6 is picked up.)

---

## 6. Recommended next steps (implementation, separate WPs)

Ordered by leverage; each is its own change, none included in this doc.

1. **UX-1 — Nav restructure (§4.1). ✅ DONE.** Refactored
   [`AppShell.tsx`](../frontend/src/components/AppShell.tsx) from a flat list into the
   grouped nav (Search / Explore ▾ / Workspaces ▾ / Submit / Review / Account) using
   USWDS `NavDropDownButton` + `Menu`. The Network explorer (`/graph`) now lives under
   Explore (fixes G2 orphan); Review is gated to reviewer/admin in the nav to match its
   route. Added `AppShell.test.tsx`; updated `docs/ui-design.md` §5 IA.
2. **UX-2 — Cohort cross-links (§4.2, G2–G3). ◑ PARTIAL — the safe, no-plumbing
   wins landed.** Shipped: (G3) a "Grow this collection" discovery action on
   [`CollectionDetailPage`](../frontend/src/pages/CollectionDetailPage.tsx) — seeds
   `POST /v1/discovery/seeds` with up to 25 of the collection's members (seeds travel
   in the request body, so no URL-length limit); `RelatedWork` was generalized to
   accept a `seedWorkIds` cohort. (G2) an "Open in the full network explorer →" link
   from the focused search result. **Deferred to UX-3:** the "Analyze this
   collection/map" and whole-cohort "Explore as network" buttons — these need a work
   set passed by *reference* (`?collection=` / `?map=`), because inlining hundreds of
   `work_ids` in a URL breaks, and the Analytics/Graph pages don't yet forward a
   cohort. That plumbing IS UX-3, so those buttons ship there **(now shipped — see
   UX-3).**
3. **UX-3 — Cohort as a routable concept (§4.3, G1/G4). ✅ DONE.** Backend: the four
   `/v1/bibliometrics/*` endpoints and a new `GET /v1/collections/{id}/graph` accept a
   cohort *by reference* — `?collection=` / `?map=` resolved server-side to the
   owner's member work set (owner-scoped: `401` anon, `404` non-owner) via a new
   optional-principal dependency that keeps the reads open otherwise. Frontend:
   Analytics forwards the cohort to every tab and shows an "Analyzing a saved
   collection/map" banner with a way back to the full corpus; GraphPage renders
   `?collection=` (alongside the existing `?map=`) cohorts; the UX-2-deferred "Analyze
   these papers" + "Explore as network" buttons now ship on the collection page, and
   each saved map gets an "Analyze" link. Every future bibliometric WP inherits cohort
   selection.
4. **UX-4 — Journey coverage in the story doc. ✅ DONE.** Added Persona D and a new
   corpus-exploration epic (US-7.1–7.5, covering journeys J2–J4/J7) to
   [`docs/ui-design.md`](../docs/ui-design.md) §2/§8, plus an a11y principle that
   every visualization ships a synced non-canvas table; reconciled the stale
   "deferred: semantic search / network viz" and "side nav" notes with what shipped.
5. **Backlog — shared saved-set base.** The open question across all three parity
   plans (unify Collection / Map / Corpus membership) is the same as G4 at the data
   layer. UX-3 deliberately ships FIRST over the existing `work_ids` API so the UI
   cohort contract is stable; this table unification then lands underneath without
   changing that contract. Sequence before the heavier bibliometric network/thematic
   WPs but after UX-3.

---

## 7. Decisions & remaining open questions

**Resolved (2026-07-23):**
- **Persona D is a first-class target user** (§2) — Analytics/Graph become primary
  surfaces; the bibliometrix track is in-scope product work.
- **"Cohort" is committed as a first-class routable concept** (§4.3), built now via
  UX-3 over the existing `work_ids` API, ahead of the bibliometric network/thematic
  WPs.
- **Assistant (scite WP6) → its own destination under Explore ▾, with an "Ask about
  these results" bridge from Search** (§5.1). Depends on cohort routing (UX-3).
- **Nav mechanism = USWDS dropdown top-nav** (`PrimaryNav` + `NavDropDownButton`
  submenus), not a sidebar (§4.1). Unblocks UX-1.

**Still open:**
1. Naming for the Assistant destination in the nav ("Ask" vs. "Assistant" vs.
   "Q&A") — cosmetic, decide when scite WP6 is scheduled.
