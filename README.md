# InterCiter

A provenance-first knowledge-graph system that extracts claims from scientific
papers, **anchors each claim to its exact source passage**, and classifies how
citing claims relate to cited work — separating a citation's *function*
(background, method, direct evidence, comparison) from its *stance* (support,
contradict, neutral). Walking these relations traces a claim back to its earlier
cited antecedents within the traversed corpus.

This repository holds the **design** for InterCiter: a systems-design overview,
detailed design docs, an executable [LinkML](https://linkml.io) schema, and
external design reviews. It is published as a [Quarto](https://quarto.org)
website (`docs/_site/`).

## Design philosophy

InterCiter is **provenance-first**. Model outputs, human corrections, cluster
groupings, and review decisions coexist as distinct, immutable, traceable
records. What the paper says (`ClaimOccurrence`) is never overwritten by what a
model thinks it means (`ClaimInterpretation`); uncertainty is expressed by
**abstaining** (`unresolved`), never by overclaiming. The system builds on
established infrastructure — BioLink, RoboKop, and Semantic Scholar — and its
research contribution is captured in three testable hypotheses: source-grounded
extraction, selective claim alignment, and auditable lineage.

## Where to start

- **Design Overview** — [docs/interciter-systems-design.md](docs/interciter-systems-design.md):
  summary, principles, MVP scope, key decisions, and open questions. This is the
  entry point.
- **Detailed design** — the design docs in [docs/](docs/):
  - [Data model](docs/data-model.md) — the immutable logical model: papers/versions/passages,
    occurrences vs. interpretations, revision graph, soft clustering, first-class
    relation assertions, BioLink mapping.
  - [Architecture](docs/architecture.md) — layers; write model vs. read projection;
    Semantic Scholar integration; availability states; async jobs; ingestion security.
  - [Scoring & review](docs/scoring-and-review.md) — decomposed confidence signals,
    Assessment records, review workflow, deferred user/trust scoring.
  - [Evaluation](docs/evaluation.md) — gold corpus, per-stage metrics, calibration
    and abstention, S2 intent as weak supervision.
  - [API](docs/api.md) — the `/v1` surface: jobs/runs, evidence endpoints,
    revisions, bounded traversal.
  - [Grant framing](docs/grant-framing.md) — three hypotheses, precise claims,
    budget honesty, domain-scope framing.
- **Schema** — [schema/interciter.yaml](schema/interciter.yaml): the logical data
  model as an executable, BioLink-aligned LinkML schema, with generated Pydantic
  models, SQL DDL, and JSON Schema in [schema/generated/](schema/generated/).
- **External feedback** — supplementary design reviews:
  [0001](docs/feedback/0001-gpt-5.6-sol-pro-feedback.md) ·
  [0002](docs/feedback/0002-gemini-3.1-pro-feedback.md) ·
  [0003](docs/feedback/0003-claude-opus-4.8-feedback.md).

## Repository structure

```
docs/                          Documentation & Quarto site
  interciter-systems-design.md Design overview (entry point)
  data-model.md, ...           Detailed design documents
  feedback/                    External design reviews
  _quarto.yml                  Quarto website configuration
  index.qmd, about.qmd         Website landing and about pages
  styles.css                   Site styles
  _site/                       Rendered website output (build artifact)
schema/
  interciter.yaml              LinkML logical data model
  generated/                   Generated Pydantic / SQL DDL / JSON Schema
  requirements.txt             Schema tooling dependencies
Makefile                       Schema validation and code-generation tasks
```

## Working with the schema

The logical data model is written once in [schema/interciter.yaml](schema/interciter.yaml)
and generates downstream artifacts. Tasks require [`uv`](https://docs.astral.sh/uv/).

```sh
make help        # List available targets
make lint        # Validate the schema
make pydantic    # Generate Pydantic models  -> schema/generated/models.py
make sqlddl      # Generate SQL DDL           -> schema/generated/schema.sql
make jsonschema  # Generate JSON Schema       -> schema/generated/schema.json
make all         # Validate and generate everything
make clean       # Remove generated artifacts
```

## Building the website

The design is published as a Quarto website. With [Quarto](https://quarto.org)
installed, run from the `docs/` directory:

```sh
cd docs
quarto preview   # Live-reloading local preview
quarto render    # Build the static site into docs/_site/
```

The full design (overview plus all design docs, excluding the feedback files) is
also available as a single Word document for offline reading and comments.

## Status

InterCiter is at the **design stage**. The MVP is scoped as a thin, auditable
vertical slice: given an open-access biomedical paper, identify empirical result
claims, show their exact source passages and citation contexts, classify each
cited relationship (function + stance) with calibrated abstention, and trace one
hop to the cited paper or a confidently matched target claim. See the
[design overview](docs/interciter-systems-design.md) for MVP scope, deferred work, and
open decisions.
