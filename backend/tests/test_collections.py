"""Collections API tests (scite-parity WP4, F5)."""

from __future__ import annotations


def _create_collection(client, headers, name: str = "T2D Core") -> dict:
    resp = client.post(
        "/v1/collections",
        json={"name": name, "description": "priority evidence set"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _submit(client, headers, sample: str) -> dict:
    from helpers import load_sample

    resp = client.post("/v1/papers", json={"xml": load_sample(sample)}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


def test_create_list_update_delete_collection(client, user_headers):
    created = _create_collection(client, user_headers)
    collection_id = created["collection_id"]

    listed = client.get("/v1/collections", headers=user_headers)
    assert listed.status_code == 200
    assert [row["collection_id"] for row in listed.json()] == [collection_id]

    patched = client.patch(
        f"/v1/collections/{collection_id}",
        json={"name": "Updated Core"},
        headers=user_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Updated Core"

    deleted = client.delete(f"/v1/collections/{collection_id}", headers=user_headers)
    assert deleted.status_code == 204
    assert client.get(f"/v1/collections/{collection_id}", headers=user_headers).status_code == 404


def test_collection_members_work_id_and_identifier_batch(client, user_headers):
    collection = _create_collection(client, user_headers)
    collection_id = collection["collection_id"]

    paper = _submit(client, user_headers, "paper_b.xml")
    work_id = paper["result"]["work_id"]

    add = client.post(
        f"/v1/collections/{collection_id}/members",
        json={
            "work_ids": [work_id],
            "dois": ["10.1000/demo-doi"],
            "csv_text": "10.2000/demo-csv, 12345678",
        },
        headers=user_headers,
    )
    assert add.status_code == 200, add.text
    body = add.json()
    assert body["added_count"] >= 3
    assert len(body["created_stub_work_ids"]) >= 1

    detail = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    assert detail.status_code == 200
    assert detail.json()["member_count"] >= 3


def test_collection_detail_can_include_member_citation_tallies(client, user_headers):
    _submit(client, user_headers, "paper_b.xml")
    paper = _submit(client, user_headers, "paper_a.xml")
    work_id = paper["result"]["work_id"]

    collection_id = _create_collection(client, user_headers)["collection_id"]
    add = client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": [work_id]},
        headers=user_headers,
    )
    assert add.status_code == 200

    detail = client.get(
        f"/v1/collections/{collection_id}",
        params={"include_member_tallies": "true"},
        headers=user_headers,
    )
    assert detail.status_code == 200
    members = detail.json()["members"]
    assert len(members) == 1
    assert members[0]["citation_tallies"] is not None
    assert "total" in members[0]["citation_tallies"]
    assert detail.json()["aggregate_citation_tallies"] is not None


def test_collection_detail_member_sorting_controls(client, user_headers):
    _submit(client, user_headers, "paper_b.xml")
    paper_a = _submit(client, user_headers, "paper_a.xml")
    paper_b = _submit(client, user_headers, "paper_b.xml")

    coll_id = _create_collection(client, user_headers)["collection_id"]
    add = client.post(
        f"/v1/collections/{coll_id}/members",
        json={"work_ids": [paper_a["result"]["work_id"], paper_b["result"]["work_id"]]},
        headers=user_headers,
    )
    assert add.status_code == 200

    by_support = client.get(
        f"/v1/collections/{coll_id}",
        params={
            "include_member_tallies": "true",
            "member_sort": "support_desc",
        },
        headers=user_headers,
    )
    assert by_support.status_code == 200
    members = by_support.json()["members"]
    assert len(members) == 2
    support_counts = [
        (m["citation_tallies"] or {"by_stance": {}})["by_stance"].get("support", 0)
        for m in members
    ]
    assert support_counts == sorted(support_counts, reverse=True)


def test_collection_ownership_is_enforced(client, make_user):
    _, owner_headers = make_user(name="owner")
    _, other_headers = make_user(name="other")

    collection_id = _create_collection(client, owner_headers)["collection_id"]

    assert client.get(f"/v1/collections/{collection_id}", headers=other_headers).status_code == 403
    assert (
        client.patch(
            f"/v1/collections/{collection_id}",
            json={"name": "hijack"},
            headers=other_headers,
        ).status_code
        == 403
    )
    assert client.delete(f"/v1/collections/{collection_id}", headers=other_headers).status_code == 403


def test_collection_endpoints_require_auth(client):
    assert client.get("/v1/collections").status_code == 401
    assert client.post("/v1/collections", json={"name": "anon"}).status_code == 401
