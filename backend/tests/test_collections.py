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

    # Another user's collection must be indistinguishable from a missing one so
    # collection ids don't leak across accounts.
    assert client.get(f"/v1/collections/{collection_id}", headers=other_headers).status_code == 404
    assert (
        client.patch(
            f"/v1/collections/{collection_id}",
            json={"name": "hijack"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/collections/{collection_id}", headers=other_headers).status_code == 404
    # And the owner still sees it untouched.
    owner_view = client.get(f"/v1/collections/{collection_id}", headers=owner_headers)
    assert owner_view.status_code == 200
    assert owner_view.json()["name"] == "T2D Core"


def test_collection_endpoints_require_auth(client):
    assert client.get("/v1/collections").status_code == 401
    assert client.post("/v1/collections", json={"name": "anon"}).status_code == 401


def test_collection_description_can_be_cleared(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    cleared = client.patch(
        f"/v1/collections/{collection_id}",
        json={"description": None},
        headers=user_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["description"] is None
    # Omitting the field leaves the (cleared) value untouched.
    renamed = client.patch(
        f"/v1/collections/{collection_id}",
        json={"name": "Renamed"},
        headers=user_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["description"] is None


def test_identifier_parsing_normalizes_and_skips_ambiguous_tokens(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    wiley_doi = "10.1002/(sici)1097-4636(199905)45:2<133::aid-jbm9>3.0.co;2-#"
    add = client.post(
        f"/v1/collections/{collection_id}/members",
        json={
            # Legacy DOI with an embedded semicolon must survive tokenizing,
            # doi.org URLs must be unwrapped, and a bare year must not become
            # a PMID stub.
            "csv_text": f"{wiley_doi.upper()}\nhttps://doi.org/10.3000/from-url, 2021\npmid:87654321",
        },
        headers=user_headers,
    )
    assert add.status_code == 200, add.text
    body = add.json()
    assert body["added_count"] == 3
    assert body["skipped_identifiers"] == ["2021"]

    detail = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    dois = {m["doi"] for m in detail.json()["members"] if m["doi"]}
    pmids = {m["pmid"] for m in detail.json()["members"] if m["pmid"]}
    assert wiley_doi in dois  # stored lowercase, semicolon suffix intact
    assert "10.3000/from-url" in dois
    assert pmids == {"87654321"}


def test_duplicate_case_variant_doi_does_not_create_second_stub(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    first = client.post(
        f"/v1/collections/{collection_id}/members",
        json={"dois": ["10.4000/CasedDOI"]},
        headers=user_headers,
    )
    assert first.status_code == 200
    assert len(first.json()["created_stub_work_ids"]) == 1

    second = client.post(
        f"/v1/collections/{collection_id}/members",
        json={"dois": ["10.4000/caseddoi"]},
        headers=user_headers,
    )
    assert second.status_code == 200
    assert second.json()["created_stub_work_ids"] == []
    assert second.json()["added_count"] == 0


def test_add_members_batch_limit_is_enforced(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    too_many = client.post(
        f"/v1/collections/{collection_id}/members",
        json={"csv_text": "\n".join(f"10.9000/bulk-{i}" for i in range(501))},
        headers=user_headers,
    )
    assert too_many.status_code == 400
    assert "limit" in too_many.json()["detail"]


def test_get_collection_rejects_unknown_member_sort(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]
    resp = client.get(
        f"/v1/collections/{collection_id}",
        params={"member_sort": "bogus"},
        headers=user_headers,
    )
    assert resp.status_code == 422


def test_watch_toggle_captures_snapshot_and_state(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    created = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    assert created.json()["is_watched"] is False
    assert created.json()["watch_snapshot_at"] is None

    watched = client.post(
        f"/v1/collections/{collection_id}/watch",
        json={"watch": True},
        headers=user_headers,
    )
    assert watched.status_code == 200
    assert watched.json()["is_watched"] is True
    assert watched.json()["watch_snapshot_at"] is not None

    unwatched = client.post(
        f"/v1/collections/{collection_id}/watch",
        json={"watch": False},
        headers=user_headers,
    )
    assert unwatched.status_code == 200
    assert unwatched.json()["is_watched"] is False


def test_new_citation_delta_reports_signals_after_snapshot(client, user_headers):
    # paper_a cites paper_b, producing a supporting citation targeting paper_b.
    paper_b = _submit(client, user_headers, "paper_b.xml")
    work_b = paper_b["result"]["work_id"]

    collection_id = _create_collection(client, user_headers)["collection_id"]
    client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": [work_b]},
        headers=user_headers,
    )

    # Baseline BEFORE the citing paper exists: no support recorded yet.
    watched = client.post(
        f"/v1/collections/{collection_id}/watch",
        json={"watch": True},
        headers=user_headers,
    )
    assert watched.status_code == 200

    # A new citing paper arrives after the snapshot.
    _submit(client, user_headers, "paper_a.xml")

    delta = client.get(
        f"/v1/collections/{collection_id}/new-citations", headers=user_headers
    )
    assert delta.status_code == 200
    body = delta.json()
    assert body["has_snapshot"] is True
    assert body["new_support_total"] >= 1
    assert any(m["work_id"] == work_b and m["new_support"] >= 1 for m in body["members"])

    # Re-baselining clears the delta (the signals are now "seen").
    client.post(
        f"/v1/collections/{collection_id}/watch",
        json={"watch": True},
        headers=user_headers,
    )
    reseen = client.get(
        f"/v1/collections/{collection_id}/new-citations", headers=user_headers
    )
    assert reseen.json()["new_support_total"] == 0
    assert reseen.json()["members"] == []


def test_new_citation_delta_without_snapshot(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]
    delta = client.get(
        f"/v1/collections/{collection_id}/new-citations", headers=user_headers
    )
    assert delta.status_code == 200
    assert delta.json()["has_snapshot"] is False
    assert delta.json()["members"] == []


def test_bulk_remove_members(client, user_headers):
    paper_a = _submit(client, user_headers, "paper_a.xml")
    paper_b = _submit(client, user_headers, "paper_b.xml")
    work_a = paper_a["result"]["work_id"]
    work_b = paper_b["result"]["work_id"]

    collection_id = _create_collection(client, user_headers)["collection_id"]
    client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": [work_a, work_b]},
        headers=user_headers,
    )

    removed = client.post(
        f"/v1/collections/{collection_id}/members/bulk-delete",
        json={"work_ids": [work_a, work_b, "work_does_not_exist"]},
        headers=user_headers,
    )
    assert removed.status_code == 200
    body = removed.json()
    assert body["removed_count"] == 2
    assert set(body["removed_work_ids"]) == {work_a, work_b}

    detail = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    assert detail.json()["member_count"] == 0


def test_bulk_remove_requires_non_empty_list(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]
    resp = client.post(
        f"/v1/collections/{collection_id}/members/bulk-delete",
        json={"work_ids": []},
        headers=user_headers,
    )
    assert resp.status_code == 422


def test_member_view_surfaces_integrity_flags(client, user_headers, session):
    from interciter import models

    paper = _submit(client, user_headers, "paper_b.xml")
    work_id = paper["result"]["work_id"]

    work = session.get(models.PaperWork, work_id)
    work.is_retracted = True
    work.integrity_notice = "expression_of_concern"
    session.commit()

    collection_id = _create_collection(client, user_headers)["collection_id"]
    client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": [work_id]},
        headers=user_headers,
    )

    detail = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    member = detail.json()["members"][0]
    assert member["is_retracted"] is True
    assert member["integrity_notice"] == "expression_of_concern"


def test_watch_and_delta_enforce_ownership(client, make_user):
    _, owner_headers = make_user(name="owner2")
    _, other_headers = make_user(name="other2")
    collection_id = _create_collection(client, owner_headers)["collection_id"]

    assert (
        client.post(
            f"/v1/collections/{collection_id}/watch",
            json={"watch": True},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/collections/{collection_id}/new-citations", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/collections/{collection_id}/members/bulk-delete",
            json={"work_ids": ["work_x"]},
            headers=other_headers,
        ).status_code
        == 404
    )


def test_watch_and_delta_require_auth(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]
    assert client.post(
        f"/v1/collections/{collection_id}/watch", json={"watch": True}
    ).status_code == 401
    assert client.get(
        f"/v1/collections/{collection_id}/new-citations"
    ).status_code == 401
    assert client.post(
        f"/v1/collections/{collection_id}/members/bulk-delete",
        json={"work_ids": ["work_x"]},
    ).status_code == 401


# ---------------------------------------------------------------------------------
# WP9 — reference-manager import (RIS / BibTeX)
# ---------------------------------------------------------------------------------

_RIS_LIBRARY = """TY  - JOUR
AU  - Smith, J.
TI  - Metformin and glycemic control
DO  - 10.1000/ris-demo-doi
DB  - PubMed
AN  - 20000001
ER  -

TY  - JOUR
TI  - A record with no identifiers
AU  - Doe, A.
ER  -
"""

_BIBTEX_LIBRARY = """@article{smith2020,
  title = {Fasting glucose review},
  author = {Smith, John},
  doi = {10.1000/bibtex-demo-doi},
  pmid = {20000002},
}

@article{jones2021,
  title = {No identifiers here},
  author = {Jones, Amy},
}
"""


def test_reference_manager_parsers_extract_identifiers():
    from interciter.ingestion import reference_managers as rm

    assert rm.detect_format(_RIS_LIBRARY) == "ris"
    assert rm.detect_format(_BIBTEX_LIBRARY) == "bibtex"
    assert rm.detect_format("10.1/x 12345678") == "csv"
    assert rm.detect_format("anything", filename="lib.bib") == "bibtex"

    ris = rm.parse_references(_RIS_LIBRARY, "ris")
    assert ris.dois == ["10.1000/ris-demo-doi"]
    assert ris.pmids == ["20000001"]  # AN accession + PubMed hint
    assert ris.entry_count == 2
    assert ris.matched_count == 1

    bib = rm.parse_references(_BIBTEX_LIBRARY, "bibtex")
    assert bib.dois == ["10.1000/bibtex-demo-doi"]
    assert bib.pmids == ["20000002"]
    assert bib.entry_count == 2
    assert bib.matched_count == 1


def test_import_ris_and_bibtex_seed_collection(client, user_headers):
    collection_id = _create_collection(client, user_headers)["collection_id"]

    ris = client.post(
        f"/v1/collections/{collection_id}/import",
        json={"text": _RIS_LIBRARY, "format": "ris"},
        headers=user_headers,
    )
    assert ris.status_code == 200, ris.text
    body = ris.json()
    assert body["format"] == "ris"
    assert body["entry_count"] == 2
    assert body["matched_count"] == 1
    assert body["added_count"] == 2  # one DOI stub + one PMID stub
    assert len(body["created_stub_work_ids"]) == 2

    # Auto-detected format (no explicit `format`) works too.
    bib = client.post(
        f"/v1/collections/{collection_id}/import",
        json={"text": _BIBTEX_LIBRARY},
        headers=user_headers,
    )
    assert bib.status_code == 200, bib.text
    assert bib.json()["format"] == "bibtex"
    assert bib.json()["added_count"] == 2

    detail = client.get(f"/v1/collections/{collection_id}", headers=user_headers)
    dois = {m["doi"] for m in detail.json()["members"] if m["doi"]}
    assert {"10.1000/ris-demo-doi", "10.1000/bibtex-demo-doi"} <= dois


def test_import_is_owner_scoped_and_requires_auth(client, user_headers, make_user):
    collection_id = _create_collection(client, user_headers)["collection_id"]
    other_headers = make_user(name="intruder")[1]

    assert (
        client.post(
            f"/v1/collections/{collection_id}/import",
            json={"text": _RIS_LIBRARY, "format": "ris"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/collections/{collection_id}/import",
            json={"text": _RIS_LIBRARY},
        ).status_code
        == 401
    )


def test_collection_graph_over_members(client, user_headers, make_user):
    from interciter.enums import Role

    collection_id = _create_collection(client, user_headers)["collection_id"]
    b = _submit(client, user_headers, "paper_b.xml")["result"]["work_id"]
    a = _submit(client, user_headers, "paper_a.xml")["result"]["work_id"]
    client.post(
        f"/v1/collections/{collection_id}/members",
        json={"work_ids": [a, b]},
        headers=user_headers,
    )

    # The collection renders as a citation graph of its members, with the A→B edge.
    resp = client.get(
        f"/v1/collections/{collection_id}/graph", headers=user_headers
    )
    assert resp.status_code == 200
    view = resp.json()
    paper_ids = {n["id"] for n in view["nodes"] if n["type"] == "paper"}
    assert paper_ids == {a, b}
    assert any(
        e["source"] == a and e["target"] == b
        for e in view["edges"]
        if e["type"] == "cites"
    )

    # Owner-scoped: another user 404s (id doesn't leak); anonymous 401s.
    _, other = make_user(Role.user, "graphother")
    assert (
        client.get(
            f"/v1/collections/{collection_id}/graph", headers=other
        ).status_code
        == 404
    )
    assert client.get(f"/v1/collections/{collection_id}/graph").status_code == 401
