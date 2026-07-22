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
  ui-design.md                 UI design, user stories, auth/session decisions
  feedback/                    External design reviews
  _quarto.yml                  Quarto website configuration
  index.qmd, about.qmd         Website landing and about pages
  styles.css                   Site styles
  _site/                       Rendered website output (build artifact)
backend/                       FastAPI service (package `interciter`), uv-managed
  interciter/                  API, ingestion, services, CLI, auth/sessions
  tests/                       Pytest suite
  Dockerfile                   API image (multi-stage, non-root)
frontend/                      React + TypeScript + Vite SPA (USWDS)
  src/                         Screens, components, API client, auth context
  Dockerfile, nginx.conf       Web image (build SPA, serve + reverse-proxy /v1)
schema/
  interciter.yaml              LinkML logical data model
  generated/                   Generated Pydantic / SQL DDL / JSON Schema
  requirements.txt             Schema tooling dependencies
docker-compose.yml             Full stack: PostgreSQL + API + web
Makefile                       Schema, backend, frontend, docker, and docs tasks
```

## Running with Docker

The whole stack — PostgreSQL (system of record), the FastAPI API, and the
nginx-served SPA — runs with [Docker Compose](https://docs.docker.com/compose/).
nginx reverse-proxies `/v1` and `/health` to the API, so the browser sees a single
origin and the BFF session cookie works without CORS.

```sh
cp .env.example .env               # set POSTGRES_PASSWORD before exposing anywhere
make docker-up                     # build + start db, api, web (detached)
make docker-seed                   # load the bundled sample corpus
make docker-admin NAME=me          # bootstrap an admin user (prints an API token)
```

The UI is then served at `http://localhost:8080`. Scale the API vertically with
more workers (`UVICORN_WORKERS` in `.env`) or horizontally behind a load balancer
(`docker compose up --scale backend=N`). Tail logs with `make docker-logs` and
stop with `make docker-down` (add `ARGS=-v` to also drop the database volume).

The compose stack runs over plain HTTP, so `SESSION_COOKIE_SECURE` defaults to
`false`; set it to `true` and terminate TLS in front for any real deployment.
See `make help` for all container targets.

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

InterCiter has a working **MVP vertical slice**: a FastAPI backend (`backend/`)
and a React + USWDS frontend (`frontend/`) implement the thin, auditable slice —
given an open-access biomedical paper, identify empirical result claims, show
their exact source passages and citation contexts, classify each cited
relationship (function + stance) with calibrated abstention, and trace one hop to
the cited paper or a confidently matched target claim. The web UI adds ingestion,
a reviewer workspace, and account management over a Backend-for-Frontend session
layer. The [design overview](docs/interciter-systems-design.md) covers scope,
deferred work, and open decisions; [docs/ui-design.md](docs/ui-design.md) covers
the UI, user stories, and auth/session design.

Run the API with `make be-serve`, the UI with `make fe-dev`, and both test suites
with `make test` (see `make help`).
