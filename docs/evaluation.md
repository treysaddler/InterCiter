# InterCiter — Evaluation Plan

All three reviews agreed this was the largest gap: the original design hand-waved "Semantic Scholar citation intent gives us an evaluation story." This document makes evaluation a first-class component. For the grant, this is also the methodology section — and the annotation corpus is the **budget crux**, named as such rather than treated as a checkbox.

## Gold corpus

A manually adjudicated evaluation corpus over the MVP domain slice:

- **Annotation protocol** with written guidelines per task (claim spans, citation scope, function, stance, target alignment), piloted and revised before full annotation.
- **Inter-annotator agreement** reported per task (e.g. Krippendorff's α / Cohen's κ), with disagreement categories analyzed — disagreements are signal about ontology weaknesses, not just noise.
- **Adjudication** of disagreements by a senior annotator; adjudication rate reported.
- `ReviewDecision` records double as ongoing annotation: the production review workflow and the evaluation pipeline share one data structure ([scoring-and-review.md](scoring-and-review.md)).

The corpus **deliberately includes hard cases**: multiple citations in one sentence, compound claims, negation, hedging, indirect citation, systematic reviews, conflicting studies, and target papers containing several similar claims.

## Per-stage metrics

Errors compound across the pipeline, so every stage is measured separately:

| Stage | Measurements |
|---|---|
| Document parsing | Citation-marker resolution, passage-offset accuracy, section recognition |
| Claim extraction | Span precision/recall, atomicity, factual fidelity, qualifier preservation |
| Citation scope | Accuracy linking a citation marker to the local claim it belongs to |
| Target-claim retrieval | Recall@k; precision at the automatic-link threshold |
| Relationship classification | Per-class precision/recall, macro-F1, confusion matrix (function and stance separately) |
| Confidence | Calibration error (ECE); selective risk / coverage curves as abstention increases |
| Clustering | Pair precision/recall against adjudicated equivalence judgments |
| Multi-hop tracing (phase 2) | Path precision, coverage, cycle handling, per-hop provenance completeness |
| Human review | Inter-annotator agreement, disagreement categories, adjudication rate |
| Operations | **Cost per paper (LLM + compute)**, throughput, p95 latency, retry rate, ingestion failure rate |

Cost per paper is a reported metric, not an afterthought: LLM extraction cost at corpus scale directly shapes the feasibility story and interacts with any multi-model comparison.

## Abstention as a measured behavior

Every uncertain stage can return `unresolved` ([data-model.md](data-model.md)). Evaluation therefore reports **selective performance**: precision at the thresholds actually used in production, and the risk/coverage tradeoff as thresholds move. The claim being tested is not "the system is always right" but "the system is right at useful precision *when it chooses to answer*, and honest when it doesn't."

## Semantic Scholar citation intent: weak supervision + baseline, not ground truth

S2's citation-intent labels use a different label set from InterCiter's function/stance ontology. They are used as:

1. **weak supervision** to bootstrap classifiers, via an explicit **mapping study** (how S2 labels distribute over InterCiter's ontology, measured on the gold corpus);
2. a **baseline** to beat, giving the grant a comparative evaluation.

They are never the final ground truth.

## Model swappability, demonstrated cheaply

Production multi-model extraction is deferred ([../interciter-systems-design.md](../interciter-systems-design.md)), but swappability is still demonstrated: run a second extraction model **on the evaluation set only**, compare per-stage metrics and error categories. `ExtractionRun` provenance makes this a query, not a feature. This preserves the multi-model story for the grant without making it an MVP production feature.
