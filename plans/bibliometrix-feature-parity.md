# bibliometrix Feature-Parity Plan

Status: DRAFT — planning artifact for subagent execution
Source: https://github.com/massimoaria/bibliometrix + https://www.bibliometrix.org
(README + biblioshiny feature list), captured 2026-07-23
Owner: (assign)

This document (1) catalogs the bibliometrix / biblioshiny features we want to
replicate, (2) maps each to InterCiter's existing capabilities, and (3) breaks the
gap into discrete, subagent-ready work packages (WPs). Companion to
`plans/scite-feature-parity.md` and `plans/litmaps-feature-parity.md` — shared work
packages are cross-referenced to avoid duplication.

InterCiter differentiators to preserve while replicating bibliometrix:
- Provenance-first (verbatim spans), decomposed scores, explicit abstention.
- Function and stance are SEPARATE dimensions (this IS bibliometrix's "citation
  function analysis", and InterCiter already ships it at claim granularity).
- LinkML-first schema changes; reads open / writes require auth + CSRF.
- USWDS / Section-508 UI (a11y non-canvas fallbacks for EVERY visualization —
  networks, thematic maps, Sankey diagrams, spectrograms all need a synced table).

## 0. The fundamental framing difference (read first)

bibliometrix is a **corpus-level, metadata-driven science-mapping** toolkit: it
ingests a bibliographic dataset (WoS/Scopus/OpenAlex/etc.) and produces aggregate
descriptive statistics + knowledge-structure maps (conceptual / intellectual /
social) over the *whole collection's metadata* (authors, keywords, references,
affiliations, citation counts). It does NOT read or reason about the *content* of
claims — its "Content Analysis" is keyword/TF-IDF/citation-function tagging.

InterCiter is **claim-level, provenance-first evidence synthesis**: it extracts and
grounds individual scientific assertions with verbatim spans, separate function +
stance, decomposed scores, and explicit abstention.

Parity therefore means adding a **corpus-level analytics + science-mapping layer**
ON TOP of InterCiter's existing metadata (PaperWork, CitationEdge, authors, the
snowball corpus) — WITHOUT collapsing InterCiter's claim-level rigor into blended
metadata scores. bibliometrix's descriptive/aggregate lens complements, and does not
replace, InterCiter's evidence lens. Notably, InterCiter is already *ahead* of
bibliometrix on Content Analysis (real function+stance+provenance vs. keyword tags).

Bibliometrix organizes its workflow as **SAAS**: Search → Appraisal → Analysis →
Synthesis. The WPs below are grouped to align with that pipeline.

---

## 0b. Cross-plan status snapshot (all parity plans · updated 2026-07-23)

Three parity plans (`scite`, `litmaps`, `bibliometrix`) share one codebase; check
all three before starting a WP so shared work is built once.

Shipped to origin/main:
- scite: WP1 citation tallies · WP2 claim search · WP3 paper report · WP4
  collections (+ watch / delta / integrity / bulk) · WP5 retraction+integrity
  signal · WP8 saved searches + alerts · WP9 Zotero/Mendeley (RIS/BibTeX) import.
- litmaps: WP-L1 discovery · WP-L2 saved maps · WP-L3a/b/c D3 renderer + axis
  layouts + annotations · WP-L4 read-only map sharing · WP-L5 map monitoring.
- bibliometrix: WP-B1 corpus descriptive analytics + "Main Information" dashboard ·
  WP-B2 author/source/country analytics (h-index/Lotka/Bradford/SCP-MCP).

Not yet built:
- scite: WP6 grounded Assistant (RAG QA) · WP7 Reference Check.
- litmaps: WP-L6 Zotero seed import (extends the shipped scite WP9 importer).
- bibliometrix: WP-B3 … WP-B10.

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
1. scite WP6 grounded Assistant — high value; WP2 retrieval + LLM client already
   exist; later extended by bibliometrix WP-B10.
