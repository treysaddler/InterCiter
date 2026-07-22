# External data integration: Semantic Scholar & ROBOKOP

This is an implementation plan (not yet built) for pulling the enrichment data
InterCiter's design already assumes from two upstream providers — **Semantic Scholar**
(paper + citation-graph substrate) and **ROBOKOP** (biomedical knowledge graph +
entity normalization) — and for standing up a **local cache of the Semantic Scholar
bulk datasets** as a reusable component the rest of the system builds on.

It follows the patterns already established by
[`ingestion/pmc.py`](../backend/interciter/ingestion/pmc.py): a settings-driven,
rate-limited, cache-first client that fetches on demand, never bundles licensed text,
and is exercised by network-gated tests.

## Goals

1. **Per-paper enrichment (Academic Graph API)** — identifier mapping, resolved
   citation links with contexts + intents, SPECTER2 embeddings, TLDR + core metadata.
2. **Bulk datasets (Datasets API)** — download and cache the full-corpus snapshots
   (papers, citations, abstracts, s2orc, embeddings, tldrs) locally, keyed by a pinned
   release id, so downstream code queries a local store instead of the network.
3. **ROBOKOP** — ground extracted targets to canonical CURIEs, look up known
   biomedical edges for a subject/object pair, and carry the provenance through to
   `RelationAssertion`.

Non-goals for this phase: replacing the JATS ingestion path, doing claim-level
alignment with embeddings (paper-level narrowing only — see
[architecture.md](architecture.md)), and treating S2 citation-intent labels as ground
truth (weak supervision only — see [evaluation.md](evaluation.md)).

## Module layout

```
backend/interciter/ingestion/
  pmc.py                # existing NCBI/PMC fetcher (template)
  semantic_scholar.py   # NEW — Academic Graph API client (per-paper)
  robokop.py            # NEW — node-norm + name-res + TRAPI client
backend/interciter/datasets/
  __init__.py
  s2_bulk.py            # NEW — Datasets API: releases, download links, diffs
  store.py             # NEW — local cache layout + manifest + lookup by corpusId
```

Config lives in [`config.py`](../backend/interciter/config.py) `Settings`; CLI verbs in
[`cli.py`](../backend/interciter/cli.py); tests are network-gated by
`INTERCITER_NET_TESTS=1` like the existing PMC tests.

---

## 1. Semantic Scholar Academic Graph API (per-paper)

Base: `https://api.semanticscholar.org/graph/v1`. Auth via optional `x-api-key`
header. Unauthenticated traffic shares a global pool; an API key's introductory limit
is 1 rps, so the client reuses the `pmc.py` `_rate_limit` pattern and backs off on 429.

Paper ids accept several prefixes, which lets us resolve from what we already store:
`DOI:10.…`, `PMID:…`, `PMCID:PMC…`, `CorpusId:…`, `ARXIV:…`, or a raw S2 `paperId`.

### 1a. Identifier mapping → `PaperWork`

- `GET /paper/{id}?fields=externalIds,title,year,venue,authors` returns
  `externalIds` (`DOI`, `PubMed`, `PubMedCentral`, `CorpusId`, `ArXiv`, …).
- Batch form: `POST /paper/batch?fields=externalIds` with `{"ids": [...]}` (up to 500
  ids) — the efficient path for backfilling many works at once.
- **Writes:** populate `PaperWork.s2_corpus_id` (already a column, indexed) and fill
  gaps in `doi` / `pmid`. A returned DOI/PMID **does not** imply accessible full text —
  keep availability state driven by actual ingestion, not by presence of an identifier.

### 1b. Resolved citation links (references) with contexts + intents

- `GET /paper/{id}/references?fields=contexts,intents,isInfluential,citedPaper.externalIds,citedPaper.title`
  (paginate with `offset`/`limit`, 1000 max).
- This is the **headline inheritance**: S2 ties each bibliography entry to the inline
  sentences that mention it. Maps onto `CitationMention` — the same table the JATS
  parser fills — so S2-derived mentions and parser-derived mentions coexist, each
  tagged with provenance. `contexts` gives candidate `verbatim_text`/`marker_span`;
  `citedPaper.externalIds` resolves `cited_work_id`.
- `intents` (e.g. `background`, `methodology`, `result`) are **weak supervision**, not
  our `function`/`stance` ontology. Store them raw on the mention (see schema note
  below); a mapping study — not a direct copy — is what feeds `RelationAssertion`.

### 1c. SPECTER2 embeddings (paper-level only)

