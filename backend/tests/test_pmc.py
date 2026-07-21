"""PMC Open Access fetcher tests.

Unit tests run offline. Live fetch tests hit NCBI and are gated behind
``INTERCITER_NET_TESTS=1`` so the default suite stays hermetic.
"""

from __future__ import annotations

import os

import pytest

from interciter.ingestion.pmc import PMCFetchError, fetch_jats, normalize_pmcid

_NET = os.environ.get("INTERCITER_NET_TESTS") == "1"
_netonly = pytest.mark.skipif(not _NET, reason="network test; set INTERCITER_NET_TESTS=1")


def test_normalize_pmcid_variants():
    assert normalize_pmcid("PMC7839591") == "7839591"
    assert normalize_pmcid("pmc7839591") == "7839591"
    assert normalize_pmcid(" 7839591 ") == "7839591"


def test_normalize_pmcid_rejects_bad():
    with pytest.raises(PMCFetchError):
        normalize_pmcid("not-an-id")


@_netonly
def test_fetch_real_oa_paper_returns_jats():
    xml = fetch_jats("PMC7839591")
    assert "<article" in xml
    assert "10.1111/dom.14232" in xml
