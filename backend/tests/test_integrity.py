"""Integrity enrichment tests (scite-parity WP5).

Unit tests run offline with a fake Crossref client. The live test hits the real
Crossref API and is gated behind ``INTERCITER_NET_TESTS=1``.
"""

from __future__ import annotations

import os

import pytest

from interciter import models
from interciter.ids import new_id
from interciter.ingestion import crossref
from interciter.services import integrity

_NET = os.environ.get("INTERCITER_NET_TESTS") == "1"
_netonly = pytest.mark.skipif(
    not _NET, reason="network test; set INTERCITER_NET_TESTS=1"
)


class _FakeClient:
    """Stands in for the crossref module; records the DOIs it was asked about."""

    def __init__(self, message: dict | None):
        self.message = message
        self.calls: list[str] = []

    def get_work(self, doi, *, settings=None, use_cache=True):
        self.calls.append(doi)
        return self.message


def _make_work(session, *, doi: str | None = None, title: str = "A trial") -> models.PaperWork:
    work = models.PaperWork(
        work_id=new_id("PaperWork"),
        title=title,
        doi=doi,
        availability_state=models.enums.AvailabilityState.metadata_stub,
    )
    session.add(work)
    session.commit()
    return work


def test_integrity_from_message_flags_retraction():
    message = {"update-to": [{"type": "retraction", "label": "Retraction"}]}
    is_retracted, notice = integrity.integrity_from_message(message)
    assert is_retracted is True
    assert notice == "Retraction"


def test_integrity_from_message_flags_notice_without_retraction():
    message = {
        "update-to": [
            {"type": "expression_of_concern", "label": "Expression of concern"}
        ]
    }
    is_retracted, notice = integrity.integrity_from_message(message)
    assert is_retracted is False
    assert notice == "Expression of concern"


def test_integrity_from_message_title_fallback():
    message = {"title": ["RETRACTED: A flawed study"]}
    is_retracted, notice = integrity.integrity_from_message(message)
    assert is_retracted is True
    assert notice == "Retracted"


def test_integrity_from_message_clean():
    is_retracted, notice = integrity.integrity_from_message({"title": ["A fine study"]})
    assert is_retracted is False
    assert notice is None


def test_check_work_sets_flags_additively(session):
    work = _make_work(session, doi="10.1000/retracted")
    client = _FakeClient({"update-to": [{"type": "retraction", "label": "Retraction"}]})

    result = integrity.check_work(session, work, client=client)
    session.commit()

    assert client.calls == ["10.1000/retracted"]
    assert result.checked is True
    assert result.is_retracted is True
    assert result.integrity_notice == "Retraction"
    assert result.changed is True
    assert work.is_retracted is True
    assert work.integrity_notice == "Retraction"


def test_check_work_reports_no_change_on_second_pass(session):
    work = _make_work(session, doi="10.1000/retracted")
    client = _FakeClient({"update-to": [{"type": "retraction"}]})

    integrity.check_work(session, work, client=client)
    session.commit()
    second = integrity.check_work(session, work, client=client)
    assert second.changed is False


def test_check_work_marks_clean_after_check(session):
    work = _make_work(session, doi="10.1000/clean")
    client = _FakeClient({"title": ["A fine study"]})

    result = integrity.check_work(session, work, client=client)
    session.commit()

    assert result.checked is True
    # A definite False (checked, clean) is distinguishable from an unchecked None.
    assert work.is_retracted is False
    assert work.integrity_notice is None


def test_check_work_skips_without_doi(session):
    work = _make_work(session, doi=None)
    client = _FakeClient({"update-to": [{"type": "retraction"}]})

    result = integrity.check_work(session, work, client=client)

    assert result.checked is False
    assert result.skipped_reason == "no DOI to resolve"
    assert client.calls == []
    assert work.is_retracted is None


def test_check_work_handles_missing_crossref_record(session):
    work = _make_work(session, doi="10.1000/unknown")
    client = _FakeClient(None)

    result = integrity.check_work(session, work, client=client)

    assert result.checked is True
    assert result.skipped_reason == "no Crossref record"
    # An unknown DOI must not overwrite/clear any existing flag.
    assert work.is_retracted is None


def test_check_all_filters_doi_and_only_unchecked(session):
    retracted = _make_work(session, doi="10.1000/a", title="A")
    _make_work(session, doi=None, title="No DOI")  # skipped: no DOI
    client = _FakeClient({"update-to": [{"type": "retraction"}]})

    first = integrity.check_all(session, client=client)
    # Only the DOI-bearing work is considered.
    assert {r.work_id for r in first} == {retracted.work_id}

    # Second pass with only_unchecked skips the already-flagged work.
    second = integrity.check_all(session, only_unchecked=True, client=client)
    assert second == []


def test_normalize_doi_unwraps_prefixes():
    assert crossref.normalize_doi("https://doi.org/10.1000/Abc") == "10.1000/abc"
    assert crossref.normalize_doi("doi:10.1000/XYZ") == "10.1000/xyz"


@_netonly
def test_crossref_live_flags_known_retraction():
    # Wakefield et al. 1998 (Lancet), retracted in 2010 — a stable retraction record.
    message = crossref.get_work("10.1016/S0140-6736(97)11096-0", use_cache=False)
    assert message is not None
    is_retracted, _ = integrity.integrity_from_message(message)
    assert is_retracted is True
