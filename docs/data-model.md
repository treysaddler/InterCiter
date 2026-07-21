# InterCiter — Logical Data Model

This is the **logical** model: the immutable system of record. It is deliberately richer than what queries traverse — see [architecture.md](architecture.md) for how it is projected into a flattened graph for reading. Do not implement this 1:1 as the graph schema.

## Why claims are modeled as separate entities

A claim is split into distinct entities rather than one `Claim` node, because a single node would have to act simultaneously as:

1. an occurrence of text in a paper;
2. a normalized proposition;
3. an editable, versioned record;
4. a canonical object produced by deduplication.

Those four roles have different identities and lifecycles. Collapsing them produces edit-chain ambiguity, edge-migration complexity on merge, and corroboration/model-agreement confusion in scoring, so the model keeps them separate. This is schema richness, not feature scope — most of these entities are plain relational tables behind a small feature set, and the MVP builds only the thin path through them.

## Entity catalog

### Bibliographic layer

```text
PaperWork
  work_id
  canonical bibliographic identity (title, authors, venue, year)
  DOI / PMID / S2 corpusId mappings

PaperVersion
  version_id, work_id
  manifestation: preprint | published | correction | retraction-notice
  artifact_hash              (hash of the ingested file)
  full-text availability + license status   (see availability states in architecture.md)
  parser_name / parser_version / parse_status

Passage
  passage_id, paper_version_id
  section / page / paragraph / sentence locators (where available)
  normalized character offsets
  verbatim_text              (the exact source text — see anchoring note below)

CitationMention
  mention_id, passage_id
  marker span within the passage (e.g. "[12]", "(Smith 2019)")
  cited_work_id
  bibliographic_resolution_confidence
```

`PaperWork` vs `PaperVersion` matters in biomedicine: effect directions can change between a preprint and the corrected journal version. Claims anchor to a *version*, never just a work.

**Anchoring is layered, not offset-only.** Offsets are relative to a specific `PaperVersion` with a recorded `artifact_hash` and parser version — a re-parse or parser upgrade produces a *new* `PaperVersion` rather than silently shifting old offsets. The stored `verbatim_text` provides a second, parser-independent anchor that allows fuzzy re-anchoring of old passages onto new versions. This addresses the parser-brittleness concern without giving up exact evidence.

### Extraction layer

```text
ExtractionRun
  run_id
  model / provider / model_version
  prompt_template_version
  parser_version, code_revision
  inference parameters
  timestamp

ClaimOccurrence
  occurrence_id, passage_id
  exact source span within the passage
  occurrence_type (e.g. reported-result, background-assertion)
  extraction_run_id

ClaimInterpretation
  interpretation_id
  claim_occurrence_id
  normalized_text            (the proposition, as normalized)
  structured qualifiers      (population, intervention/exposure, comparator,
                              outcome, dosage, time horizon, effect direction,
                              effect size, hedging/certainty, negation)
  extraction_run_id — or — human author_id
  parent_interpretation_ids  (revision graph, see below)
  created_by / created_at
```

The occurrence/interpretation split is the core defensive move: `ClaimOccurrence` is what the paper *says* (source-bound, verifiable), `ClaimInterpretation` is what a model or human *thinks it means*. A bad normalization can never overwrite the ground truth, and multiple models (or a human) can attach competing interpretations to the same occurrence.

### Revision semantics

Revisions form a **graph via `parent_interpretation_ids`**, not a `superseded_by` linked list — the linked list could not represent concurrent edits, branches, or reconciliation. "Current head" is *derived* (computed at read time or materialized in the projection), never a mutable flag on the record.

The critical rule: **relation assertions never silently transfer across a material revision.** If "Treatment A reduces mortality" is revised to "Treatment A does not reduce mortality," the old support assertions must not appear as support for the new text. When a materially different revision becomes current, existing `RelationAssertion`s against the old interpretation are marked `stale_pending_review`. Reads may display inherited historical relationships, but always labeled with the exact version they were evaluated against.

Revisions are created only by the interpretation's original author or a `reviewer`/`admin` — an edit is a correction claim about someone else's work and is gated accordingly.

### Equivalence layer — soft clustering, not merging

```text
ClaimCluster
  cluster_id
  clustering method + threshold version

ClusterMembership
  cluster_id, interpretation_id
  method: automated | human
  membership_confidence
  status: active | removed
  added_by / removed_by / timestamps
```

Equivalence uses soft clustering, never an authoritative `MergeEvent` with edge copying. Reversibility bounds the *duration* of a bad merge's damage, not its blast radius — during the window before revert it still pollutes search, inflates confidence, and feeds downstream automated decisions. Instead:

- A cluster is a *statement of probable semantic equivalence*, never a replacement node. All originals remain first-class.
- **No edge copying.** Queries resolve cluster membership at read time or via the rebuildable projection; reverting a bad grouping is just removing a membership row.
- Equivalence is **not embedding distance alone**. "Drug X lowers blood pressure" and "Drug X does not lower blood pressure in older adults" sit close in embedding space while being scientifically incompatible. Candidate pairs come from embeddings (paper-level embeddings narrow *which papers* to compare; claim-level comparison uses a sentence/claim encoder — see architecture.md), but membership requires a cross-encoder / entailment check plus compatibility of structured qualifiers (negation, population, direction of effect, etc.).
- Threshold policy for the MVP: **prefer fragmentation over pollution.** Clusters are additive and can grow later; a polluted cluster misleads immediately. Uncertain pairs simply stay unclustered (abstention is a first-class outcome). Thresholds are set and validated against the gold evaluation set ([evaluation.md](evaluation.md)).

**Corroboration vs model agreement** — the two must never be conflated:

> Multiple interpretations of the *same occurrence* agreeing is **model agreement** (models may share training data and correlated errors). Distinct occurrences from *independent papers* landing in one cluster is **literature corroboration**. They are counted as separate signals ([scoring-and-review.md](scoring-and-review.md)).

### Relationship layer — first-class assertions

A relationship is an evidence-bearing **record**, not a lightweight edge:

```text
RelationAssertion
  assertion_id
  citing_occurrence_id        (the local claim making the citation)
  citation_mention_id         (the marker that licenses the relation)
  evidence_passage_id         (exact context)
  cited_work_id
  target_interpretation_id    (nullable — resolved target claim)
  target_candidates           (ranked candidates + scores when unresolved)
  function:   background | method | direct-evidence | comparison | other
  stance:     support | contradict | neutral | unclear
  scope:      whole-claim | partial-claim | paper-level-only
  resolution: claim_resolved | paper_resolved | unresolved
  target_link_score           (separate from stance confidence)
  stance_distribution         (full label-probability distribution)
  extraction_run_id
  status: proposed | accepted | rejected | unresolved | stale_pending_review
```

Function, stance, scope, and resolution are modeled as four independent dimensions rather than a single `mention / support / dissent` axis. "Mention" is a citation *function* while support/dissent are epistemic *stances*, and the two are orthogonal — a citation can mention a method while supporting a result, or support part of a claim while qualifying another. One axis cannot express that; four can.

The paper-level fallback is now expressed honestly. Instead of "this claim supports that paper," it records:

```text
stance = support, resolution = paper_resolved, target claim = unresolved
```

still walkable for chain tracing, upgradeable to `claim_resolved` later (when the target's claims are extracted, or on review), and never overstating precision. An `unresolved` outcome with ranked candidates is a legitimate result at every uncertain stage, not a failure.

### Review and assessment layer

```text
ReviewDecision
  subject_type + subject_id   (occurrence, interpretation, assertion, membership)
  reviewer_id
  decision dimension          (e.g. extraction fidelity, stance, target link)
  label / value
  rationale
  timestamp

Assessment
  subject_id, assessment_type
  component inputs            (the raw signals used)
  algorithm_version
  computed_value
  computed_at
```

All derived scores live in versioned, rebuildable `Assessment` records — never as an unexplained mutable number on a claim. See [scoring-and-review.md](scoring-and-review.md) for the signal decomposition.

`UserScore` and `TrustWeight` (community/user-supplied signals) are **deferred to phase 2** but keep the same overlay pattern; their sketches live in scoring-and-review.md.

## Additive-only, precisely scoped

"Additive-only" means **immutable scientific assertions and decisions** — not "nothing can ever be deleted." The system still needs:

- **Tombstones** for takedowns/redactions: preserve that a record existed and why it was removed, without the content;
- access revocation and license-driven retention for full text;
- handling for copyrighted or sensitive material.

## Graph shape (projection view)

What queries actually traverse, after projection ([architecture.md](architecture.md)):

```text
Paper --[has_claim]--> Claim ==[RelationAssertion: stance+function]==> Claim   (claim_resolved)
                         |                                          \=> Paper  (paper_resolved fallback)
                         --[member_of]--> Cluster
                         --[anchored_to]--> Passage --> PaperVersion
```

Each projected edge carries `resolution`, `stance`, `function`, both scores, and a pointer back to its `RelationAssertion` in the system of record.

## Mapping onto BioLink

The model maps cleanly onto BioLink:

- `ClaimInterpretation` → subtype of BioLink `InformationContentEntity`.
- `RelationAssertion` → a custom `Association` subclass; its evidence, publications, and confidence fields map naturally onto BioLink's provenance-heavy association pattern, a better fit than a lightweight property-graph edge.
- `ExtractionRun` provenance → `knowledge_source` / `primary_knowledge_source` / `aggregator_knowledge_source` slots (RoboKop already has display plumbing here).
- `PaperWork`/`PaperVersion` → BioLink `Publication`, kept close to unmodified; versioning is an additive slot.