- `GET /paper/{id}?fields=embedding.specter_v2` → a dense vector.
- Used strictly for **paper-level candidate narrowing** in target resolution, replacing
  or augmenting the current token-overlap prefilter in
  [`pipeline.py`](../backend/interciter/ingestion/pipeline.py) (`_overlap_score`). It is
  **never** used to seed claim-level dedup or to assert claim equivalence — that needs a
  sentence/cross-encoder, per [data-model.md](data-model.md).

### 1d. TLDR + core metadata

- `GET /paper/{id}?fields=tldr,abstract,title,year,venue,authors,publicationTypes,fieldsOfStudy`.
- Fills display metadata on `PaperWork` and gives reviewers a one-line gist. Abstracts
  from this endpoint are metadata, but still respect per-source licensing — cache, do
  not redistribute.

### Caching

Per-paper JSON responses cached under `pmc_cache_dir`'s sibling `s2_cache_dir`
(gitignored), keyed by the normalized id. Embeddings stored as a compact `.npy`/JSON
sidecar. Same 25 MiB response cap as PMC.

---

## 2. Semantic Scholar Datasets API (bulk, local cache component)

Base: `https://api.semanticscholar.org/datasets/v1`. **Requires an API key.** This is
the "component we can build off of": a pinned local snapshot that downstream code reads
instead of hitting the network per paper.

### Flow

1. `GET /release` → list of date-stamped releases (e.g. `2024-01-09`).
2. `GET /release/latest` → `{release_id, datasets: [{name, description, README}, …]}`.
3. `GET /release/{release_id}/dataset/{name}` → `{name, files: [presigned S3 urls…]}`.
   URLs are **pre-signed and expire** (hours), so resolve-then-download promptly and do
   not persist the URLs — persist the release id + file basenames.
4. Incremental refresh: `GET /diffs/{start}/to/{end}/{name}` → per-diff `update_files`
   and `delete_files`; upsert/delete by `corpusid`.

### Datasets available & their measured sizes

The Datasets API exposes **11 datasets**. The table below reports the *actual*
compressed (`.gz`) download footprint, measured by summing every shard's object size
for release **`2026-07-14`** (each shard's total was read from the S3 `Content-Range`
of a ranged `GET`, since the pre-signed URLs reject `HEAD`). Sizes use binary units
(1 GB = 1024 MB). Downloading the **entire corpus is ≈3.2 TB across 3,495 shards**; in
practice InterCiter only pulls the datasets and shards it needs.

| Dataset | Shards | Total size | Avg / shard | Purpose |
|---|--:|--:|--:|---|
| `papers` | 60 | 48.8 GB | 832.8 MB | Core paper attributes (title, authors, date, externalIds) |
| `abstracts` | 30 | 26.4 GB | 900.2 MB | Abstract text where licensed |
| `authors` | 30 | 3.2 GB | 109.7 MB | Core author attributes (name, affiliation, paper count) |
| `paper-ids` | 30 | 15.3 GB | 523.4 MB | Mapping from sha-based ID to paper `corpusid` |
| `citations` | 389 | 359.3 GB | 945.9 MB | Citation-graph edges (intent, influence, context) |
| `embeddings-specter_v1` | 1,005 | 986.2 GB | 1004.9 MB | Paper-level SPECTER v1 dense vectors |
| `embeddings-specter_v2` | 981 | 963.6 GB | 1005.9 MB | Paper-level SPECTER2 dense vectors |
| `s2orc` | 636 | 611.6 GB | 984.7 MB | Full-body parsed open-access text (v1) |
| `s2orc_v2` | 303 | 294.0 GB | 993.5 MB | Full-body parsed open-access text (v2) |
| `tldrs` | 30 | 6.1 GB | 206.8 MB | One-line paper summaries |
| `publication-venues` | 1 | 15.3 MB | 15.3 MB | Venue details |
| **Total** | **3,495** | **≈3.2 TB** | — | |

> Sizes are release-dependent and grow each snapshot; re-measure against the pinned
> `release_id` when refreshing. Reproduce with `backend/_ds_sizes.py` (needs
> `INTERCITER_S2_API_KEY`). The two `embeddings-*` datasets alone account for ~1.9 TB
> (~55%) of the corpus, so pull them only for a targeted slice.