2. bibliometrix WP-B3 network matrices — co-citation / coupling / co-word /
   collaboration; REUSES the litmaps WP-L3 D3 renderer + discovery.py coupling,
   so cheap and high-impact.
3. scite WP7 Reference Check — reuses WP1 tallies + WP5 integrity over a paper's
   reference list (identifier intake first, PDF later).
4. litmaps WP-L6 / bibliometrix WP-B6 — layer Map-seed + WoS/Scopus/OpenAlex onto
   the shipped scite WP9 import core (also backfills WP-B2 affiliation/country).

---

## 1. Feature catalog & gap analysis

Legend: ✅ have · 🟡 partial · ⬜ missing

### B1. Data management — import & conversion (SAAS: Search)
bibliometrix: `convert2df` imports/normalizes exports from WoS, Scopus, PubMed,
OpenAlex, Cochrane CDSR, Lens.org, Dimensions (plaintext/BibTeX/CSV/JSON/XML);
direct API retrieval from OpenAlex + PubMed; merge collections across databases.

InterCiter mapping:
- ✅ Ingestion substrate: `ingestion/semantic_scholar.py`, `ingestion/pmc.py`,
  `ingestion/crossref.py`, S2 bulk datasets, `ingestion/snowball.py` (~1k-paper
  metadata+citation corpus).
- 🟡 JATS full-text ingest (`ingestion/parser.py`) + S2/PMC metadata. No importer
  for WoS/Scopus/Lens/Dimensions export formats, no RIS/BibTeX, no OpenAlex.
- ⬜ Multi-database export-file importer + reference-manager formats + OpenAlex API.

Gap: a `convert2df`-equivalent import layer (overlaps scite-parity WP9 Zotero/RIS
+ external-data OpenAlex). See WP-B6.

### B2. Data appraisal — quality, completeness, matching, PRISMA (SAAS: Appraisal)
bibliometrix: `missingData()` metadata-completeness report; `applyCitationMatching`
to reconcile citations across databases; `completeMetadata()` DOI-based enrichment
via OpenAlex; auto PRISMA flow diagram; filter by year/journal/country/citation.

InterCiter mapping:
- ✅ Non-destructive enrichment (`services/enrichment.py` backfills S2 metadata,
  never overwrites); Crossref integrity (`services/integrity.py`); citation
  reconciliation via `CitationEdge` + `enrichment.persist_reference_metadata`.
- 🟡 Filtering exists per-endpoint (search facets, report filters) but no corpus-
  level "cohort builder" with a documented inclusion/exclusion audit trail.
- ⬜ Metadata-completeness report; explicit citation-matching pass; PRISMA flow
  diagram; a first-class "dataset / cohort" object with provenance.

Gap: completeness report + PRISMA provenance (WP-B7); citation matching is largely
✅ via existing edges (surface it). Filtering → cohort concept.

### B3. Main Information dashboard + descriptive analytics (SAAS: Analysis)
bibliometrix: "Main Information" (timespan, #sources, #documents, annual growth
rate, avg citations/doc, #authors, co-authors/doc, international co-authorship %,
document types, keyword counts); annual scientific production; most productive
authors / sources / countries; most cited manuscripts.

InterCiter mapping:
- ✅ Raw substrate exists: PaperWork (year/venue/authors/citations), CitationEdge,
  RelationAssertion tallies (`services/citation_stats.py`).
- 🟡 `services/report.py` gives a per-PAPER report with citing timelines. No
  corpus-wide descriptive rollup.
- ⬜ Corpus "Main Information" summary + annual production + top authors/sources/
  countries/documents ranking.

Gap: `services/bibliometrics.py` descriptive rollup + dashboard. See WP-B1.

