"""Shared saved-set / cohort base tests.

Covers the single owner-scoped seam that resolves a saved Collection or Map into an
analysis cohort, both at the service layer and through ``GET /v1/cohorts/resolve``.
"""

from __future__ import annotations

import pytest

from interciter.services import cohort
from interciter.services.projection import NotFound


def _submit(client, headers, sample: str) -> str:
    from helpers import load_sample

    resp = client.post("/v1/papers", json={"xml": load_sample(sample)}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()["result"]["work_id"]


def _create_collection(client, headers, work_ids) -> str:
    resp = client.post(
        "/v1/collections", json={"name": "Core set"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["collection_id"]
    add = client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": work_ids},
        headers=headers,
    )
    assert add.status_code == 200, add.text
    return collection_id


def _create_map(client, headers, work_ids) -> str:
    resp = client.post(
        "/v1/maps", json={"name": "Seed map", "work_ids": work_ids}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["map_id"]


# --------------------------------------------------------------------------------
# Endpoint: GET /v1/cohorts/resolve
# --------------------------------------------------------------------------------


def test_resolve_collection_source(client, user_headers):
    b = _submit(client, user_headers, "paper_b.xml")
    a = _submit(client, user_headers, "paper_a.xml")
    collection_id = _create_collection(client, user_headers, [a, b])

    resolved = client.get(
        f"/v1/cohorts/resolve?collection={collection_id}", headers=user_headers
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["source_type"] == "collection"
    assert body["source_id"] == collection_id
    assert body["name"] == "Core set"
    assert body["member_count"] == 2


def test_resolve_map_source(client, user_headers):
    b = _submit(client, user_headers, "paper_b.xml")
    a = _submit(client, user_headers, "paper_a.xml")
    map_id = _create_map(client, user_headers, [a, b])

    resolved = client.get(f"/v1/cohorts/resolve?map={map_id}", headers=user_headers)
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["source_type"] == "map"
    assert body["source_id"] == map_id
    assert body["member_count"] == 2


def test_resolve_requires_auth_for_saved_source(client, user_headers):
    collection_id = _create_collection(
        client, user_headers, [_submit(client, user_headers, "paper_b.xml")]
    )
    # Anonymous callers cannot resolve an owner-private saved set.
    assert client.get(f"/v1/cohorts/resolve?collection={collection_id}").status_code == 401


def test_resolve_is_owner_scoped(client, user_headers, make_user):
    collection_id = _create_collection(
        client, user_headers, [_submit(client, user_headers, "paper_b.xml")]
    )
    other_headers = make_user(name="intruder")[1]
    # Another user's collection is reported as missing, never leaked.
    assert (
        client.get(
            f"/v1/cohorts/resolve?collection={collection_id}", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/v1/cohorts/resolve?map=map_does_not_exist", headers=user_headers
        ).status_code
        == 404
    )


def test_resolve_rejects_ambiguous_and_empty(client, user_headers):
    collection_id = _create_collection(
        client, user_headers, [_submit(client, user_headers, "paper_b.xml")]
    )
    map_id = _create_map(client, user_headers, [])
    both = client.get(
        f"/v1/cohorts/resolve?collection={collection_id}&map={map_id}",
        headers=user_headers,
    )
    assert both.status_code == 400
    assert client.get("/v1/cohorts/resolve", headers=user_headers).status_code == 400


# --------------------------------------------------------------------------------
# Service: cohort.resolve_cohort
# --------------------------------------------------------------------------------


class _Principal:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


def test_resolve_cohort_passthrough_and_defaults(session):
    # No saved source: explicit work_ids pass through; nothing => whole corpus (None).
    assert cohort.resolve_cohort(session, work_ids=["w1", "w2"]) == ["w1", "w2"]
    assert cohort.resolve_cohort(session) is None


def test_resolve_cohort_requires_principal(session):
    with pytest.raises(cohort.CohortAuthRequired):
        cohort.resolve_cohort(session, collection="coll_x")


def test_resolve_cohort_rejects_ambiguous(session):
    with pytest.raises(cohort.AmbiguousCohort):
        cohort.resolve_cohort(
            session,
            collection="coll_x",
            map_id="map_x",
            principal=_Principal("user_1"),
        )


def test_resolve_cohort_unknown_source_not_found(session):
    with pytest.raises(NotFound):
        cohort.resolve_cohort(
            session, map_id="map_missing", principal=_Principal("user_1")
        )
