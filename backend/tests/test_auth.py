"""Auth tests: minimal roles + first-class ownership enforcement."""

from __future__ import annotations

from helpers import load_sample


def _seed_paper(client, headers) -> str:
    resp = client.post("/v1/papers", json={"xml": load_sample("paper_b.xml")}, headers=headers)
    assert resp.status_code == 202
    return resp.json()["result"]["work_id"]


def _first_claim(client, work_id) -> dict:
    claims = client.get(f"/v1/papers/{work_id}/claims").json()
    assert claims
    return claims[0]


# --- authentication ---------------------------------------------------------


def test_submit_requires_auth(client):
    resp = client.post("/v1/papers", json={"xml": load_sample("paper_b.xml")})
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.post(
        "/v1/papers",
        json={"xml": load_sample("paper_b.xml")},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_malformed_auth_header_rejected(client):
    resp = client.post(
        "/v1/papers",
        json={"xml": load_sample("paper_b.xml")},
        headers={"Authorization": "Token abc"},
    )
    assert resp.status_code == 401


def test_whoami_reflects_role(client, reviewer_headers):
    me = client.get("/v1/users/me", headers=reviewer_headers).json()
    assert me["role"] == "reviewer"


def test_reads_stay_open(client, user_headers):
    work_id = _seed_paper(client, user_headers)
    # No auth header on the read.
    assert client.get(f"/v1/papers/{work_id}/claims").status_code == 200


# --- role gating ------------------------------------------------------------


def test_only_admin_creates_users(client, user_headers, admin_headers):
    denied = client.post(
        "/v1/users", json={"display_name": "x", "role": "user"}, headers=user_headers
    )
    assert denied.status_code == 403

    created = client.post(
        "/v1/users",
        json={"display_name": "newbie", "role": "reviewer"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["api_token"]  # token returned exactly once
    assert body["role"] == "reviewer"


def test_review_decision_requires_reviewer(client, user_headers, reviewer_headers):
    work_id = _seed_paper(client, user_headers)
    claim = _first_claim(client, work_id)
    payload = {
        "subject_type": "claim_interpretation",
        "subject_id": claim["interpretation_id"],
        "decision_dimension": "extraction_fidelity",
        "label": "accepted",
    }
    assert client.post("/v1/review-decisions", json=payload, headers=user_headers).status_code == 403
    assert client.post("/v1/review-decisions", json=payload, headers=reviewer_headers).status_code == 201


# --- ownership --------------------------------------------------------------


def test_owner_can_revise_but_others_cannot(client, make_user):
    _, author = make_user()
    _, other = make_user(name="other")

    work_id = _seed_paper(client, author)
    passage_id = _first_claim(client, work_id)["evidence"]["passage_id"]

    # Author creates a human claim they own.
    created = client.post(
        "/v1/claims",
        json={"normalized_text": "Author claim about glucose.", "passage_id": passage_id},
        headers=author,
    )
    assert created.status_code == 201
    interp_id = created.json()["interpretation_id"]

    # A different non-reviewer user cannot revise it.
    denied = client.post(
        f"/v1/claim-interpretations/{interp_id}/revisions",
        json={"normalized_text": "Hijacked text."},
        headers=other,
    )
    assert denied.status_code == 403

    # The author can.
    ok = client.post(
        f"/v1/claim-interpretations/{interp_id}/revisions",
        json={"normalized_text": "Refined author claim about glucose."},
        headers=author,
    )
    assert ok.status_code == 201
    assert ok.json()["parent_interpretation_id"] == interp_id


def test_reviewer_can_revise_model_authored_claim(client, user_headers, reviewer_headers):
    work_id = _seed_paper(client, user_headers)
    claim = _first_claim(client, work_id)  # model-authored, author_id is null

    # A regular user cannot revise someone else's / a model's interpretation.
    denied = client.post(
        f"/v1/claim-interpretations/{claim['interpretation_id']}/revisions",
        json={"normalized_text": "User rewrite."},
        headers=user_headers,
    )
    assert denied.status_code == 403

    # A reviewer can.
    ok = client.post(
        f"/v1/claim-interpretations/{claim['interpretation_id']}/revisions",
        json={"normalized_text": "Reviewer-corrected claim."},
        headers=reviewer_headers,
    )
    assert ok.status_code == 201