### B4. Three-level metrics: Sources / Authors / Documents (SAAS: Analysis)
bibliometrix: Sources (journal impact, Bradford's law, production over time);
Authors (productivity, h-index, Lotka's law, collaboration, OpenAlex author bios);
Documents (citation analysis, most-relevant, RPYS, trend topics).

InterCiter mapping:
- ✅ Author nodes (`_author_id` hash) + citation counts on paper nodes (WP-L3b).
- ⬜ No h-index / Lotka / Bradford laws; no author productivity or collaboration
  metrics; no country/affiliation analytics; no trend-topics-over-time.

Gap: author/source/country analytics (laws + impact indices). See WP-B2. Needs
affiliation/country metadata (schema addition).

### B5. Conceptual structure — co-word, thematic map, thematic evolution
bibliometrix: co-word co-occurrence networks; thematic map (strategic diagram:
centrality × density → motor / niche / emerging-declining / basic themes, Cobo
2011); thematic evolution over time (time-sliced Sankey); conceptual structure via
MCA / CA / MDS + k-means; NLP term extraction (TF-IDF, RAKE, YAKE) + stemming.

InterCiter mapping:
- ✅ Claims + grounded entities (`services/grounding.py`, ROBOKOP CURIEs) are a
  richer conceptual substrate than raw keywords.
- ⬜ No keyword/term extraction over the corpus, no co-word matrix, no thematic map
  or thematic evolution, no MCA/CA/MDS dimensionality reduction.

Gap: term extraction + co-word network + thematic map + thematic evolution. See
WP-B4. (Can seed terms from grounded entities/claims rather than raw keywords —
an InterCiter upgrade over keyword-only co-word analysis.)

### B6. Intellectual structure — co-citation, coupling, historiograph
bibliometrix: co-citation networks (document / author / source level); bibliographic
coupling; historiograph (Garfield chronological direct-citation network using Local
Citation Score); `biblioNetwork` builds coupling/co-citation/co-occurrence/
collaboration matrices at author/reference/source/country/keyword/title/abstract
levels; `networkPlot` with multiple layouts; RPYS (reference publication year
spectroscopy → Sleeping Beauties, Hot Papers, Constant Performers, Life Cycles).

InterCiter mapping:
- ✅ `CitationEdge` directed citation graph; `services/graph.py` neighborhoods +
  `graph_for_works`; `services/discovery.py` IS bibliographic coupling / co-
  reference ranking already; D3 `NetworkGraph` renderer w/ axis layouts (WP-L3).
- 🟡 Direct-citation graph exists; no co-citation matrix, no historiograph
  (chronological LCS network), no RPYS.
- ⬜ Co-citation networks (doc/author/source); historiograph; RPYS.

Gap: co-citation matrices + historiograph + RPYS, built on existing CitationEdge +
years. See WP-B3 (networks) + WP-B5 (historiograph + RPYS). Reuse the D3 renderer.

### B7. Social structure — collaboration networks + world map
bibliometrix: co-authorship networks at author / institution / country level;
interactive collaboration world map; SCP/MCP (single- vs multi-country pubs),
international co-authorship %.

InterCiter mapping:
- ✅ Author nodes + `authored` edges in `services/graph.py`.
- ⬜ No institution/country dimension; no collaboration metrics; no geographic map.

Gap: co-authorship networks + country collaboration + map. See WP-B2 (metrics) +
WP-B3 (networks). Country map needs affiliation/country metadata + an a11y-safe
choropleth (USWDS has no map component — table fallback mandatory).

### B8. Content analysis (citation function + in-context)
bibliometrix: citation function analysis (background / method / comparison /
critique); in-context citation analysis with citation windows; keyword/concept
extraction; word-frequency trends; IMRaD structural analysis; AI summaries.

InterCiter mapping:
- ✅✅ **InterCiter is AHEAD here.** Claims carry separate function + stance,
  verbatim provenance spans (the "in-context citation" done properly),
  section/IMRaD facets (`services/search.py`), decomposed scores, abstention.
- 🟡 No corpus-level word-frequency trend charts; no RAKE/YAKE/TF-IDF keyword
  extraction (grounded entities are the InterCiter analogue).

Gap: mostly ✅. Optional: corpus keyword/term-frequency trends (folds into WP-B4).
Do NOT regress claim-level rigor to match bibliometrix's coarser keyword tagging.

### B9. Life Cycle analysis
bibliometrix: `lifeCycle` fits a logistic growth model to annual publication counts
to classify a field's stage (emergence / rapid growth / maturity / saturation) and
forecast future production.

InterCiter mapping:
- ⬜ No temporal growth modeling.

Gap: logistic-growth life-cycle model + forecast. See WP-B9 (small, self-contained).

### B10. Synthesis — Biblio AI, reports, animated networks (SAAS: Synthesis)
bibliometrix: Biblio AI (interpret results, generate narratives/recommendations);
interactive Excel reports; Three-Field Plot (Sankey of 3 metadata fields); animated
diachronic networks.

InterCiter mapping:
- 🟡 scite-parity WP6 (grounded Assistant RAG QA) is the Biblio-AI analogue.
- 🟡 `ReportPage` (scite WP3) is per-paper, not corpus-level; no Excel export, no
  Three-Field Sankey, no animated networks.
- ⬜ Corpus report/export; Three-Field Plot; narrative AI over bibliometric outputs.

Gap: corpus report + Three-Field Plot (WP-B8); Biblio-AI narration → EXTEND scite
WP6 (WP-B10). Animated networks deferred (nice-to-have; a11y-hostile).

---

## 2. Overlap with existing parity plans (do NOT duplicate)
- Import connectors (B1) → scite-parity **WP9** (Zotero/Mendeley RIS/BibTeX) +
  external-data OpenAlex. B1 = extend WP9 to WoS/Scopus/Lens/Dimensions + OpenAlex
  API, and target a corpus/cohort (not just a Collection/Map).
- Assistant / Biblio AI (B10) → scite-parity **WP6** (grounded RAG QA). B10 = feed
  bibliometric rollups into WP6 as an additional grounded context source.
- Network rendering (B3/B5/B6/B7) → REUSE `components/NetworkGraph.tsx` (D3 SVG,
  post WP-L3) + `services/graph.py`. Do not add a second graph renderer.
- Bibliographic coupling (B6) → `services/discovery.py` already computes it; expose
  it as a network/matrix rather than re-deriving.
- Per-paper report (B10) → scite-parity **WP3** `services/report.py`; B8 lifts it
  to corpus level (shared DTOs/timeline buckets).
- Citation tallies (B3/B8) → scite-parity **WP1** `services/citation_stats.py`.

---

## 3. Priority & sequencing (bibliometrix-specific WPs)

These are NEW packages. Prereqs reference scite/litmaps WPs where shared. A shared
prerequisite is a **Corpus / cohort** concept (a named, filterable set of works the
analytics run over). Reuse the litmaps `Map` + scite `Collection` membership base if
one gets unified (see open questions); otherwise analytics can run over an ad-hoc
`work_ids` set or the whole DB, and adopt the cohort object when it lands.

Wave A — descriptive analytics foundation (unlocks everything, low risk, no NLP):
- WP-B1 Corpus descriptive analytics + "Main Information" dashboard (B3)
- WP-B2 Author / Source / Country analytics — laws + impact indices (B4/B7-metrics)

Wave B — knowledge-structure science mapping (reuses the D3 renderer):
- WP-B3 Bibliometric network matrices — co-citation / coupling / co-occurrence /
  collaboration (B6/B7-networks)
- WP-B5 Historiograph (LCS chronological network) + RPYS (B6)
- WP-B4 Conceptual structure — term extraction + co-word + thematic map + thematic
  evolution (B5) [heaviest; needs NLP]

Wave C — data pipeline + synthesis:
- WP-B6 Multi-database import + completeness report + citation matching (B1/B2) →
  extend scite WP9
- WP-B7 PRISMA flow diagram + cohort provenance (B2)
- WP-B8 Corpus report + Three-Field Plot + export (B10)
- WP-B9 Life Cycle logistic model (B9)
- WP-B10 Biblio-AI narration of bibliometric outputs (B10) → extend scite WP6

Rationale: WP-B1 (descriptive rollup) is the foundation every dashboard/report
reuses and needs no new schema or NLP — ship it first. WP-B2 adds the "laws" and
needs affiliation/country metadata (first schema touch). Networks (WP-B3/B5) reuse
the D3 renderer and existing CitationEdge, so they are cheap and high-impact.
Conceptual structure (WP-B4) is the heaviest (NLP + dimensionality reduction) — last
in Wave B. Wave C is the data-in / synthesis-out bookends.

---

## 4. Subagent-ready work packages

Follow repo conventions (see §5 checklist). Verify with `make be-test` +
`make fe-typecheck && make fe-test`. Update `docs/api.md`.

### WP-B1 — Corpus descriptive analytics + "Main Information"  (B3) — ✅ DONE
Goal: a corpus-wide descriptive summary (bibliometrix "Main Information" +
annual production + top authors/sources/countries/documents).

Shipped: `services/bibliometrics.py` `corpus_summary(session, *, work_ids=None,
min_year=None, max_year=None, top_k=10)` — derived/non-mutating projection over a
cohort (explicit `work_ids` else whole DB), year-filtered. Computes document/source/
author counts, author appearances + co-authors/doc + single-authored count, dense
annual-production series + compound annual growth rate, avg citations/doc + total
citations (global citation in-degree over distinct citing works, restricted to the
cohort), and top-k productive authors / sources / most-cited documents. Endpoint
`GET /v1/bibliometrics/summary` (reads OPEN; router `api/routers/bibliometrics.py`).
DTOs `BibliometricsSummary` + `AnnualProduction`/`AuthorProductivity`/
`SourceProductivity`/`CitedDocument` in `schemas.py` + `frontend/src/api/types.ts`.
Frontend `pages/AnalyticsPage.tsx` — "Main Information" indicator cards + annual-
production a11y table (aria-hidden bars) + top-k tables, year filter, public nav
"Analytics". Tests `tests/test_bibliometrics.py` (8: synthetic cohort math +
sample-corpus rollup + endpoint) + `pages/AnalyticsPage.test.tsx` (3). Deferred:
document-type + keyword counts (no such metadata yet); country column is WP-B2.

### WP-B2 — Author / Source / Country analytics (laws + indices)  (B4/B7) — ✅ DONE
Goal: h-index, Lotka's law (author productivity distribution), Bradford's law
(source zones), country SCP/MCP + international co-authorship %.

Shipped: additive LinkML slot `PaperWork.author_affiliations` (multivalued raw
affiliation strings; NOT a first-class Author/Authorship — hashed author names kept,
country parsed from affiliation tails). Regenerated (`make jsonschema`), mirrored in
`models.py` (JSON col default list). `services/bibliometrics.py` extended:
`author_metrics` (per-author document_count + total_citations + h-index over the
citation graph, + `_lotka_fit` OLS exponent/constant of the productivity
distribution), `source_metrics` (per-venue document_count/total_citations/h-index +
`_bradford_zone_map` three-zone partition), `country_metrics` (`_parse_country`
lexicon + alias heuristic over affiliation strings → SCP/MCP split + international
co-authorship %). Endpoints `GET /v1/bibliometrics/{authors,sources,countries}`
(reads OPEN; shared work_ids/min_year/max_year/top_k). Law fits use plain Python OLS
(NO numpy/scipy dep). DTOs (`AuthorMetrics`/`AuthorMetric`/`LotkaFit`/`LotkaPoint`,
`SourceMetrics`/`SourceMetric`/`BradfordZone`, `CountryMetrics`/`CountryMetric`) in
`schemas.py` + `types.ts`. Frontend `AnalyticsPage.tsx` refactored into tabs
(Overview / Authors / Sources / Countries via `?tab=`), each an a11y RankTable + law
summary; year filter shared across tabs. Tests `test_bibliometrics.py` (+7:
h-index, Lotka distribution, Bradford partition, SCP/MCP, empty-country, endpoints)
+ `AnalyticsPage.test.tsx` (+3 tab tests). Country analytics degrade to empty until
an affiliation-bearing importer (WP-B6 OpenAlex) populates `author_affiliations`.
Deferred: first-class Author/Authorship entity; country map (WP-B3).

### WP-B3 — Bibliometric network matrices  (B6/B7-networks)
Goal: co-citation / bibliographic-coupling / keyword co-occurrence / co-authorship
networks (bibliometrix `biblioNetwork` + `networkPlot`), rendered in the existing D3
`NetworkGraph`.
Backend: extend `services/graph.py` (or `services/bibliometrics.py`) with matrix
builders over a cohort: `co_citation_network` (references co-cited by the same
works — needs reference-level nodes from CitationEdge), `coupling_network` (reuse
`services/discovery.py` coupling scores → edges), `coword_network` (keyword/grounded-
entity co-occurrence), `collaboration_network` (co-authorship at author/country
level). Return the existing `GraphView` DTO so the renderer is unchanged. Normalize
edge weights (association/Salton) as node/edge `data`.
Frontend: AnalyticsPage "Networks" section — pick network type + level; render via
`NetworkGraph` (force or axis layout from WP-L3b); keep the a11y node/edge table in
sync (mandatory). No new renderer.
Tests: matrix construction (co-citation pair counts, coupling reuse, co-word counts)
on the sample corpus; GraphView shape; a11y table.
Deps: WP-B1; reuses litmaps WP-L3 renderer + scite WP1/discovery.

### WP-B4 — Conceptual structure: co-word + thematic map + thematic evolution  (B5)
Goal: co-word network → thematic map (centrality × density strategic diagram) →
thematic evolution (time-sliced Sankey).
Backend: term source = grounded entities/claims first (InterCiter upgrade), keywords
fallback. NEW `services/conceptual.py`: term extraction/normalization; co-word
matrix; Louvain/greedy clustering; per-cluster centrality (Callon external) +
density (internal) → quadrant classification (motor/niche/emerging-declining/basic);
thematic evolution across year slices with inclusion-index flows. (Defer MCA/CA/MDS —
factorial methods are a large numerical add; start with network + strategic diagram.)
Endpoints `GET /v1/conceptual/thematic-map` + `.../thematic-evolution` (cohort +
field + n + slices).
Frontend: AnalyticsPage "Conceptual structure" — thematic map (scatter of clusters
by centrality×density, quadrant-labeled) + a11y table of themes w/ metrics; thematic
evolution as an a11y-first flow table + optional Sankey (aria-hidden SVG, table is
source of truth).
Tests: co-word counts, quadrant classification thresholds, evolution flow inclusion
index on a fixture.
Deps: WP-B1, WP-B3. Heaviest WP (NLP + clustering) — schedule last in Wave B.

### WP-B5 — Historiograph + RPYS  (B6)
Goal: Garfield historiograph (chronological direct-citation network by Local
Citation Score) + Referenced Publication Year Spectroscopy.
Backend: extend `services/bibliometrics.py`. Historiograph: over a cohort, compute
Local Citation Score (in-cohort in-degree from CitationEdge), keep top-n, emit a
year-ordered `GraphView` (x=year axis layout reuses WP-L3b). RPYS: histogram of
cited-reference years + median-deviation sequence; classify references (Hot Paper /
Constant Performer / Life Cycle / Sleeping Beauty) from the citation-year sequence.
Endpoints `GET /v1/bibliometrics/{historiograph,rpys}`.
Frontend: AnalyticsPage — historiograph via `NetworkGraph` (axis=year); RPYS as an
a11y spectrogram (bar table by reference year + classified-reference table).
Tests: LCS ranking, RPYS year histogram + classification on a fixture with a known
sleeping-beauty pattern.
Deps: WP-B1; reuses CitationEdge + years + WP-L3b axis layout.

### WP-B6 — Multi-database import + completeness + citation matching  (B1/B2) → EXTEND scite WP9
Goal: import WoS/Scopus/Lens/Dimensions export files + RIS/BibTeX/CSV + OpenAlex API;
metadata-completeness report; surface citation matching.
Backend: extend scite-parity WP9's connector (SHIPPED: `ingestion/reference_managers.py`
RIS/BibTeX parser + `collections.import_references`) with `convert2df`-style parsers
(field-tag mapping to PaperWork/CitationEdge), an OpenAlex client
(`ingestion/openalex.py`, mirror `semantic_scholar.py` rate-limit/cache/net-gated-
test pattern), `missing_data(cohort)` completeness report, and a `citation_matching`
pass (largely reuse `enrichment.persist_reference_metadata` + CitationEdge dedupe —
surface it as an explicit step). Keep stub-work creation idempotent.
Frontend: import UI targets a Corpus/cohort (extends the Collection/Map importer);
completeness report panel.
Tests: parse a small WoS/Scopus/RIS fixture → works+edges; completeness percentages;
OpenAlex client offline-mocked (+ net-gated live).
Deps: scite WP9. External/live tests gated by `INTERCITER_NET_TESTS=1`.

### WP-B7 — PRISMA flow diagram + cohort provenance  (B2)
Goal: a first-class filterable **Corpus/cohort** with an inclusion/exclusion audit
trail rendered as a PRISMA flow diagram (identification → screening → eligibility →
included).
Schema (LinkML-first): `Corpus` (or reuse a unified saved-set base with Collection/
Map) + `CorpusFilterStep` side rows (stage, criterion, counts in/out). Mirror in
`models.py` + `ids.py`.
Backend: `services/corpus.py` — build a cohort by applying ordered filters (timespan,
language, doc type, source, min citations), recording counts per stage. Endpoint
`GET /v1/corpora/{id}/prisma`.
Frontend: PRISMA diagram (a11y-first: ordered stage table is source of truth; SVG
boxes aria-hidden).
Tests: filter application + stage counts; PRISMA node totals reconcile.
Deps: WP-B1; ideally the unified saved-set base (open question §6).

### WP-B8 — Corpus report + Three-Field Plot + export  (B10)
Goal: corpus-level report (bibliometrix Three-Field Plot + combined tables) with
CSV/Excel-style export.
Backend: `services/report.py` (scite WP3) lifted to corpus scope — reuse timeline
buckets + tallies over a cohort; `three_field` (Sankey linkage counts between two of
{authors, sources, keywords/entities, countries, references}). Endpoints
`GET /v1/bibliometrics/report` + `.../three-field`. Export via existing CSV pattern
(see Collections CSV export).
Frontend: `pages/AnalyticsReportPage.tsx` — Three-Field Plot (a11y-first linkage
table + aria-hidden Sankey) + export button.
Tests: three-field linkage counts; report rollup; CSV export columns.
Deps: WP-B1, WP-B2; reuses scite WP1/WP3.

### WP-B9 — Life Cycle logistic growth model  (B9)
Goal: fit a logistic growth curve to annual production; classify field stage +
forecast.
Backend: extend `services/bibliometrics.py` — `life_cycle(cohort, forecast_years)`:
nonlinear-least-squares logistic fit (K, tm, delta_t) on the annual series, R²/RMSE,
stage classification (emergence/growth/maturity/saturation), forecast points. Pure
numpy/scipy (scipy already? else add) — no network. Endpoint
`GET /v1/bibliometrics/life-cycle`.
Frontend: AnalyticsPage — fitted-curve a11y table (observed vs fitted vs forecast) +
stage label + fit metrics.
Tests: fit + stage classification on a synthetic logistic series (known K/tm).
Deps: WP-B1.

### WP-B10 — Biblio-AI narration  (B10) → EXTEND scite WP6
Goal: narrate bibliometric outputs (interpret Main Information, thematic map,
historiograph) as grounded text.
Do NOT build a second assistant. In scite-parity WP6's grounded RAG QA, add
bibliometric rollups (WP-B1..B5 JSON) as an additional grounded context source so the
assistant can summarize/interpret them WITH citations back to the underlying works —
never fabricating metrics. In-app only.
Deps: scite WP6, WP-B1 (+ others as available).

---

## 5. Conventions checklist for every WP
- [ ] LinkML-first: edit `schema/interciter.yaml`, regenerate (`make jsonschema`),
      mirror in `models.py` + `ids.py` (`relationship()` on insert-ordered FK cols).
- [ ] Derived reads via `services/` (non-mutating, projection style); analytics are
      pure rollups over existing records — never mutate the scientific record.
- [ ] Reads open; writes (and any network-triggering imports) require `require_user`
      + CSRF; ownership from principal.
- [ ] DTOs in `schemas.py` + `frontend/src/api/types.ts`; router in `api/app.py`.
- [ ] USWDS + Section-508: EVERY visualization (network, thematic map, Sankey,
      RPYS spectrogram, PRISMA, country map, life-cycle curve) keeps an a11y
      table/legend as the source of truth; canvas/SVG is aria-hidden + try/catch for
      jsdom. Tests assert on the table, not the SVG. REUSE the D3 `NetworkGraph`
      renderer (post litmaps WP-L3) — do not add a second graph library.
- [ ] Tests both sides; external/live import tests gated by `INTERCITER_NET_TESTS=1`.
- [ ] Preserve claim-level rigor: decomposed scores + explicit abstention +
      function/stance SEPARATE. Corpus metadata analytics are ADDITIVE, never a
      replacement for or blend of claim-level evidence.
- [ ] Reuse existing graph + S2/PMC/Crossref code; keep stub-work creation idempotent.

## 6. Notes / open questions
- **Unified saved-set base**: bibliometrix runs over a "collection". InterCiter now
  has scite `Collection` (WP4) AND litmaps `Map` (WP-L2) AND (proposed) `Corpus`
  (WP-B7) — three membership tables. DECIDE on a shared "saved set of works" base
  before building `Corpus` to avoid a third divergence (already flagged in litmaps
  §6). Analytics can run over ad-hoc `work_ids` until then.
- **Author identity**: authors are currently hashed graph nodes (`_author_id`).
  Author-level analytics (h-index, Lotka, collaboration, OpenAlex bios) want a
  first-class `Author` + `Authorship` (position/affiliation/country). Decide whether
  to graduate authors to entities (bigger schema change) before WP-B2.
- **Affiliation/country metadata**: needed for country analytics + collaboration
  map (B2/B7). Source from S2/OpenAlex affiliation strings; needs parsing +
  normalization (ROR/country). Gate country map behind this.
- **Term source for co-word (WP-B4)**: prefer grounded entities/claims over raw
  keywords (InterCiter is richer than keyword-only bibliometrix). Keywords fallback
  when grounding abstains.
- **Factorial methods (MCA/CA/MDS)**: deferred from WP-B4 — start with co-word
  network + strategic diagram; add correspondence analysis only if demanded (large
  numerical dependency).
- **Content Analysis is already ahead**: bibliometrix's citation-function tagging is
  a coarse version of InterCiter's function+stance+provenance. Do NOT regress to
  keyword-level tagging to "match" it; instead surface the existing claim data as the
  Content Analysis view.
- **A11y for maps/Sankey/spectrograms**: USWDS ships no map/Sankey/scatter
  components — every one needs a hand-built table fallback that stays in sync with
  the active measure/slice (the established InterCiter pattern).
- **Biblio AI honesty**: the narration assistant (WP-B10) must cite underlying works
  and never invent metrics — reuse scite WP6's grounded-RAG guardrails.
- **Corpus scale**: descriptive rollups + networks must stay performant over the
  ~1k-paper snowball corpus (and larger imports); prefer set-based SQL aggregates,
  cap rendered network nodes (existing ≤250 neighborhood cap), page big tables.
