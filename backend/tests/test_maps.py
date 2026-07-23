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
