# InterCiter — Grant Framing

## Three explicit hypotheses

The proposal is stronger presented as a research system testing three falsifiable hypotheses, each with its own metrics ([evaluation.md](evaluation.md)):

1. **Source-grounded extraction.** Scientific claim interpretations can be generated while preserving exact, inspectable evidence anchors (passage, offsets, verbatim text, paper version).
2. **Selective claim alignment.** Citation contexts can be linked to specific cited claims at useful precision *when the system is allowed to abstain* — the risk/coverage tradeoff is the result, not a footnote.
3. **Auditable lineage.** Immutable, versioned relation assertions let users inspect how every step in a citation lineage was generated, reviewed, or revised.

## Language corrections

Two places where the original framing overstated feasibility:

- **"Trace claims back to their original sources" → soften.** A citation graph identifies an *earlier cited antecedent*, or the earliest source found *within the traversed corpus*. It cannot prove intellectual originality — papers omit citations, cite secondary sources, and independently derive similar findings. The honest claim is still valuable; the overstated one is attackable.
- **"Automated deduplication is safe because merges are reversible" → replace with:**

  > Automated clustering is non-destructive, measurable, and reversible — but uncertain clusters do not become authoritative without meeting a validated threshold or receiving review.

  Reversibility bounds duration of damage, not blast radius; the design change backing this wording is in [data-model.md](data-model.md).

## Narrative

Unchanged and still the strongest part: InterCiter **builds on existing infrastructure** (BioLink schema extension, RoboKop provenance plumbing, Semantic Scholar paper/citation substrate) rather than re-solving bibliographic parsing. Its novelty is precisely the three hypotheses: source-grounded claim extraction, selective alignment, and auditable lineage. The revised relation model strengthens the BioLink story — evidence-bearing `RelationAssertion`s map naturally onto BioLink's provenance-heavy association pattern.

## Budget honesty

Two costs are named up front rather than discovered later:

- **The adjudicated annotation corpus is the budget crux.** Guideline development, multi-annotator labeling, agreement analysis, and adjudication are the largest non-engineering line item — and a legitimate thing to request funding for, since the corpus is itself a reusable contribution.
- **LLM extraction cost at corpus scale** is a reported evaluation metric (cost per paper) and a feasibility parameter, interacting with model choice and any multi-model comparison.

## Domain scope, decided deliberately

The MVP narrows to **empirical result claims in one open-access biomedical subdomain** (see [../interciter-systems-design.md](../interciter-systems-design.md)). Domain-agnostic remains the stated long-term direction, framed as: the *architecture* (evidence anchoring, assertion model, abstention) is domain-neutral; the *vocabularies* (entity categories, qualifier sets) are domain plugins, with BioLink as the first. This turns the narrowing into a design statement rather than a retreat.
