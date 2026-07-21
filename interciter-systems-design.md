# InterCiter — Systems Design Overview

> **Revision 2** (2026-07-20). Incorporates three external design reviews: [GPT Sol](feedback/0001-gpt-5.6-sol-pro-feedback.md) (data-model and MVP critique), [Gemini](feedback/0002-gemini-3.1-pro-feedback.md) (physical-schema and UX critique of GPT Sol's proposal), and [Opus](feedback/0003-claude-opus-4.8-feedback.md) (adjudication of both). The design detail now lives in [docs/](docs/); this document is the entry point.

## Document map

| Document | Contents |
|---|---|
| [docs/data-model.md](docs/data-model.md) | The immutable logical model: papers/versions/passages, occurrences vs interpretations, revision graph, soft clustering, first-class relation assertions, BioLink mapping |
| [docs/architecture.md](docs/architecture.md) | Layers; write model vs read projection; Semantic Scholar integration; availability states; async jobs; ingestion security |
| [docs/scoring-and-review.md](docs/scoring-and-review.md) | Decomposed confidence signals, Assessment records, review workflow, deferred user/trust scoring |
| [docs/evaluation.md](docs/evaluation.md) | Gold corpus, per-stage metrics, calibration and abstention, S2 intent as weak supervision |
| [docs/api.md](docs/api.md) | The `/v1` surface: jobs/runs, evidence endpoints, revisions, bounded traversal |
| [docs/grant-framing.md](docs/grant-framing.md) | Three hypotheses, corrected language, budget honesty, domain-scope framing |

## Summary

InterCiter is a knowledge-graph system that extracts individual claims from scientific papers, **anchors each claim to its exact source passage**, and classifies how citing claims relate to cited work — separating the citation's *function* (background, method, direct evidence, comparison) from its *stance* (support, contradict, neutral). Walking these relations traces a claim to its **earlier cited antecedents within the traversed corpus**. On this core it layers semantic search, citation-network visualization, and automated reference generation, all through a single API.

The design philosophy is **provenance-first**: model outputs, human corrections, cluster groupings, and review decisions coexist as distinct, immutable, traceable records. What the paper says (`ClaimOccurrence`) is never overwritten by what a model thinks it means (`ClaimInterpretation`); uncertainty is expressed by **abstaining** (`unresolved`), never by overclaiming. The system builds on established infrastructure — BioLink, RoboKop, Semantic Scholar — and its research contribution is captured in three testable hypotheses: source-grounded extraction, selective claim alignment, and auditable lineage ([docs/grant-framing.md](docs/grant-framing.md)).

## Design principles (revised)

1. **Build smallest to largest.** The MVP is a thin, auditable vertical slice that proves the highest-risk scientific loop; everything else layers on the same foundation.
2. **Piggyback on existing infrastructure.** Extend BioLink rather than invent an ontology; inherit Semantic Scholar's citation graph rather than parse bibliographies; use RoboKop's provenance plumbing.
3. **Provenance-first: immutable assertions, not "never delete."** Scientific assertions and decisions are append-only; tombstones, retention, and takedown handling still exist for legal and licensing reality.
4. **Evidence anchoring makes provenance true.** *(New.)* Every claim points to a paper version, passage, offsets, and verbatim text. A provenance-first system that can't show where in the paper a claim came from is internally contradictory.
5. **Abstention is a first-class outcome.** *(New — promoted from a fallback.)* Every uncertain stage — alignment, stance, clustering — can return `unresolved` with candidates and calibrated scores, rather than guessing.
6. **LLM as starting point, not source of truth.** Extraction runs are fully recorded and swappable; human review corrects rather than gates.
7. **Separate the logical model from the physical schema.** *(New.)* The rich immutable model is the system of record (relational); queries traverse a derived, rebuildable graph projection that is never authoritative.
8. **Signals stay decomposed.** *(New.)* No blended global confidence; model agreement and literature corroboration are different evidence and never summed.
9. **API-first.** Every feature, including InterCiter's own frontends, routes through the API — which serves reader-friendly composed views by default, with the audit structure behind explicit endpoints.
10. **Minimal, reproducible storage footprint.** Domain slices with pinned corpus versions and inclusion criteria; inherit precomputed artifacts where they're actually fit for purpose.

## Architecture at a glance

Three layers — **Ingestion/Extraction** (stateless, pluggable, run-recorded), **Knowledge Graph** (immutable system of record + derived projection, BioLink-aligned), **Access** (API and everything on it). The write model is normalized PostgreSQL; the read model is a periodically rebuilt graph projection that flattens occurrence/interpretation/cluster chains into traversable claim nodes, with every projected edge pointing back to its evidence-bearing `RelationAssertion`. Details and guardrails: [docs/architecture.md](docs/architecture.md).

## MVP — a thin, auditable vertical slice

> Given an open-access biomedical paper, identify empirical result claims, show their exact source passages and citation contexts, classify each cited relationship (function + stance) with calibrated abstention, and trace **one hop** to the cited paper or a confidently matched target claim.

**What counts as an MVP claim:** an empirical result claim — a statement reporting a study finding with a direction of effect — in open-access full text (XML first; general PDF ingestion deferred), within one tightly defined biomedical subdomain.

### In the MVP

| Include | Rationale |
|---|---|
| One biomedical subdomain, open-access XML first | Bounds ontology and annotation variation; avoids PDF parsing dominating the research |
| Empirical result claims only | A definable target, unlike "all claims" |
| Exact evidence anchoring (versions, passages, spans) | Required for trust and for evaluation |
| One reference extraction pipeline, fully run-recorded | Tests the hypothesis; preserves swappability via `ExtractionRun` provenance |
| Citation-scope identification, then function/stance classification | Scope must precede stance |
| Paper-level target + optional claim-level alignment, with abstention | The chain never dead-ends, and never overclaims |
| One-hop trace endpoint | Prevents multi-hop error compounding from dominating early results |
| Minimal annotation + adjudication workflow | Creates ground truth; doubles as the review mechanism |
| Soft clustering (high-precision thresholds, abstain when unsure) | Needed for corroboration counting; non-destructive by construction |
| Polling job API; minimal roles + first-class ownership | Simple, forecloses nothing |
| Ingestion hardening (sandboxed parsing, output validation, prompt-injection defenses) | The pipeline eats untrusted documents |

### Deferred to phase 2

| Defer | Reason |
|---|---|
| Production multi-LLM extraction | Swappability is demonstrated on the eval set instead ([docs/evaluation.md](docs/evaluation.md)) |
| Blended ranking scores | Components must be validated separately first |
| Public user scores + paper trust weighting | Identity, abuse, and bias problems; overlay design retained for later |
| Deep multi-hop traversal | Per-hop errors compound; ships bounded (`max_depth`, `max_nodes`) when it ships |
| Reference generation | Depends on validated high-precision retrieval |
| General PDF ingestion | After the structured-text pipeline is validated |
| Cross-domain support | Vocabularies become domain plugins later; architecture stays domain-neutral |
| Network visualization; review-queue prioritization; webhooks | Layers over data already stored |

## Open decisions and known risks

- **Domain scope — decided:** MVP narrows to one biomedical subdomain (both reviews' recommendation), with domain-agnosticism reframed as "domain-neutral architecture, pluggable vocabularies" ([docs/grant-framing.md](docs/grant-framing.md)). Revisit only if the grant's funder profile demands broader initial scope.
- **Which biomedical subdomain / paper type — open.** Choose for annotation tractability (e.g. a literature with relatively formulaic empirical claims) before corpus work begins.
- **LLM cost at scale — open.** Cost per paper is a tracked evaluation metric; corpus-scale extrapolation belongs in the grant budget.
- **Clustering thresholds — open by design.** Set from the gold corpus via calibration; the standing policy is prefer-fragmentation-over-pollution.
- **Physical graph store — deliberately last.** Chosen only after the immutable logical model stabilizes (reviews' priority ordering).

## What changed in Revision 2

Accepted from the reviews, in order of importance:

1. **Evidence anchoring** — `PaperVersion` / `Passage` / `CitationMention`, offsets + verbatim text + artifact hashes. The biggest catch: provenance-first requires it.
2. **The `Claim` node was split** into `ClaimOccurrence` / `ClaimInterpretation` / `ClaimCluster` + revision graph — it had conflated four objects with different lifecycles.
3. **Relations became first-class evidence-bearing `RelationAssertion`s**, with function / stance / scope / resolution as separate axes replacing `mention/support/dissent`.
4. **Authoritative merging (`MergeEvent` + edge copying) was removed** in favor of soft clustering — reversibility bounds damage duration, not blast radius.
5. **Edit-chain semantics fixed** — revision graph instead of a linked list; material revisions mark dependent assertions `stale_pending_review` instead of silently inheriting support.
6. **Blended global confidence removed** — decomposed signals; model agreement ≠ literature corroboration; versioned `Assessment` records.
7. **SPECTER usage corrected** — paper-level candidate narrowing only; claim-level work needs sentence encoders + cross-encoder/entailment.
8. **A real evaluation plan** — adjudicated gold corpus, per-stage metrics, calibration/abstention reporting; S2 intent demoted to weak supervision + baseline.
9. **Logical/physical split** (from the Gemini review) — the rich model is the system of record; the graph is a derived, rebuildable, never-authoritative projection; the API abstracts the audit model away from end users.
10. **MVP narrowed** to the one-hop vertical slice above; trust weighting, public scoring, multi-model production extraction, and deep traversal deferred.
11. **Operational honesty** — paper availability states, reproducible slice definition, hydration retry/caching, ingestion security, tombstones/retention, and jobs/runs as first-class API resources.
