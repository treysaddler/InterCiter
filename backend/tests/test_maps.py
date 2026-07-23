"""Saved maps API tests (litmaps-parity WP-L2)."""

from __future__ import annotations


def _submit(client, headers, sample: str) -> str:
    from helpers import load_sample

    resp = client.post("/v1/papers", json={"xml": load_sample(sample)}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()["result"]["work_id"]


def _create_map(client, headers, **kwargs) -> dict:
    body = {"name": "T2D map", **kwargs}
    resp = client.post("/v1/maps", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_list_get_update_delete_map(client, user_headers):
    created = _create_map(
        client,
        user_headers,
        description="glycemic control",
        layout_config={"layout": "axis", "xMeasure": "year"},
    )
    map_id = created["map_id"]
    assert created["layout_config"]["layout"] == "axis"
    assert created["member_count"] == 0

    listed = client.get("/v1/maps", headers=user_headers)
    assert listed.status_code == 200
    assert [row["map_id"] for row in listed.json()] == [map_id]

    patched = client.patch(
        f"/v1/maps/{map_id}",
        json={"name": "Renamed", "layout_config": {"layout": "force"}},
        headers=user_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["layout_config"] == {"layout": "force"}

    deleted = client.delete(f"/v1/maps/{map_id}", headers=user_headers)
    assert deleted.status_code == 204
    assert client.get(f"/v1/maps/{map_id}", headers=user_headers).status_code == 404


def test_create_map_with_seed_set_and_render_graph(client, user_headers):
    b = _submit(client, user_headers, "paper_b.xml")
    a = _submit(client, user_headers, "paper_a.xml")
    created = _create_map(client, user_headers, work_ids=[a, b])
    map_id = created["map_id"]
    assert created["member_count"] == 2
    assert {m["work_id"] for m in created["members"]} == {a, b}

    # The map graph renders exactly the seed set with the A→B citation edge.
    graph = client.get(f"/v1/maps/{map_id}/graph", headers=user_headers)
    assert graph.status_code == 200
    view = graph.json()
    paper_ids = {n["id"] for n in view["nodes"] if n["type"] == "paper"}
    assert paper_ids == {a, b}
    assert any(
        e["source"] == a and e["target"] == b
        for e in view["edges"]
        if e["type"] == "cites"
    )


def test_add_members_idempotent_and_remove(client, user_headers):
    b = _submit(client, user_headers, "paper_b.xml")
    a = _submit(client, user_headers, "paper_a.xml")
    map_id = _create_map(client, user_headers)["map_id"]

    add = client.post(
        f"/v1/maps/{map_id}/members", json={"work_ids": [a, b]}, headers=user_headers
    )
    assert add.status_code == 200
    assert add.json()["member_count"] == 2

    # Re-adding the same works does not duplicate membership.
    again = client.post(
        f"/v1/maps/{map_id}/members", json={"work_ids": [a, b]}, headers=user_headers
    )
    assert again.json()["member_count"] == 2

    removed = client.delete(f"/v1/maps/{map_id}/members/{a}", headers=user_headers)
    assert removed.status_code == 204
    assert client.get(f"/v1/maps/{map_id}", headers=user_headers).json()["member_count"] == 1
    # Removing a non-member is a 404.
    assert (
        client.delete(f"/v1/maps/{map_id}/members/{a}", headers=user_headers).status_code
        == 404
    )


def test_update_member_note_and_position(client, user_headers):
    a = _submit(client, user_headers, "paper_a.xml")
    map_id = _create_map(client, user_headers, work_ids=[a])["map_id"]

    patched = client.patch(
        f"/v1/maps/{map_id}/members/{a}",
        json={"note": "key trial", "position": {"x": 10, "y": 20}},
        headers=user_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["note"] == "key trial"
    assert patched.json()["position"] == {"x": 10, "y": 20}

    detail = client.get(f"/v1/maps/{map_id}", headers=user_headers).json()
    assert detail["members"][0]["note"] == "key trial"


def test_map_is_owner_scoped(client, user_headers, make_user):
    map_id = _create_map(client, user_headers)["map_id"]
    other_headers = make_user(name="intruder")[1]
    # Another user cannot see, render, or mutate the map — reported as missing.
    assert client.get(f"/v1/maps/{map_id}", headers=other_headers).status_code == 404
    assert client.get(f"/v1/maps/{map_id}/graph", headers=other_headers).status_code == 404
    assert (
        client.patch(f"/v1/maps/{map_id}", json={"name": "x"}, headers=other_headers).status_code
        == 404
    )
    # And it is not listed for them.
    assert client.get("/v1/maps", headers=other_headers).json() == []


def test_maps_require_auth(client):
    assert client.get("/v1/maps").status_code == 401
    assert client.post("/v1/maps", json={"name": "x"}).status_code == 401


def test_share_mint_is_idempotent_and_grants_public_read(client, user_headers):
    b = _submit(client, user_headers, "paper_b.xml")
    a = _submit(client, user_headers, "paper_a.xml")
    map_id = _create_map(
        client, user_headers, work_ids=[a, b], layout_config={"layout": "force"}
    )["map_id"]

    minted = client.post(f"/v1/maps/{map_id}/share", headers=user_headers)
    assert minted.status_code == 200
    token = minted.json()["share_token"]
    assert token
    assert minted.json()["map_id"] == map_id

    # Re-sharing returns the SAME token so links stay stable.
    again = client.post(f"/v1/maps/{map_id}/share", headers=user_headers)
    assert again.json()["share_token"] == token

    # The owner sees the token on their own map view; anyone with the token can read
    # it WITHOUT auth, and owner identity is never exposed.
    owner_view = client.get(f"/v1/maps/{map_id}", headers=user_headers).json()
    assert owner_view["share_token"] == token

    public = client.get(f"/v1/shared-maps/{token}")
    assert public.status_code == 200
    body = public.json()
    assert body["map_id"] == map_id
    assert body["member_count"] == 2
    assert "owner_id" not in body

    graph = client.get(f"/v1/shared-maps/{token}/graph")
    assert graph.status_code == 200
    paper_ids = {n["id"] for n in graph.json()["nodes"] if n["type"] == "paper"}
    assert paper_ids == {a, b}


def test_share_revoke_makes_token_unresolvable(client, user_headers):
    map_id = _create_map(client, user_headers)["map_id"]
    token = client.post(f"/v1/maps/{map_id}/share", headers=user_headers).json()[
        "share_token"
    ]
    assert client.get(f"/v1/shared-maps/{token}").status_code == 200

    revoked = client.delete(f"/v1/maps/{map_id}/share", headers=user_headers)
    assert revoked.status_code == 204
    # The old link no longer resolves, and the owner view no longer carries a token.
    assert client.get(f"/v1/shared-maps/{token}").status_code == 404
    assert client.get(f"/v1/shared-maps/{token}/graph").status_code == 404
    owner_view = client.get(f"/v1/maps/{map_id}", headers=user_headers).json()
    assert owner_view["share_token"] is None


def test_shared_map_unknown_token_is_404(client):
    assert client.get("/v1/shared-maps/does-not-exist").status_code == 404
    assert client.get("/v1/shared-maps/does-not-exist/graph").status_code == 404


def test_share_is_owner_scoped_and_requires_auth(client, user_headers, make_user):
    map_id = _create_map(client, user_headers)["map_id"]
    other_headers = make_user(name="intruder")[1]
    # A non-owner cannot mint or revoke a share for someone else's map.
    assert client.post(f"/v1/maps/{map_id}/share", headers=other_headers).status_code == 404
    assert client.delete(f"/v1/maps/{map_id}/share", headers=other_headers).status_code == 404
    # And anonymous callers cannot share at all.
    assert client.post(f"/v1/maps/{map_id}/share").status_code == 401


# ---------------------------------------------------------------------------------
# WP-L5 — map monitoring (extends the scite WP8 alerts subsystem)
# ---------------------------------------------------------------------------------


def test_map_watch_toggle_state(client, user_headers):
    map_id = _create_map(client, user_headers)["map_id"]

    on = client.post(
        f"/v1/maps/{map_id}/watch", json={"watch": True}, headers=user_headers
    )
    assert on.status_code == 200
    assert on.json()["is_watched"] is True
    assert on.json()["watch_last_checked_at"] is None
    assert client.get(f"/v1/maps/{map_id}", headers=user_headers).json()["is_watched"] is True

    off = client.post(
        f"/v1/maps/{map_id}/watch", json={"watch": False}, headers=user_headers
    )
    assert off.status_code == 200
    assert off.json()["is_watched"] is False


def test_map_monitor_seeds_then_alerts_on_new_connection(
    client, session, make_user, monkeypatch
):
    from interciter import models
    from interciter.enums import AvailabilityState
    from interciter.services import enrichment

    _owner_id, headers = make_user(name="map-watcher")

    # Two seed works with DOIs so discovery resolves a Semantic Scholar id for each.
    for wid, doi in (("seed_a", "10.1/a"), ("seed_b", "10.1/b")):
        session.add(
            models.PaperWork(
                work_id=wid,
                availability_state=AvailabilityState.metadata_stub,
                doi=doi,
            )
        )
    session.commit()

    refs = {
        "DOI:10.1/a": [
            {
                "cited_corpus_id": "100",
                "cited_doi": None,
                "cited_pmid": None,
                "cited_title": "Shared reference",
                "cited_year": 2020,
                "is_influential": True,
            }
        ],
        "DOI:10.1/b": [
            {
                "cited_corpus_id": "100",
                "cited_doi": None,
                "cited_pmid": None,
                "cited_title": "Shared reference",
                "cited_year": 2020,
                "is_influential": False,
            }
        ],
    }
    monkeypatch.setattr(
        enrichment, "reference_links", lambda pid, **kw: list(refs.get(pid, []))
    )

    map_id = _create_map(client, headers, work_ids=["seed_a", "seed_b"])["map_id"]
    watched = client.post(
        f"/v1/maps/{map_id}/watch", json={"watch": True}, headers=headers
    )
    assert watched.json()["is_watched"] is True

    # First monitor run only seeds the baseline — no alerts for existing candidates.
    first = client.post(f"/v1/maps/{map_id}/monitor", headers=headers)
    assert first.status_code == 200
    assert first.json()["created_count"] == 0
    # The run stamps a checked-at timestamp.
    assert client.get(f"/v1/maps/{map_id}", headers=headers).json()[
        "watch_last_checked_at"
    ] is not None

    # An unchanged second run surfaces nothing new.
    assert client.post(f"/v1/maps/{map_id}/monitor", headers=headers).json()[
        "created_count"
    ] == 0

    # A newly connected paper appears in discovery → one alert on the next run.
    refs["DOI:10.1/a"].append(
        {
            "cited_corpus_id": "200",
            "cited_doi": None,
            "cited_pmid": None,
            "cited_title": "Brand new connection",
            "cited_year": 2023,
            "is_influential": False,
        }
    )
    third = client.post(f"/v1/maps/{map_id}/monitor", headers=headers)
    assert third.json()["created_count"] == 1
    assert "Brand new connection" in third.json()["alerts"][0]["summary"]

    # And it is visible in the shared alert feed as a map source.
    feed = client.get("/v1/alerts", headers=headers).json()
    assert any(
        a["source_type"] == "map" and a["alert_type"] == "new_connected_paper"
        for a in feed
    )


def test_map_watch_and_monitor_are_owner_scoped_and_require_auth(
    client, user_headers, make_user
):
    map_id = _create_map(client, user_headers)["map_id"]
    other_headers = make_user(name="intruder")[1]

    assert client.post(
        f"/v1/maps/{map_id}/watch", json={"watch": True}, headers=other_headers
    ).status_code == 404
    assert client.post(
        f"/v1/maps/{map_id}/monitor", headers=other_headers
    ).status_code == 404
    assert client.post(f"/v1/maps/{map_id}/watch", json={"watch": True}).status_code == 401
    assert client.post(f"/v1/maps/{map_id}/monitor").status_code == 401
