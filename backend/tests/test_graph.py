"""Graph service + /v1/graph API tests: papers, authors, citations, claims, expansion."""

from __future__ import annotations

from interciter import models
from interciter.enums import AvailabilityState
from interciter.ingestion.pipeline import ingest_paper
from interciter.services import enrichment, graph

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    session.commit()
    return b, a


def test_paper_graph_has_nodes_and_citation_edge(session):
    b, a = _ingest_both(session)
    view = graph.build_paper_graph(session)

    paper_nodes = {n.id: n for n in view.nodes if n.type == "paper"}
    assert a.work_id in paper_nodes
    assert b.work_id in paper_nodes

    cites = [e for e in view.edges if e.type == "cites"]
    assert any(e.source == a.work_id and e.target == b.work_id for e in cites), (
        "expected an A→B citation edge from the resolved mention"
    )
    # No self-loops.
    assert all(e.source != e.target for e in view.edges)


def test_include_authors_adds_author_nodes_and_edges(session):
    work = models.PaperWork(
        work_id="work_authors",
        title="A paper",
        authors=["Jane Doe", "John Roe"],
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    session.commit()

    without = graph.build_paper_graph(session, include_authors=False)
    assert all(n.type != "author" for n in without.nodes)

    with_authors = graph.build_paper_graph(session, include_authors=True)
    author_nodes = [n for n in with_authors.nodes if n.type == "author"]
    assert {n.label for n in author_nodes} >= {"Jane Doe", "John Roe"}
    authored = [e for e in with_authors.edges if e.type == "authored"]
    assert all(e.target == "work_authors" for e in authored)


def test_neighborhood_centers_and_includes_citation(session):
    b, a = _ingest_both(session)
    view = graph.paper_neighborhood(session, a.work_id, depth=1)
    assert view.center_id == a.work_id
    node_ids = {n.id for n in view.nodes}
    assert a.work_id in node_ids
    assert b.work_id in node_ids  # one hop away via the citation edge


def test_neighborhood_missing_work_raises(session):
    import pytest

    with pytest.raises(KeyError):
        graph.paper_neighborhood(session, "work_does_not_exist")


def test_claim_graph_edges_are_function_tagged(session):
    _ingest_both(session)
    view = graph.claim_graph(session)
    assert all(n.type == "claim" for n in view.nodes)
    relates = [e for e in view.edges if e.type == "relates"]
    assert relates, "expected at least one claim-resolved relation edge"
    edge = relates[0]
    assert {edge.source, edge.target} <= {n.id for n in view.nodes}
    assert "function" in edge.data


def test_expand_creates_stub_works_and_edges_idempotently(session, monkeypatch):
    work = models.PaperWork(
        work_id="work_expand",
        title="Citing paper",
        doi="10.1000/citing",
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    session.commit()

    fake_links = [
        {
            "cited_corpus_id": "111",
            "cited_doi": "10.1000/ref-one",
            "cited_pmid": None,
            "cited_title": "Reference one",
            "contexts": ["... as shown ..."],
            "intents": ["background"],
            "is_influential": True,
        },
        {
            "cited_corpus_id": "222",
            "cited_doi": None,
            "cited_pmid": "999",
            "cited_title": "Reference two",
            "contexts": [],
            "intents": [],
            "is_influential": False,
        },
    ]
    monkeypatch.setattr(enrichment, "reference_links", lambda *a, **k: fake_links)

    result = graph.expand_from_semantic_scholar(session, work, use_cache=False)
    assert result.references_fetched == 2
    assert result.works_created == 2
    assert result.edges_created == 2
    edges = session.query(models.CitationEdge).all()
    assert {e.source for e in edges} == {"semantic_scholar"}
    assert all(e.citing_work_id == "work_expand" for e in edges)

    # Re-expanding is idempotent: the stubs resolve, no new edges.
    again = graph.expand_from_semantic_scholar(session, work, use_cache=False)
    assert again.works_created == 0
    assert again.edges_created == 0


def test_expand_skips_when_unidentifiable(session, monkeypatch):
    work = models.PaperWork(
        work_id="work_noid",
        title="No identifiers",
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    session.commit()
    called = False

    def _should_not_call(*a, **k):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(enrichment, "reference_links", _should_not_call)
    result = graph.expand_from_semantic_scholar(session, work)
    assert result.skipped_reason is not None
    assert called is False


# --- API surface ------------------------------------------------------------------


def test_graph_papers_endpoint_open(client, user_headers):
    from helpers import load_sample as _load

    client.post("/v1/papers", json={"xml": _load("paper_b.xml")}, headers=user_headers)
    client.post("/v1/papers", json={"xml": _load("paper_a.xml")}, headers=user_headers)

    resp = client.get("/v1/graph/papers?include_authors=false")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(n["type"] == "paper" for n in body["nodes"])
    assert "edges" in body and "truncated" in body


def test_graph_neighborhood_404(client):
    assert client.get("/v1/graph/papers/nope").status_code == 404


def test_expand_requires_auth(client, user_headers):
    client.post("/v1/papers", json={"xml": load_sample("paper_a.xml")}, headers=user_headers)
    work_id = client.get("/v1/papers").json()[0]["work_id"]
    # No auth header → write is rejected.
    assert client.post(f"/v1/graph/papers/{work_id}/expand").status_code in (401, 403)


def test_robokop_expansion_stubbed(client, user_headers):
    _ingest = client.post(
        "/v1/papers", json={"xml": load_sample("paper_a.xml")}, headers=user_headers
    )
    assert _ingest.status_code == 202
    # A real interpretation id is required to reach the 501 (else 404).
    claims = client.get("/v1/graph/claims").json()["nodes"]
    if claims:
        resp = client.post(
            f"/v1/graph/claims/{claims[0]['id']}/expand-robokop", headers=user_headers
        )
        assert resp.status_code == 501
