"""API tests: the /v1 surface over the vertical slice."""

from __future__ import annotations


def _submit(client, name: str, headers: dict, **extra) -> dict:
    from helpers import load_sample

    body = {"xml": load_sample(name), **extra}
    resp = client.post("/v1/papers", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


def test_submit_and_poll_job(client, user_headers):
    job = _submit(client, "paper_b.xml", user_headers)
    assert job["owner_id"]
    polled = client.get(f"/v1/jobs/{job['job_id']}").json()
    assert polled["status"] == "succeeded"
    assert polled["result"]["availability_state"] == "full_text_extracted"


def test_idempotency_key_dedupes(client, user_headers):
    first = _submit(client, "paper_b.xml", user_headers, idempotency_key="k-1")
    second = _submit(client, "paper_b.xml", user_headers, idempotency_key="k-1")
    assert first["job_id"] == second["job_id"]


def test_list_papers(client, user_headers):
    empty = client.get("/v1/papers")
    assert empty.status_code == 200 and empty.json() == []

    _submit(client, "paper_a.xml", user_headers)
    _submit(client, "paper_b.xml", user_headers)

    listed = client.get("/v1/papers").json()  # reads stay open (no auth header)
    assert len(listed) >= 2
    assert all("availability_state" in p and "work_id" in p for p in listed)


def test_full_read_flow_and_trace(client, user_headers):
    _submit(client, "paper_b.xml", user_headers)
    job_a = _submit(client, "paper_a.xml", user_headers)
    work_id = job_a["result"]["work_id"]

    claims = client.get(f"/v1/papers/{work_id}/claims").json()
    assert claims

    # Every claim response embeds its evidence.
    for claim in claims:
        assert claim["evidence"]["verbatim_text"]

    # At least one claim traces one hop into paper B at the claim level.
    found_claim_resolved = False
    for claim in claims:
        trace = client.get(f"/v1/claims/{claim['claim_id']}/trace").json()
        for hop in trace["hops"]:
            if hop["resolution"] == "claim_resolved":
                found_claim_resolved = True
                assert hop["target_claim"] is not None
                assert hop["evidence"] is not None
    assert found_claim_resolved


def test_relationship_filtering(client, user_headers):
    _submit(client, "paper_b.xml", user_headers)
    job_a = _submit(client, "paper_a.xml", user_headers)
    work_id = job_a["result"]["work_id"]
    claims = client.get(f"/v1/papers/{work_id}/claims").json()

    total_rels = 0
    for claim in claims:
        rels = client.get(f"/v1/claims/{claim['claim_id']}/relationships").json()
        total_rels += len(rels)
    assert total_rels >= 3


def test_malformed_xml_fails_job_not_request(client, user_headers):
    resp = client.post("/v1/papers", json={"xml": "<article>broken"}, headers=user_headers)
    assert resp.status_code == 202
    job = resp.json()
    polled = client.get(f"/v1/jobs/{job['job_id']}").json()
    assert polled["status"] == "failed"
    assert "parse" in (polled["error"] or "").lower()


def test_empty_submission_rejected(client, user_headers):
    resp = client.post("/v1/papers", json={}, headers=user_headers)
    assert resp.status_code == 422


def test_evidence_endpoints(client, user_headers):
    job = _submit(client, "paper_b.xml", user_headers)
    work_id = job["result"]["work_id"]
    claims = client.get(f"/v1/papers/{work_id}/claims").json()
    claim = claims[0]

    occ = client.get(f"/v1/claim-occurrences/{claim['occurrence_id']}")
    assert occ.status_code == 200
    interp = client.get(f"/v1/claim-interpretations/{claim['interpretation_id']}")
    assert interp.status_code == 200
    passage = client.get(f"/v1/passages/{claim['evidence']['passage_id']}")
    assert passage.status_code == 200
    assert passage.json()["verbatim_text"]
