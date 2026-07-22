"""FastAPI application — the `/v1` access layer.

API-first: every feature routes through here. Default read representations are the
composed, reader-friendly views; the full audit structure sits behind explicit
evidence, revision, and run endpoints.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..db import init_db
from .routers import (
    claims,
    collections,
    discovery,
    graph,
    papers,
    relations,
    review,
    search,
    session,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="InterCiter API",
    version="0.1.0",
    description=(
        "MVP vertical slice: ingest an open-access biomedical paper, anchor empirical "
        "result claims to their source passages, classify each cited relationship "
        "(function + stance) with calibrated abstention, and trace one hop to the cited "
        "paper or a confidently matched target claim."
    ),
    lifespan=lifespan,
)

app.include_router(papers.router, prefix="/v1", tags=["papers", "jobs"])
app.include_router(claims.router, prefix="/v1", tags=["claims"])
app.include_router(collections.router, prefix="/v1", tags=["collections"])
app.include_router(search.router, prefix="/v1", tags=["search"])
app.include_router(relations.router, prefix="/v1", tags=["relations"])
app.include_router(review.router, prefix="/v1", tags=["review"])
app.include_router(graph.router, prefix="/v1", tags=["graph"])
app.include_router(discovery.router, prefix="/v1", tags=["discovery"])
app.include_router(session.router, prefix="/v1", tags=["auth"])
app.include_router(users.router, prefix="/v1", tags=["users"])


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
