"""Monitoring API tests — saved searches + alerts (scite-parity WP8)."""

from __future__ import annotations


def _submit(client, headers, sample: str) -> dict:
    from helpers import load_sample

    resp = client.post("/v1/papers", json={"xml": load_sample(sample)}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


def _create_search(client, headers, *, q: str = "metformin", name: str = "Metformin") -> dict:
    resp = client.post(
        "/v1/saved-searches",
        json={"name": name, "query": {"q": q}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_saved_search_crud(client, user_headers):
    created = _create_search(client, user_headers)
    ss_id = created["saved_search_id"]
    assert created["query"]["q"] == "metformin"

    listed = client.get("/v1/saved-searches", headers=user_headers)
    assert [s["saved_search_id"] for s in listed.json()] == [ss_id]

    patched = client.patch(
        f"/v1/saved-searches/{ss_id}",
        json={"name": "Renamed"},
        headers=user_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"

    deleted = client.delete(f"/v1/saved-searches/{ss_id}", headers=user_headers)
    assert deleted.status_code == 204
    assert client.get(f"/v1/saved-searches/{ss_id}", headers=user_headers).status_code == 404


def test_saved_search_alerts_on_new_matches(client, user_headers):
    # Baseline the search BEFORE any matching claims exist.
    ss = _create_search(client, user_headers, q="metformin")
    ss_id = ss["saved_search_id"]

    # First run with no corpus: nothing new.
    first = client.post(f"/v1/saved-searches/{ss_id}/run", headers=user_headers)
    assert first.status_code == 200
    assert first.json()["created_count"] == 0

    # Ingest papers that produce metformin claims.
    _submit(client, user_headers, "paper_b.xml")
    _submit(client, user_headers, "paper_a.xml")

    run = client.post(f"/v1/saved-searches/{ss_id}/run", headers=user_headers)
    assert run.status_code == 200
    body = run.json()
    assert body["created_count"] >= 1
    assert all(a["alert_type"] == "new_claim" for a in body["alerts"])
    assert all(a["source_type"] == "saved_search" for a in body["alerts"])

    # Re-running without new data yields nothing (baseline advanced).
    again = client.post(f"/v1/saved-searches/{ss_id}/run", headers=user_headers)
    assert again.json()["created_count"] == 0


def test_created_search_baselines_existing_hits(client, user_headers):
    # Corpus already has metformin claims when the search is created.
    _submit(client, user_headers, "paper_b.xml")
    _submit(client, user_headers, "paper_a.xml")

    ss = _create_search(client, user_headers, q="metformin")
    ss_id = ss["saved_search_id"]

    # The first run must NOT alert on pre-existing hits.
    run = client.post(f"/v1/saved-searches/{ss_id}/run", headers=user_headers)
    assert run.json()["created_count"] == 0


def test_alerts_list_and_read_flow(client, user_headers):
    ss = _create_search(client, user_headers, q="metformin")
    ss_id = ss["saved_search_id"]
    _submit(client, user_headers, "paper_b.xml")
    _submit(client, user_headers, "paper_a.xml")
    client.post(f"/v1/saved-searches/{ss_id}/run", headers=user_headers)

    alerts = client.get("/v1/alerts", headers=user_headers).json()
    assert len(alerts) >= 1
    unread = client.get("/v1/alerts?unread_only=true", headers=user_headers).json()
    assert len(unread) == len(alerts)

    first_id = alerts[0]["alert_id"]
    read = client.post(f"/v1/alerts/{first_id}/read", headers=user_headers)
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    remaining = client.get("/v1/alerts?unread_only=true", headers=user_headers).json()
    assert len(remaining) == len(alerts) - 1

    marked = client.post("/v1/alerts/read-all", headers=user_headers)
    assert marked.status_code == 200
    assert marked.json()["marked_read"] == len(remaining)
    assert client.get("/v1/alerts?unread_only=true", headers=user_headers).json() == []


def test_run_all_covers_watched_collections(client, user_headers):
    # A watched collection whose member gains a supporting citation after baseline.
    paper_b = _submit(client, user_headers, "paper_b.xml")
    work_b = paper_b["result"]["work_id"]

    coll = client.post(
        "/v1/collections", json={"name": "Watched"}, headers=user_headers
    ).json()
    coll_id = coll["collection_id"]
    client.post(
        f"/v1/collections/{coll_id}/members",
        json={"work_ids": [work_b]},
        headers=user_headers,
    )
    # Watch captures the baseline (no supporting citation yet).
    client.post(
        f"/v1/collections/{coll_id}/watch", json={"watch": True}, headers=user_headers
    )

    # A new citing paper supports work_b.
    _submit(client, user_headers, "paper_a.xml")

    run = client.post("/v1/alerts/run", headers=user_headers)
    assert run.status_code == 200
    body = run.json()
    assert body["created_count"] >= 1
    assert any(
        a["alert_type"] == "new_support" and a["work_id"] == work_b
        for a in body["alerts"]
    )

    # Baseline advanced: a second run reports nothing new.
    assert client.post("/v1/alerts/run", headers=user_headers).json()["created_count"] == 0


def test_run_all_alerts_on_new_retraction(client, user_headers, session):
    from interciter import models

    paper_b = _submit(client, user_headers, "paper_b.xml")
    work_b = paper_b["result"]["work_id"]
    coll_id = client.post(
        "/v1/collections", json={"name": "Integrity"}, headers=user_headers
    ).json()["collection_id"]
    client.post(
        f"/v1/collections/{coll_id}/members",
        json={"work_ids": [work_b]},
        headers=user_headers,
    )
    client.post(
        f"/v1/collections/{coll_id}/watch", json={"watch": True}, headers=user_headers
    )

    # The member becomes retracted after the baseline.
    work = session.get(models.PaperWork, work_b)
    work.is_retracted = True
    session.commit()

    run = client.post("/v1/alerts/run", headers=user_headers)
    assert any(
        a["alert_type"] == "retraction" and a["work_id"] == work_b
        for a in run.json()["alerts"]
    )


def test_saved_search_ownership_and_auth(client, make_user):
    _, owner_headers = make_user(name="owner3")
    _, other_headers = make_user(name="other3")
    ss_id = _create_search(client, owner_headers)["saved_search_id"]

    assert client.get(f"/v1/saved-searches/{ss_id}", headers=other_headers).status_code == 404
    assert (
        client.post(f"/v1/saved-searches/{ss_id}/run", headers=other_headers).status_code
        == 404
    )
    assert client.delete(f"/v1/saved-searches/{ss_id}", headers=other_headers).status_code == 404

    # Anonymous access is rejected.
    assert client.get("/v1/saved-searches").status_code == 401
    assert client.get("/v1/alerts").status_code == 401
    assert client.post("/v1/alerts/run").status_code == 401


def test_alerts_are_owner_scoped(client, make_user):
    _, owner_headers = make_user(name="owner4")
    _, other_headers = make_user(name="other4")

    ss_id = _create_search(client, owner_headers, q="metformin")["saved_search_id"]
    _submit(client, owner_headers, "paper_b.xml")
    _submit(client, owner_headers, "paper_a.xml")
    client.post(f"/v1/saved-searches/{ss_id}/run", headers=owner_headers)

    # The other user sees none of the owner's alerts.
    assert client.get("/v1/alerts", headers=other_headers).json() == []
