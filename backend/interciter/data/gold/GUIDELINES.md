# InterCiter gold-set annotation guidelines

These guidelines govern the manually adjudicated evaluation corpus for the MVP domain
slice: **empirical result claims in type-2-diabetes / prediabetes glycemic-control RCTs
and their systematic reviews** (open-access, JATS XML from the PMC Open Access subset).

They implement the per-task protocol the design calls for (docs/evaluation.md): claim
spans, citation scope, function, stance, and target alignment — piloted and revised
before full annotation, with inter-annotator agreement and adjudication.

## Provenance and licensing

- We annotate real papers but **do not redistribute their full text**. The gold JSON
  stores annotations keyed to `pmcid` / `doi`; full text is fetched on demand from PMC
  and cached locally (gitignored). Record each paper's `license`.
- Papers may be `CC BY`, `CC BY-NC`, or `CC BY-NC-ND`; the non-commercial / no-derivative
  ones are exactly why we key to identifiers rather than bundling text.

## Corpus fields

- `domain`, `corpus_version`, `source` (`pmc-oa`).
- `exhaustive_claims`: set **true** only when *every* result claim in *every* paper is
  annotated. When true, extraction precision is reported; when false, only recall is
  (precision over all predictions is meaningless against a partial key).
- `papers[]`: each with `pmcid`, `doi`, `order` (antecedents before citers), `license`,
  `title`, annotated `citations[]`, and `claims[]`.
- `equivalences[]`: groups of `gold_id`s adjudicated as the same proposition.

## What is an annotatable claim

An **empirical result claim**: a statement reporting a study finding with a direction of
effect. Annotate the claim as it appears; do not invent qualifiers the text doesn't state.

`occurrence_type`:
- `reported_result` — a finding with a direction of effect ("HbA1c was reduced by 1.8%").
- `background_assertion` — contextual statements, incl. reporting a *comparator study's*
  baseline characteristics or non-result facts.
- `method_description`, `hypothesis`, `other` — as applicable.

`gold_id` `text` should **quote or closely paraphrase the source sentence** so the
predicted span can be aligned; keep the distinctive content words (drug, outcome,
direction). Prefer the crisp primary-result sentence (usually in Results / Primary
outcome) over a discussion recap.

Qualifiers (annotate only what the text states; otherwise `null`):
- `effect_direction`: `increase` | `decrease` | `no_effect` | `mixed` | `unclear`.
  Negated findings ("no significant difference") → `no_effect`, `negated: true`.
- `certainty`: `definite` (significant/demonstrated) | `probable` | `possible` (hedged:
  "may", "suggests") | `speculative`.
- `population` / `intervention` / `comparator` / `outcome` / `dosage` / `time_horizon` /
  `effect_size` where clearly stated.

## Citations

Annotate the `citations[]` you evaluate: `marker` (the in-text marker text, e.g. `23`)
and `resolved_doi` (the DOI the bibliography entry resolves to). Only include markers you
also annotate relations for, or that you want scored for citation-marker resolution.

## Relations (four independent axes)

For each citation attached to a claim, annotate a relation with **four orthogonal axes**:

- `function` — why the citation is there: `background` | `method` | `direct_evidence`
  | `comparison` | `other`. (A citation's function is *not* its stance.)
- `stance` — the citing claim's epistemic stance toward the cited work: `support` |
  `contradict` | `neutral` | `unclear`. Reporting a comparator's magnitude without
  agreeing/disagreeing is `neutral`. Abstain with `unclear` when genuinely ambiguous.
- `scope` — how much of the claim the citation applies to: `whole_claim` |
  `partial_claim` (one clause of a multi-part sentence) | `paper_level_only`.
- `resolution` — how precisely the target is identified:
  - `claim_resolved` — a specific cited claim is meant; set `target_gold_id` to that
    claim's `gold_id` (the cited paper must also be in the corpus, ingested earlier).
  - `paper_resolved` — the cited *paper* is identified but no single target claim is;
    `target_gold_id: null`. This is the honest default when the cited paper is out of
    corpus or the reference is paper-level (e.g. a baseline-characteristics comparison).
  - `unresolved` — the citation could not be resolved at all.

## Equivalence / clustering

Add a group to `equivalences[]` only when claims assert the **same proposition** (same
intervention, outcome, and direction). Two different drugs both reducing HbA1c are **not**
equivalent — prefer fragmentation over pollution. Within-paper restatements of the same
result (Results vs Discussion summary) *are* equivalent.

Distinguish, when reasoning about scores:
- **model agreement** — interpretations of the *same occurrence*;
- **literature corroboration** — equivalent claims from *independent papers*.

## Abstention

Every uncertain axis may abstain (`unclear` / `unresolved`). Abstention is a correct
outcome, not an error; the harness scores selective performance (precision at the
operating threshold, and the risk/coverage curve), so annotate the *correct* answer even
when you expect the current extractor to abstain or get it wrong.

## Hard cases to include deliberately

Multiple citations in one sentence; compound / multi-clause claims (use `partial_claim`);
negation and hedging; indirect / paper-level citations; systematic reviews citing many
trials; and target papers containing several similar claims.

## Adjudication workflow

Draft annotations are proposed (here, model-drafted from the source), then a senior
annotator adjudicates. Report inter-annotator agreement per task and the adjudication
rate. In production, `ReviewDecision` records double as ongoing annotation, so the review
workflow and the evaluation pipeline share one data structure.
