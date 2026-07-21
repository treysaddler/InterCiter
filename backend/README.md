# InterCiter — MVP backend

A thin, auditable vertical slice of the [InterCiter design](../interciter-systems-design.md):
given an open-access biomedical paper (JATS XML), it anchors empirical result claims to
their exact source passages, classifies each cited relationship (function + stance) with
calibrated abstention, and traces **one hop** to the cited paper or a confidently matched
target claim — all through an API-first `/v1` surface.

The rich, immutable logical model is the system of record; reads are served by a derived,
rebuildable projection. Nothing scientific is ever overwritten.

## Layout

```
interciter/
  config.py            Environment-driven settings (SQLite dev, Postgres prod)
  enums.py             Controlled vocabularies (mirror the LinkML schema)
  models.py            SQLAlchemy ORM — the immutable system of record
  schemas.py           Pydantic API DTOs (composed reader views + audit views)
  db.py                Engine / session / init_db
  ids.py               Prefixed opaque id generation
  auth.py              Principals, token hashing, role/ownership core
  ingestion/
    parser.py          Hardened JATS/PMC XML parser (defusedxml)
    extractor.py       Swappable extraction interface + deterministic stub
    pipeline.py        Ingest -> passages, claims, relations, clustering
  services/
    projection.py      Composed claim views, one-hop trace, decomposed scores
    jobs.py            First-class job resources (polling model) + idempotency
    review.py          Human claims, revisions, review decisions, cluster fixes
  api/                 FastAPI app + /v1 routers (incl. security.py auth deps)
  data/sample/         Two bundled JATS papers for the demo corpus
  sample.py            Seed the sample corpus
  cli.py               initdb / ingest / seed / serve
```

## Quick start

Requires [`uv`](https://docs.astral.sh/uv/).

```sh
cd backend
uv venv --python 3.13
uv pip install -e '.[dev]'

uv run pytest                      # run the test suite
uv run interciter seed             # ingest the bundled sample corpus
uv run interciter useradd me --role admin   # create a user, prints a bearer token
uv run interciter serve --reload   # run the API at http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000/docs> for the interactive API, or:

```sh
uv run interciter ingest interciter/data/sample/paper_a.xml
```

## Auth

Minimal role-based auth (`user` / `reviewer` / `admin`) plus first-class ownership, modeled
from day one because retrofitting it is painful. Reads are open in the MVP; writes require a
`Authorization: Bearer <token>` header. Create the first admin with `interciter useradd`, then
manage further users through `POST /v1/users` (admin only). Tokens are stored only as hashes.

- Submitting a paper records the submitter as the job owner.
- Revising an interpretation is restricted to its author or a `reviewer`/`admin`.
- Review decisions and cluster-member removal require `reviewer`/`admin`.

## What the vertical slice demonstrates

- **Evidence anchoring** — every claim and relation response embeds its source passage
  (verbatim text + offsets + version + work).
- **Occurrence vs interpretation** — the immutable "what the paper says" is kept distinct
  from "what the extractor thinks it means".
- **Four independent relation axes** — function, stance, scope, resolution.
- **Honest resolution with abstention** — claim-level when confident, an explicit
  paper-level fallback with ranked candidates otherwise, and `unclear`/`unresolved` when
  the signal is weak.
- **Soft clustering** — high-precision, reversible membership rows; corroboration counts
  independent papers, kept separate from model agreement.
- **Provenance** — every record points back to an `ExtractionRun`.
- **Ingestion hardening** — size limits, `defusedxml` parsing, strict schema validation,
  and paper text treated strictly as data.
- **Minimal roles + first-class ownership** — `reviewer`/`admin` gating and owner-scoped
  edits, enforced on writes while reads stay open.

## Configuration

Settings are environment-driven with the `INTERCITER_` prefix, e.g.:

```sh
export INTERCITER_DATABASE_URL="postgresql+psycopg://user:pass@localhost/interciter"
```

The default is a local SQLite file (`interciter.db`) so the MVP runs with zero
infrastructure. Table creation uses `create_all` for the MVP; production would use
migrations.
