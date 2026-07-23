# InterCiter — UI Design & User Stories

Status: **implemented (MVP)**. This document planned InterCiter's first user
interface and now records what was built. It is written to the same standard as
the other design docs: it states constraints, weighs options explicitly, and
captures user stories so coverage is checkable. The MVP frontend now exists under
`frontend/` and implements the screens and stories below; see
[Implementation status](#implementation-status).

The UI is a client of the existing `/v1` API ([api.md](api.md)); it renders and
collects, it never becomes a second system of record. Everything a screen shows
must be traceable to an API response, and every write goes back through the API.

## Implementation status

The MVP UI is built and runs against the API: a **React + TypeScript + Vite** SPA
using **USWDS** via `@trussworks/react-uswds` (`frontend/`). All eleven screens are
live against `/v1` — home, login, papers list, paper detail, **claim detail**
(claim beside its verbatim passage with the span highlighted, one-hop relations
with function/stance as separate tags and explicit abstention, decomposed score
chips, provenance on demand), ingest, job (polling), extraction run, review
(triage queue + revise / review-decision / clusters), cluster (with reviewer
soft-remove), and account (self view + admin user management).

Auth is the BFF session cookie with CSRF (§11); reads stay open, writes are gated.
Accessibility is built in (USWDS components, skip-nav, gov banner, route-change
focus). A Vitest + React Testing Library suite covers the evidence highlighter,
score chips, relation/abstention rendering, and the CSRF client behavior.

A few endpoints were added to the API this session to support the reader and
reviewer flows: `GET /v1/papers` (list), `GET /v1/claims/{id}/clusters`, the BFF
session endpoints (`POST /v1/auth/login|logout`, `GET /v1/auth/csrf`), and account
management (`GET /v1/users`, `PATCH /v1/users/{id}`, `POST /v1/users/{id}/rotate-token`).
See [api.md](api.md).

Run it locally: `make be-serve` (API, cookies non-Secure for http dev) and
`make fe-dev` (SPA on :5173, proxying `/v1`); seed data with `make be-seed`.

---

## 1. Constraints that shape every decision

Three constraints drive the entire design. If a UI choice violates one of these,
it is wrong regardless of how convenient it is.

1. **Provenance-first** ([data-model.md](data-model.md)). What a paper *says*
   (`ClaimOccurrence`) is distinct from what a model *thinks it means*
   (`ClaimInterpretation`). The UI must never blur the two, never present a
   model inference as if it were the paper's words, and never show a claim it
   cannot anchor to a verbatim passage in the same view. Uncertainty is shown by
   **abstention** (`unresolved`), never hidden behind a confident-looking number.

2. **Government accessibility (USWDS / Section 508)**. The interface must use the
   [U.S. Web Design System](https://designsystem.digital.gov/) and meet WCAG 2.0
   AA / Section 508. This is a hard requirement, not a preference — it decides the
   component library (§3) and rules out ad-hoc component kits.

3. **API-first, read-projection default** ([architecture.md](architecture.md)).
   The default read representation is the *composed, reader-friendly view*; the
   full audit structure sits behind explicit "show evidence / show provenance"
   affordances. The UI mirrors this: readable by default, auditable on demand.

**Non-goals for the first UI.** Deep (multi-hop) graph traversal, semantic
search, reference-drafting, network visualization, and user-trust scoring are all
phase-2 API surface ([api.md](api.md) §Phase 2) and are out of scope here.

---

## 2. Users & personas

The MVP UI serves two primary personas. A third (operator) is supported minimally
because ingestion has to happen somewhere, but it is not the focus.

### Persona A — Reader / Explorer (primary)
A biomedical researcher who wants to understand a paper's empirical claims and
where they came from. They do not care about occurrence-vs-interpretation
mechanics; they want: *"What does this paper claim, exactly what sentence backs
it, who does it cite for it, and does that cited work actually support it?"*
They mostly **read**. They should never have to understand the data model to get
value.

### Persona B — Reviewer / Curator (primary)
A domain expert (or the team) auditing model output. They triage extractions,
correct interpretations, accept or reject cluster memberships and relation
assertions, and record rationale. Every action they take is **additive and
attributed** — nothing is destroyed, decisions are `ReviewDecision` overlays and
revisions are new records with parents ([scoring-and-review.md](scoring-and-review.md)).
Requires `reviewer` or `admin` role.

### Persona C — Ingestion operator (secondary)
Submits a paper (DOI / PMID / open-access XML), watches the job, and — for
evaluation — triggers a re-extraction or compares extractors. Any authenticated
user can submit; this persona is thin in the MVP.

---

## 3. Frontend stack — options, tradeoffs, recommendation

Because USWDS is mandatory, the real question is *how* we consume USWDS, not
whether. USWDS ships as framework-agnostic HTML/CSS + vanilla JS (Sass tokens,
`.usa-*` BEM classes, small JS behaviors for interactive components like combo
box, modal, accordion). We can consume it four ways.

### Option 1 — React + TypeScript + Vite + `@trussworks/react-uswds`  ✅ recommended
A single-page app calling the FastAPI `/v1`, using the Trussworks React component
library (USWDS 3.x React bindings; actively maintained, TypeScript-native,
Vite-based, used in production across DOL, CDC/ReportStream, CMS/EASi,
login.gov-adjacent projects, vote.gov, search.gov).

**Pros**
- USWDS components come pre-wrapped as accessible React components — the JS
  behaviors (combo box, modal focus-trap, date picker) are handled for you, so we
  don't hand-wire USWDS vanilla JS into React lifecycles.
- Strong fit for the *interactive, stateful* screens this app needs (evidence
  drawers, inline revision editors, review queues, optimistic writes).
- TypeScript end-to-end; we can generate a typed API client from the FastAPI
  OpenAPI schema and get compile-time safety against the `/v1` contract.
- Vite = fast dev loop, simple build, static output deployable behind any web
  server or CDN.

**Cons**
- Two deployables (SPA + API) and a JS build step.
- `react-uswds` is community-maintained (Truss), not GSA-official — must track
  USWDS-version alignment (pin `uswds` and `@trussworks/react-uswds` together).
- SPA accessibility needs deliberate route-change focus management (solvable, but
  our responsibility).

### Option 2 — Next.js + `@trussworks/react-uswds`
Same component library, but with a React meta-framework (SSR/SSG, file routing).

**Pros**: server rendering → faster first paint and simpler SEO/perf story;
built-in routing; Nava and NASA ship USWDS Next.js starters.
**Cons**: heavier than we need — the app is behind auth, internal, and read-mostly;
SSR adds a Node server to operate and complicates talking to the Python API. The
routing/SSR benefits don't pay for themselves in an internal audit tool.

### Option 3 — SvelteKit (USWDS vanilla)
**Pros**: small, fast, less boilerplate.
**Cons**: **no mature USWDS component library** — we'd wire USWDS vanilla JS into
Svelte ourselves and own accessibility for every interactive component. For a
508-required project this is meaningful, avoidable risk. Not recommended.

### Option 4 — Server-rendered inside FastAPI (Jinja + HTMX + USWDS vanilla)
Templates rendered by FastAPI, USWDS CSS/JS included directly, HTMX for partial
updates. One deployable, no JS build.

**Pros**: simplest operationally; USWDS used exactly as documented; progressive
enhancement is natural; great for mostly-read screens.
**Cons**: the reviewer workflows (inline revision, evidence drawers synced to
selection, optimistic review actions) are genuinely interactive and get awkward in
HTMX; we'd hand-manage USWDS JS init and focus for those; no typed API client.

### Recommendation — DECIDED: Option 1

**Option 1 (React + TS + Vite + `@trussworks/react-uswds`) is the chosen stack.**
It satisfies the 508/USWDS requirement with the least accessibility risk
(components are pre-built and tested), matches the interactive nature of the
reviewer workflows, and lets us generate a typed client from the API contract we
already have. Option 4 (Jinja + HTMX) is retained only as a documented fallback if
operational simplicity ever outweighs the reviewer UX — the read-only screens would
port cleanly.

**Working assumptions (confirm during setup):** deploy the SPA as static assets;
talk to `/v1` **same-origin** (reverse-proxy) to avoid CORS; pin USWDS +
react-uswds versions together; generate the TS client from FastAPI's OpenAPI. Auth
and token handling are specified in §11.

---

## 4. Component system — USWDS mapping

The design maps every recurring UI element to a USWDS component so we stay inside
the system and inherit its accessibility.

| InterCiter element | USWDS component |
| --- | --- |
| App shell, banners | Header, Official gov banner, Footer, Side navigation |
| Paper / claim lists | Table (sortable), Card, Pagination |
| Claim ↔ evidence pairing | Summary box / Prose for verbatim text; Accordion for "show provenance" |
| Ingestion & auth forms | Form, Text input, Combo box, File input, Validation |
| Job / run status | Step indicator or Tag/badge + Alert; Process list for run stages |
| Function / stance / resolution labels | Tag (semantic color); **abstention rendered as an explicit "unresolved" tag, not empty** |
| Reviewer actions | Button (default/secondary/outline), Modal (confirm), Textarea (rationale) |
| Decomposed scores | Custom small "score chip" set built from USWDS tokens — **no single blended meter** |
| Notifications / errors | Alert (info/warning/error/success), Site alert |

Two things are **deliberately not** off-the-shelf USWDS and need custom (but
token-styled) components:

- **Evidence pane** — a passage viewer that highlights the exact `char_start`/
  `char_end` span of a claim inside its verbatim text. USWDS has no "annotated
  passage" component; we build one from USWDS typography + color tokens.
- **Score decomposition** — the named, per-component signal display. USWDS has no
  multi-signal indicator; we render each `ScoreComponent` as its own labeled chip
  with its `Assessment` provenance, honoring "never a blended scalar."

---

## 5. Information architecture (routes)

The primary nav is grouped by user goal rather than one flat list — see
[UX journeys & IA redesign](../plans/ux-journeys.md) §4 for the rationale. The top
nav is: **Search · Explore ▾ · Workspaces ▾ · Submit · Review\* · Account**, where
the two `▾` items are USWDS `PrimaryNav` dropdowns:

- **Explore ▾** (open): Papers · Network explorer · Analytics
- **Workspaces ▾** (auth): Collections · Maps · Alerts

Full route map:

```
/                         Home: search hero + example explorations
/search                   Claim full-text search + facets + result network
/analytics                Corpus bibliometrics (Overview/Authors/Sources/Countries)
/papers                   Paper list (availability_state, filters)
/papers/:workId           Paper detail: metadata, claims, citation tallies, integrity
/papers/:workId/report    Paper citation report (timeline, facets)
/papers/:workId/claims/:claimId   Claim detail (the core screen)
/claims/:claimId          Standalone claim detail (links from relations/traces)
/graph                    Network explorer (papers/claims, axis layouts, ROBOKOP)
/graph/papers/:workId     Network explorer centered on a paper
/shared/:token            Public read-only shared map
/ingest                   Submit a paper (DOI/PMID/XML) + idempotency key
/jobs/:jobId              Job status (poll) → link to run / paper on success
/runs/:runId              Extraction-run provenance (model, prompt, params, code rev)
/review                   Reviewer queue (role-gated): triage, clusters, stale assertions
/clusters/:clusterId      Cluster detail: memberships, conflicting-stance surfacing
/collections              Collections list (auth)
/collections/:id          Collection detail: watch, import, integrity, CSV export
/maps                     Saved maps: open in graph, share, monitor (auth)
/alerts                   Saved searches + alert feed (auth)
/account                  Current user (GET /v1/users/me); admin: user management
```

\* Review appears in the nav only for `reviewer`/`admin` (admin implies reviewer).

Route-change focus management (move focus to the new page's `<h1>`) is a required
accessibility behavior for the SPA.

---

## 6. Key screens & data flow

Each screen names the `/v1` endpoints it consumes so the plan is checkable against
the real contract.

### 6.1 Claim detail — the core screen
The screen that proves the thesis. Layout: claim text on the left, **evidence pane
pinned alongside it** (never behind a click for the primary passage), relations
below, decomposed scores in a side rail.

- `GET /v1/claims/:id` → composed `ClaimView` (`normalized_text`, `evidence` with
  `verbatim_text` + `char_start/end`, `work_id`, `occurrence_id`,
  `interpretation_id`).
- `GET /v1/claims/:id/relationships` → one-hop `RelationAssertion`s; render each
  with **function** and **stance** as separate tags, **resolution** state, and a
  `target_link_score`. `paper_resolved` hops are labeled as reaching the *paper*,
  never shown as a claim-level continuation.
- `GET /v1/claims/:id/scores` → decomposed `ScoreComponent`s, each its own chip.
- "Show provenance" accordion reveals audit views:
  `GET /v1/claim-occurrences/:id`, `/v1/claim-interpretations/:id`,
  `/v1/passages/:id`, `/v1/extraction-runs/:id`.

**Provenance-first rules on this screen:** the verbatim passage is always visible
next to the normalized claim; `unresolved` relations render as an explicit state
with a reason, not omission; scores never collapse into one number.

### 6.2 Paper detail
- `GET /v1/papers/:id` (metadata + `availability_state` badge),
  `GET /v1/papers/:id/versions` (preprint / published / correction),
  `GET /v1/papers/:id/claims` (claim table → claim detail).

### 6.3 Ingest + job
- `POST /v1/papers` (DOI/PMID/XML + `idempotency_key`) → `202` + `JobView`;
  poll `GET /v1/jobs/:jobId`; on success link to `runId` and `workId`.
- Evaluation-only: `POST /v1/papers/:id/extractions` (choose model),
  `GET /v1/extraction-runs/:runId`.

### 6.4 Reviewer workspace (role-gated)
- Triage claims/relations; open evidence; then act:
  - Revise: `POST /v1/claim-interpretations/:id/revisions` → response lists
    `staled_assertion_ids`; the UI must **surface those as newly
    `stale_pending_review`**, not swallow them.
  - Record decision: `POST /v1/review-decisions` (per-dimension label + rationale;
    rationale strongly encouraged).
  - Clusters: `GET /v1/clusters/:id` (show `conflicting_stances` explicitly);
    `DELETE /v1/clusters/:id/members/:interpretationId` (sets `removed`,
    destroys nothing) behind a confirm Modal.
- Identity/authorship comes from the authenticated principal, never a form field
  ([architecture.md] auth).

### 6.5 Account / admin
- `GET /v1/users/me`; admin-only `POST /v1/users` (token shown **once**, in a
  copy-to-clipboard Alert, with a "you will not see this again" warning).

---

## 7. Cross-cutting UX principles

- **Evidence is never more than one interaction away, and usually zero.** The
  primary passage is co-visible with the claim.
- **Abstention is a first-class visual state.** `unresolved`, empty
  `target_interpretation_id`, or a low-confidence link renders as a labeled
  "unresolved / abstained" tag with a short reason — the model declining is a
  feature to show, not a gap to hide.
- **No blended scalar, ever.** Scores are shown as named components with their
  `Assessment` provenance. There is no single 0–100 "confidence."
- **Writes are additive and attributed.** Revisions create new records with
  parents; reviews are overlays; cluster removal sets status. The UI language
  reflects this ("Revise" / "Record decision" / "Remove membership"), never
  "Edit" or "Delete" of scientific assertions.
- **Occurrence ≠ interpretation in the type system → ≠ in the UI.** Verbatim text
  is visually distinct (quoted/monospace-ish, labeled "as written") from
  normalized/model text (labeled "interpretation").
- **Loading, empty, error, and abstained are all designed states**, each using the
  appropriate USWDS Alert/skeleton, not spinners-only.

---

## 8. User stories

Format: *As a &lt;persona&gt;, I want &lt;capability&gt;, so that &lt;value&gt;.*
Each story lists acceptance criteria (AC). Stories are grouped by epic; the
**MVP** tag marks first-cut scope, **P2** marks phase-2.

### Epic 1 — Read a paper's claims (Reader)

**US-1.1 (MVP)** As a Reader, I want to see a paper's metadata and availability
state, so that I know what I'm looking at and whether full text was extracted.
- AC: title, authors, venue, year, DOI/PMID shown; `availability_state` rendered
  as a labeled tag; if `ingestion_failed`, an Alert explains and offers retry.

**US-1.2 (MVP)** As a Reader, I want a list of the paper's empirical claims, so
that I can scan what it asserts.
- AC: claims from `GET /v1/papers/:id/claims` in a sortable Table; each row shows
  normalized text + a source-section hint; row links to claim detail.

**US-1.3 (MVP)** As a Reader, I want each claim shown next to the exact sentence
that backs it, so that I can trust it came from the paper.
- AC: claim detail shows `normalized_text` and the `evidence.verbatim_text` side
  by side; the `char_start/char_end` span is visually highlighted within the
  passage; verbatim vs normalized are visually and textually labeled.

**US-1.4 (MVP)** As a Reader, I want to see who a claim cites and how, so that I
can judge the citation.
- AC: relationships list shows function and stance as separate tags, resolution
  state, and target-link score; a `support`/`contradict`/`neutral` stance is never
  merged with function.

**US-1.5 (MVP)** As a Reader, I want to follow one hop to the cited work or matched
claim, so that I can check the antecedent.
- AC: a resolved hop links to the cited paper or target claim; a `paper_resolved`
  hop is labeled "resolved to paper (not a specific claim)" and does not pretend to
  be a claim-level match.

**US-1.6 (MVP)** As a Reader, I want to see when the system abstained, so that I'm
not misled by false precision.
- AC: `unresolved` relations and missing targets render as an explicit
  "unresolved / abstained" state with a short reason; they are counted, not hidden.

**US-1.7 (MVP)** As a Reader, I want the decomposed confidence signals for a claim,
so that I understand *why* it's uncertain rather than trusting one number.
- AC: `GET /v1/claims/:id/scores` components each render as a labeled chip with
  value and, on request, `Assessment` provenance; there is no blended scalar.

**US-1.8 (MVP)** As a Reader, I want to open the full provenance of a claim, so
that I can audit the extraction.
- AC: a "show provenance" affordance reveals occurrence, interpretation, passage,
  and extraction-run records (model, prompt version, params, code revision).

### Epic 2 — Ingest & jobs (Operator)

**US-2.1 (MVP)** As an Operator, I want to submit a paper by DOI, PMID, or
open-access XML, so that the system can extract it.
- AC: `POST /v1/papers` from a validated form; returns a job; validation errors
  use USWDS field validation.

**US-2.2 (MVP)** As an Operator, I want retries to be safe, so that I don't
double-ingest.
- AC: an `idempotency_key` is sent; resubmitting the same key surfaces the existing
  job rather than creating a duplicate.

**US-2.3 (MVP)** As an Operator, I want to watch a job to completion, so that I know
when results are ready.
- AC: job page polls `GET /v1/jobs/:jobId`; shows status transitions and, on
  success, links to the run and paper; on failure shows the error in an Alert.

**US-2.4 (P2/eval)** As an Operator, I want to trigger a re-extraction with a
chosen model, so that I can compare extractors.
- AC: `POST /v1/papers/:id/extractions` with model selection; new run appears and
  is comparable to prior runs.

### Epic 3 — Review & curate (Reviewer)

**US-3.1 (MVP)** As a Reviewer, I want a queue of items needing attention, so that
I can triage efficiently.
- AC: role-gated `/review`; lists low-confidence / unresolved / `stale_pending_review`
  items with evidence one click away.

**US-3.2 (MVP)** As a Reviewer, I want to revise an interpretation, so that I can
correct the model without destroying its record.
- AC: `POST /v1/claim-interpretations/:id/revisions` creates a new interpretation
  with the old as parent; UI shows both versions; author/reviewer/admin only.

**US-3.3 (MVP)** As a Reviewer, I want to see which assertions my revision
invalidated, so that nothing silently goes stale.
- AC: the revision response's `staled_assertion_ids` are surfaced as
  `stale_pending_review`, with links to each.

**US-3.4 (MVP)** As a Reviewer, I want to record a per-dimension decision with
rationale, so that judgments are attributable and auditable.
- AC: `POST /v1/review-decisions` captures subject, dimension, label, rationale;
  reviewer identity comes from the principal; decisions are additive overlays.

**US-3.5 (MVP)** As a Reviewer, I want to see a cluster's members and any
conflicting stances, so that I can spot bad groupings.
- AC: `GET /v1/clusters/:id` shows memberships with method + confidence;
  `conflicting_stances` is surfaced prominently.

**US-3.6 (MVP)** As a Reviewer, I want to remove a bad cluster membership, so that
the grouping is trustworthy — without destroying data.
- AC: `DELETE /v1/clusters/:id/members/:interpretationId` behind a confirm Modal;
  status becomes `removed`; the record persists and is still visible as removed.

**US-3.7 (MVP)** As a Reviewer, I want to author a human claim when the model
missed one, so that coverage isn't limited to extraction.
- AC: `POST /v1/claims` with text anchored to an existing passage/occurrence;
  the human origin is recorded and shown.

### Epic 4 — Identity & access

**US-4.1 (MVP)** As any user, I want to sign in with my API token, so that my
actions are attributed.
- AC: token auth against `/v1`; `GET /v1/users/me` populates the account view;
  reviewer/admin-only UI is hidden/blocked for plain users.

**US-4.2 (MVP)** As an Admin, I want to create users, so that I can onboard
reviewers.
- AC: `POST /v1/users`; the raw token is shown exactly once with a copy control and
  a clear "won't be shown again" warning.

### Epic 5 — Accessibility & trust (cross-cutting)

**US-5.1 (MVP)** As a keyboard-only or screen-reader user, I want full parity, so
that I can use every workflow.
- AC: all flows operable via keyboard; USWDS components used for interactive
  elements; SPA moves focus to the page `<h1>` on route change; axe-core checks in
  CI show no serious/critical violations.

**US-5.2 (MVP)** As any user, I want the official gov banner and clear affordances,
so that the site meets federal presentation standards.
- AC: USWDS Header with gov banner and Footer present; color/typography from USWDS
  tokens; contrast meets WCAG 2.0 AA.

**US-5.3 (MVP)** As any user, I want honest loading/empty/error states, so that the
UI never fakes certainty.
- AC: each data view has designed loading, empty, error, and abstained states using
  USWDS Alerts/skeletons.

### Epic 6 — Deferred (P2, listed for coverage)
Semantic search (`POST /v1/search`), reference drafting (`POST /v1/references`),
multi-hop bounded traversal (`GET /v1/traces`), network visualization
(`GET /v1/networks`), and user-trust/paper-trust scoring — all deferred to phase 2
per [api.md](api.md). Called out here only so the MVP boundary is explicit.

---

## 9. Suggested MVP cut

1. App shell (USWDS header/banner/footer, side nav), auth, `/account`.
2. Ingest + job polling (US-2.1–2.3).
3. Paper list + paper detail (US-1.1–1.2).
4. **Claim detail with pinned evidence, relations, one-hop, decomposed scores,
   abstention states** (US-1.3–1.8) — the highest-value screen; build it first
   after the shell if forced to choose.
5. Reviewer workspace: revise + review-decision + stale surfacing + clusters
   (US-3.1–3.6).

Accessibility (Epic 5) is not a phase — it is an acceptance criterion on every
story above.

---

## 10. Open questions

1. **Deployment / same-origin.** Serve the SPA static and reverse-proxy `/v1`
   same-origin (no CORS), or separate hosts with CORS? (Recommend same-origin.)
2. **Typed client.** Generate a TypeScript client from FastAPI's OpenAPI, or
   hand-write a thin fetch layer? (Recommend generated.)
3. **Auth / token storage.** DECIDED — see §11 (BFF + `HttpOnly` session cookie;
   raw token never stored in the browser). Remaining work is the backend session
   layer, not a UI decision.
4. **Reviewer role bootstrapping.** How reviewers get provisioned in practice
   (admin UI vs CLI `interciter useradd`).
5. **Passage highlighting fidelity.** Confirm `char_start/char_end` are reliably
   present and correct across parsers for the evidence highlighter.
6. ~~Confirm Option 1 vs Option 4.~~ DECIDED — Option 1 (§3).

---

## 11. Authentication & token storage

The stack is a browser SPA (§3), so *where a credential lives in the browser* is a
security decision governed by federal guidance, not a convenience choice.

**Governing requirements.** OMB **M-22-09** (Federal Zero Trust — centralize
identity, avoid scattering long-lived secrets), NIST **SP 800-63B** (session
management, bearer-token protection, AAL2 reauthentication timeouts), NIST
**SP 800-53** (SC-8 TLS in transit, SC-23 session authenticity, AC-11 session lock,
AC-12 session termination), and OWASP's *OAuth 2.0 for Browser-Based Apps* BCP.

### Options considered

| Option | Federal fit | Rationale |
| --- | --- | --- |
| `localStorage` | ❌ Discouraged | JS-readable and persistent → any XSS exfiltrates a long-lived bearer token. OWASP advises against token storage here. |
| `sessionStorage` | ❌ Discouraged | Same XSS exposure; only clears on tab close. |
| In-memory only (React state/closure) | ⚠️ Acceptable, not alone | Best XSS-persistence posture (nothing survives reload) but lost on refresh → needs silent re-auth; weak UX by itself. |
| `HttpOnly` + `Secure` + `SameSite` cookie (opaque session id) | ✅ Strong | Not readable by JS, so XSS can't steal it; needs CSRF defense (`SameSite=Strict`/`Lax` + CSRF token) and TLS. |
| **BFF (Backend-for-Frontend)** | ✅✅ **Chosen** | The API/OAuth token **never reaches the browser**; a thin server-side session holds it and exposes only an `HttpOnly` cookie to the SPA. Best zero-trust alignment. |

### Decision

**BFF + `HttpOnly; Secure; SameSite=Strict` session cookie.** This fits the
same-origin reverse-proxy from §3: the SPA authenticates once, the server keeps
InterCiter's bearer token (already stored only as a SHA-256 hash) server-side, and
the browser holds only an opaque session cookie it cannot read. Add CSRF protection
(token + `SameSite`), require TLS end-to-end, and enforce 800-63B session policy
(≈30-minute idle timeout, ≈12-hour absolute reauthentication, explicit logout that
invalidates the server-side session).

**Explicitly rejected:** pasting the raw API token into the SPA and persisting it in
`localStorage`/`sessionStorage`.

### Backend impact (flagged for planning)

### Backend impact (implemented)

The BFF session layer is built in the backend:
- `POST /v1/auth/login` exchanges a raw API token (sent once) for the session;
  sets `interciter_session` (`HttpOnly`) + a readable `interciter_csrf` cookie.
- `POST /v1/auth/logout` revokes the server-side session and clears cookies;
  `GET /v1/auth/csrf` lets the SPA recover its CSRF token after a reload.
- Cookie auth is accepted **alongside** the existing `Authorization: Bearer`
  header (CLI/API clients unchanged; bearer takes precedence, no CSRF).
- Unsafe cookie-authenticated methods require a matching `X-CSRF-Token` header
  (double-submit against the session's token).
- Server-side session store (`app_session`) with sliding idle + absolute expiry
  (`INTERCITER_SESSION_*` settings) and logout/deactivation invalidation.

Account management (Epic 4) is also implemented: `is_active` on users;
`GET /v1/users`, `PATCH /v1/users/{id}` (role / activation),
`POST /v1/users/{id}/rotate-token`; CLI `userlist` / `usermod` / `userrotate`;
a last-active-admin guard prevents self-lockout.

### Long-term direction

Replace token-paste entirely with **agency SSO / login.gov via OIDC + PIV/CAC** for
phishing-resistant MFA (M-22-09). The BFF session boundary above is designed so
that swap changes *how the server obtains identity*, not how the browser holds a
session — the SPA keeps talking to the same `HttpOnly` cookie throughout.
