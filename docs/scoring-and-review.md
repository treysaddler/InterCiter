# InterCiter — Scoring and Human Review

## Confidence signals stay decomposed

Confidence is exposed as separate signals, never compressed into one global score per claim. A single blended number — extraction confidence + review status + corroboration, with an aggregate paper trust weight feeding ranking — would fold too many distinct questions into one unexplained scalar, and it would conflate model agreement with literature corroboration, which are different kinds of evidence.

## Decomposed signals

Each signal is stored and exposed **separately**:

| Signal | Question it answers |
|---|---|
| Extraction fidelity | Did the system correctly capture and normalize the source passage? |
| Target-link confidence | Did it identify the correct cited claim? |
| Stance confidence | Did it correctly classify support / contradict / neutral? |
| Review status | Has a reviewer accepted, rejected, or modified it? |
| Model agreement | Did multiple extraction methods produce compatible interpretations of the *same occurrence*? |
| Literature evidence balance | How many *independent papers* support or contradict the proposition (via cluster membership)? |
| Source-quality assessment | What quality metadata applies to the source paper? |

The model-agreement / corroboration split is the load-bearing one:

> Two models agreeing on one sentence may reflect shared training data and correlated errors. Two independent papers making the same finding is literature corroboration. They are never summed into one number.

## Assessment records

Every derived score is a versioned **`Assessment`** record — subject, assessment type, component inputs, algorithm version, computed value, timestamp — rebuildable and explainable, never a mutable field on a claim. If a formula changes, old assessments remain inspectable and new ones are computed alongside.

Any future composite ranking score is just another `Assessment` type whose inputs are the components above, introduced only after the components are individually validated ([evaluation.md](evaluation.md)).

## Deferred: user scores and paper trust weighting

`UserScore` (per-user claim/paper scores, `scope: public | private`) and `TrustWeight` (per-user paper trust entries feeding a computed aggregate) are **deferred to phase 2**. They keep the overlay pattern — separate entities, never mutable fields on the target, no last-writer-wins — but shipping them in the MVP would import identity, moderation, abuse-control, and manipulation problems, and a scalar "trust" number risks encoding prestige and popularity bias. Before phase 2, "what exactly are users rating?" needs a real answer.

```text
UserScore  --[scores]--> ClaimInterpretation | PaperWork     (phase 2)
TrustWeight --[weighs]--> PaperWork                          (phase 2)
  user_id, value, scope: private | public, created_at
```

## Human-review workflow

Every human action is additive and lands in the system of record:

| Operation | Behavior |
|---|---|
| **Revise an interpretation** | New `ClaimInterpretation` with `parent_interpretation_ids`; original untouched. Materially different revisions mark dependent `RelationAssertion`s `stale_pending_review` ([data-model.md](data-model.md)). Restricted to original author or `reviewer`/`admin`. |
| **Create a claim** | Human-authored `ClaimOccurrence` + `ClaimInterpretation` (or interpretation-only, attached to an existing occurrence). |
| **Review an assertion** | `ReviewDecision` on a specific dimension (extraction fidelity, stance, target link) with rationale; flips the assertion's status to `accepted` / `rejected`. |
| **Fix a bad cluster** | Set the offending `ClusterMembership` to `removed`. No node reconstruction, no edge un-copying — memberships are the only thing that changes. |

`ReviewDecision`s are per-dimension deliberately: a reviewer can confirm the stance while rejecting the target link, and the evaluation pipeline consumes these as adjudicated labels.

### Review queue — phase 2

Prioritization (lowest-confidence first, contested-first, high-value-papers first) is a query over data already stored (assessments, review statuses, stance conflicts within clusters). No schema work is needed now; only the ranking policy is deferred.