**`s2orc` vs `s2orc_v2`.** Despite `s2orc_v2` being the newer parse, it is currently
*smaller* (294 GB vs 611.6 GB) because it covers **fewer papers**, not because it
encodes them more compactly. Sampling the head of one shard from each (release
`2026-07-14`) gives near-identical per-shard sizes (~1 GB) and comparable per-record
size (v2 is even ~12% smaller/record), so the ~2× total-size gap is ~2× fewer records:
roughly **~33M** papers in `s2orc` vs **~18M** in `s2orc_v2` (order-of-magnitude
estimate from a first-shard sample; the API's own description strings are stale here).
The schemas also differ — v1 folds everything into one `content{text, annotations,
source}` blob, while v2 has a richer top level (`title`, `authors[]`,
`openaccessinfo{license, status, url, …}`) and splits `body` from `bibliography`, each
with its own `text` + offset `annotations`. Prefer `s2orc_v2` for cleaner structure and
explicit license metadata; fall back to `s2orc` when you need the broader coverage.

Each file is newline-delimited JSON (`.gz`), one record per line keyed by `corpusid`.

### Local store & manifest

`datasets/store.py` owns a cache root (`s2_datasets_dir`, gitignored) laid out as:

```
<s2_datasets_dir>/
  <release_id>/
    papers/part-00000.jsonl.gz …
    citations/…
    embeddings/…
  manifest.json      # pinned release_id, per-dataset file list + sha256 + byte counts
```

`manifest.json` is the **reproducibility contract** the design already calls for
(pinned corpus release + inclusion criteria, [architecture.md](architecture.md) →
"Domain slice, defined reproducibly"). It is small and **may be committed**; the data
shards are not.

**Query surface:** the first useful "build-off-of" layer is a `corpusid → record`
lookup. Options, in increasing effort: (a) stream-scan the gz shards for a slice of
ids; (b) build a local SQLite index (`corpusid → (dataset, file, byte_offset)`); (c)
load a domain slice into DuckDB/Parquet. Start with (a)+(b) for the gold-set slice; a
full ingest is a later phase.

### Smoke test (this phase)

Implement the full release/download/verify path, then **download a single shard** of
`papers` (smallest useful dataset) to validate: presigned-URL handling, gz streaming,
sha256 verification, manifest write, and a `corpusid` lookup round-trip. No full-corpus
download in this phase — the machinery is the deliverable, the data is opt-in per
dataset/shard via CLI flags.

### Etiquette & safety

Resume-friendly streaming download with retry/backoff; verify sizes/hashes; never hold
files in memory (25 MiB cap does **not** apply to bulk shards — stream to disk); honor
the per-dataset `README` license terms; require `INTERCITER_S2_API_KEY` to be set
before any datasets call.

---

## 3. ROBOKOP (biomedical knowledge graph)

Three services from the NCATS Translator / RENCI stack, all cache-first and
network-gated:

### 3a. Entity grounding — node normalization

- Name → CURIE: **Name Resolver** —
  `GET https://name-resolution-sri.renci.org/lookup?string=metformin&limit=…`.
- CURIE → canonical clique: **Node Normalizer** —
  `GET https://nodenormalization-sri.renci.org/get_normalized_nodes?curie=CHEBI:6801`
  (batch via `POST`), returning the preferred CURIE, equivalent identifiers, and
  BioLink semantic types.
- **Use:** ground the drug/gene/disease targets the extractor pulls into stable CURIEs
  so target resolution and clustering key on canonical ids rather than surface strings.
  This complements — does not replace — the current claim-overlap resolution.

### 3b. Known edges for a subject/object pair — TRAPI query

- ROBOKOP KG is queryable via a TRAPI endpoint (Automat: `robokopkg`). POST a one-hop
  TRAPI query graph: `subject` (canonical CURIE from 3a) — `predicate` (BioLink) —
  `object`, and read back `knowledge_graph.edges` with their `sources`
  (`retrieval_source`) and supporting publications.
- **Use:** corroborate or contextualize an extracted `RelationAssertion` against prior
  biomedical knowledge (e.g. "metformin — treats/affects — hyperglycemia"), and surface
  provenance. This is context/enrichment, **not** a truth oracle — it never overrides an
  extracted, source-grounded assertion.

### 3c. Provenance plumbing → `RelationAssertion` / `ExtractionRun`

- BioLink provenance slots (`primary_knowledge_source`, `aggregator_knowledge_source`)
  already have display plumbing in the data model
  ([data-model.md](data-model.md)). Capture ROBOKOP edge `sources` there so a
  ROBOKOP-corroborated assertion cites its upstream KP, distinct from InterCiter's own
  extraction provenance on `ExtractionRun`.

Caching: normalized-node and TRAPI responses cached under `robokop_cache_dir`, keyed by
a hash of the request; short TTL acceptable since these are reference lookups.

---

## Data-model impact

Prefer additive changes; do not mutate scientific assertions.

- **No new column needed** for `s2_corpus_id` (exists). Backfill it.
- **CitationMention provenance + intents:** add a nullable JSON `source_metadata` (or a
  small side table) to record `{provider: "s2"|"jats", s2_intents: [...], contexts:
  [...], is_influential: bool}`. Keeps S2 weak-supervision labels auditable and separate
  from our ontology. LinkML schema + generated models updated in lockstep
  ([`schema/interciter.yaml`](../schema/interciter.yaml)).
- **Grounded targets:** store canonical CURIE + BioLink type on the interpretation's
  `qualifiers` JSON (already free-form) or a dedicated grounding side table if we want
  to index it.
- **Embeddings:** paper-level vectors live in the cache/side store, referenced by
  `s2_corpus_id`, not inline on `PaperWork`.

Any schema change goes through LinkML first, then regenerates
`schema/generated/{models.py,schema.sql,schema.json}` and mirrors into
`interciter/models.py`.

## Config additions (`Settings`)

```python
# Semantic Scholar
s2_api_key: str | None = None            # INTERCITER_S2_API_KEY
s2_graph_base: str = "https://api.semanticscholar.org/graph/v1"
s2_datasets_base: str = "https://api.semanticscholar.org/datasets/v1"
s2_cache_dir: str = ".cache/s2"          # per-paper JSON
s2_datasets_dir: str = ".cache/s2-datasets"

# ROBOKOP / Translator
robokop_trapi_url: str = "https://automat.renci.org/robokopkg/1.5/query"
node_norm_url: str = "https://nodenormalization-sri.renci.org"
name_res_url: str = "https://name-resolution-sri.renci.org"
robokop_cache_dir: str = ".cache/robokop"
```

All cache dirs gitignored, consistent with `pmc_cache_dir`.

## CLI additions

```
interciter s2-enrich <id> [--refs] [--embedding] [--tldr]   # per-paper, prints/caches
interciter s2-datasets releases                              # list releases
interciter s2-datasets pull <name> [--release latest] [--shards 1]  # download+manifest
interciter s2-datasets lookup <corpusid>                     # local-store round-trip
interciter robokop ground "<name-or-curie>"                  # normalize → CURIE
interciter robokop edges <subject-curie> <object-curie>      # TRAPI one-hop
```

Mirrors the existing `pmc-fetch` / `pmc-inspect` verbs.

## Testing

- Unit tests (offline): id normalization, cache hit/miss, manifest read/write, TRAPI
  query-graph construction, response→model mapping using **recorded fixtures**.
- Network tests gated by `INTERCITER_NET_TESTS=1` (like `test_pmc.py`), plus a datasets
  test additionally gated on `INTERCITER_S2_API_KEY` being present.
- Bulk smoke test: pull one `papers` shard, verify sha256, assert a known `corpusid`
  resolves.

## Licensing & etiquette (non-negotiable)

- Identify tool + contact; rate-limit; exponential backoff; respect per-dataset READMEs.
- Cache locally, **never commit** fetched text/shards; commit only annotations,
  identifiers, and the small `manifest.json` (pinned release id) — same posture as the
  existing PMC gold set.

## Phased plan

1. **Config + module skeletons** (`semantic_scholar.py`, `robokop.py`,
   `datasets/{s2_bulk.py,store.py}`) with the `pmc.py` rate-limit/cache scaffolding.
2. **S2 per-paper**: identifier mapping + `s2_corpus_id` backfill; references w/
   contexts+intents; TLDR/metadata; embeddings sidecar. CLI `s2-enrich`. Fixtures +
   gated tests.
3. **S2 bulk**: releases/download/verify/manifest + single-shard smoke test + SQLite
   `corpusid` index. CLI `s2-datasets`.
4. **ROBOKOP**: name-res + node-norm grounding; TRAPI one-hop edges; provenance
   capture. CLI `robokop ground|edges`.
5. **Schema**: additive LinkML changes (mention `source_metadata`, target grounding);
   regenerate + mirror models; wire into `pipeline.py` (embedding prefilter, grounding).

## Open questions

- Bulk **query engine** for downstream: SQLite index vs DuckDB/Parquet — decide when we
  move past the gold-set slice to a real domain slice.
- **Which ROBOKOP surface**: Automat `robokopkg` (direct KG, fast one-hop) vs the full
  ROBOKOP ARA/Aragorn (reasoning, slower). Plan assumes Automat for deterministic
  one-hop lookups.
- **Embedding-based prefilter cutover**: keep token-overlap as a fallback for papers
  without an S2 embedding.
