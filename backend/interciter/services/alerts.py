"""Monitoring — saved searches + alerts (scite-parity WP8, F3/F5).

Turns two existing substrates into a notification loop, without mutating any
scientific assertion:

* a **SavedSearch** persists a claim search; re-running it and diffing the current
  hit set against the last-seen set surfaces newly matching claims;
* a **watched Collection** (WP4→WP8 bridge) is re-checked against its baseline
  snapshot to surface new supporting/contradicting citations and new retractions.

Both produce **Alert** rows (in-app only for now — no email/SMTP). Baselines advance
when a check runs, so the same signal is never alerted twice.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..ids import new_id
from ..schemas import (
    AlertRunResult,
    AlertView,
    SavedSearchCreate,
    SavedSearchUpdate,
    SavedSearchView,
    SearchQuery,
)
from . import collections, search
from .projection import NotFound

# Cap on hits considered when diffing a saved search (bounds the work per run).
_MAX_SEARCH_HITS = 5000


def _now():
    return collections._utcnow()


# --- SavedSearch views ------------------------------------------------------------


def _saved_search_view(ss: models.SavedSearch) -> SavedSearchView:
    return SavedSearchView(
        saved_search_id=ss.saved_search_id,
        owner_id=ss.owner_id,
        name=ss.name,
        query=SearchQuery(**(ss.search_query or {})),
        last_checked_at=ss.last_checked_at,
        created_at=ss.created_at,
        updated_at=ss.updated_at,
    )


def _alert_view(alert: models.Alert) -> AlertView:
    return AlertView(
        alert_id=alert.alert_id,
        source_type=alert.alert_source_type,
        source_id=alert.alert_source_id,
        alert_type=alert.alert_type,
        work_id=alert.work_id,
        claim_id=alert.claim_id,
        summary=alert.summary,
        is_read=alert.is_read,
        created_at=alert.created_at,
    )


def _load_owned_search(
    session: Session, saved_search_id: str, *, owner_id: str
) -> models.SavedSearch:
    ss = session.get(models.SavedSearch, saved_search_id)
    # A search owned by someone else is reported as missing (no id leakage).
    if ss is None or ss.owner_id != owner_id:
        raise NotFound(f"saved search {saved_search_id} not found")
    return ss


def _current_hit_ids(session: Session, query: dict) -> list[str]:
    results = search.search_claims(session, **query, limit=_MAX_SEARCH_HITS, offset=0)
    return [hit.claim_id for hit in results.hits]


# --- SavedSearch CRUD -------------------------------------------------------------


def create_saved_search(
    session: Session, payload: SavedSearchCreate, *, owner_id: str
) -> SavedSearchView:
    """Create a saved search, seeding the baseline with current hits (no alerts)."""
    query = payload.query.model_dump()
    now = _now()
    ss = models.SavedSearch(
        saved_search_id=new_id("SavedSearch"),
        owner_id=owner_id,
        name=payload.name.strip(),
        search_query=query,
        # Baseline so the first run only surfaces claims added AFTER creation.
        last_seen_ids=_current_hit_ids(session, query),
        last_checked_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(ss)
    session.commit()
    return _saved_search_view(ss)


def list_saved_searches(session: Session, *, owner_id: str) -> list[SavedSearchView]:
    rows = session.scalars(
        select(models.SavedSearch)
        .where(models.SavedSearch.owner_id == owner_id)
        .order_by(models.SavedSearch.updated_at.desc())
    )
    return [_saved_search_view(ss) for ss in rows]


def get_saved_search(
    session: Session, saved_search_id: str, *, owner_id: str
) -> SavedSearchView:
    return _saved_search_view(_load_owned_search(session, saved_search_id, owner_id=owner_id))


def update_saved_search(
    session: Session,
    saved_search_id: str,
    payload: SavedSearchUpdate,
    *,
    owner_id: str,
) -> SavedSearchView:
    ss = _load_owned_search(session, saved_search_id, owner_id=owner_id)
    provided = payload.model_fields_set
    if "name" in provided and payload.name is not None:
        ss.name = payload.name.strip()
    if "query" in provided and payload.query is not None:
        ss.search_query = payload.query.model_dump()
        # Re-baseline against the new query so the change itself doesn't alert.
        ss.last_seen_ids = _current_hit_ids(session, ss.search_query)
        ss.last_checked_at = _now()
    session.commit()
    return _saved_search_view(ss)


def delete_saved_search(session: Session, saved_search_id: str, *, owner_id: str) -> None:
    ss = _load_owned_search(session, saved_search_id, owner_id=owner_id)
    session.delete(ss)
    session.commit()


# --- Alert generation -------------------------------------------------------------


def _add_alert(
    session: Session,
    *,
    owner_id: str,
    source_type: str,
    source_id: str,
    alert_type: str,
    summary: str,
    work_id: str | None = None,
    claim_id: str | None = None,
) -> models.Alert:
    alert = models.Alert(
        alert_id=new_id("Alert"),
        owner_id=owner_id,
        alert_source_type=source_type,
        alert_source_id=source_id,
        alert_type=alert_type,
        work_id=work_id,
        claim_id=claim_id,
        summary=summary,
        is_read=False,
    )
    session.add(alert)
    return alert


def _run_saved_search(session: Session, ss: models.SavedSearch) -> list[models.Alert]:
    """Diff current hits vs last-seen, emit alerts, advance the baseline (no commit)."""
    results = search.search_claims(
        session, **(ss.search_query or {}), limit=_MAX_SEARCH_HITS, offset=0
    )
    seen = set(ss.last_seen_ids or [])
    created: list[models.Alert] = []
    for hit in results.hits:
        if hit.claim_id in seen:
            continue
        created.append(
            _add_alert(
                session,
                owner_id=ss.owner_id,
                source_type="saved_search",
                source_id=ss.saved_search_id,
                alert_type="new_claim",
                work_id=hit.work_id,
                claim_id=hit.claim_id,
                summary=(
                    f'New match for "{ss.name}": '
                    f"{(hit.paper_title or hit.work_id)} — {hit.normalized_text}"
                ),
            )
        )
    ss.last_seen_ids = [hit.claim_id for hit in results.hits]
    ss.last_checked_at = _now()
    return created


def _run_collection(session: Session, collection: models.Collection) -> list[models.Alert]:
    """Diff current member signals vs the watch baseline, emit alerts, re-baseline."""
    baseline = collection.watch_snapshot or {}
    memberships = session.scalars(
        select(models.CollectionMembership).where(
            models.CollectionMembership.collection_id == collection.collection_id
        )
    )
    created: list[models.Alert] = []
    for member in memberships:
        work = session.get(models.PaperWork, member.work_id)
        if work is None:
            continue
        support, contradict = collections._member_stance_counts(session, member.work_id)
        prior = baseline.get(member.work_id, {})
        new_support = max(0, support - int(prior.get("support", 0)))
        new_contradict = max(0, contradict - int(prior.get("contradict", 0)))
        label = work.title or work.work_id

        if new_support:
            created.append(
                _add_alert(
                    session,
                    owner_id=collection.owner_id,
                    source_type="collection",
                    source_id=collection.collection_id,
                    alert_type="new_support",
                    work_id=work.work_id,
                    summary=(
                        f'"{collection.name}": {label} gained {new_support} '
                        f"new supporting citation(s)"
                    ),
                )
            )
        if new_contradict:
            created.append(
                _add_alert(
                    session,
                    owner_id=collection.owner_id,
                    source_type="collection",
                    source_id=collection.collection_id,
                    alert_type="new_contradict",
                    work_id=work.work_id,
                    summary=(
                        f'"{collection.name}": {label} gained {new_contradict} '
                        f"new contradicting citation(s)"
                    ),
                )
            )
        if work.is_retracted and not prior.get("retracted", False):
            created.append(
                _add_alert(
                    session,
                    owner_id=collection.owner_id,
                    source_type="collection",
                    source_id=collection.collection_id,
                    alert_type="retraction",
                    work_id=work.work_id,
                    summary=f'"{collection.name}": {label} has been retracted',
                )
            )

    # Advance the baseline so consumed signals are not re-alerted.
    collection.watch_snapshot = collections._current_stance_snapshot(
        session, collection.collection_id
    )
    collection.watch_snapshot_at = _now()
    return created


def run_saved_search(
    session: Session, saved_search_id: str, *, owner_id: str
) -> AlertRunResult:
    ss = _load_owned_search(session, saved_search_id, owner_id=owner_id)
    created = _run_saved_search(session, ss)
    session.commit()
    return AlertRunResult(
        created_count=len(created), alerts=[_alert_view(a) for a in created]
    )


def run_all(
    session: Session, *, owner_id: str, settings: Settings | None = None
) -> AlertRunResult:
    """Run every saved search and watched collection the caller owns; commit once."""
    settings = settings or get_settings()
    created: list[models.Alert] = []
    for ss in session.scalars(
        select(models.SavedSearch).where(models.SavedSearch.owner_id == owner_id)
    ):
        created.extend(_run_saved_search(session, ss))
    for collection in session.scalars(
        select(models.Collection).where(
            models.Collection.owner_id == owner_id,
            models.Collection.is_watched.is_(True),
        )
    ):
        created.extend(_run_collection(session, collection))
    session.commit()
    return AlertRunResult(
        created_count=len(created), alerts=[_alert_view(a) for a in created]
    )


# --- Alert reads ------------------------------------------------------------------


def list_alerts(
    session: Session, *, owner_id: str, unread_only: bool = False, limit: int = 100
) -> list[AlertView]:
    stmt = select(models.Alert).where(models.Alert.owner_id == owner_id)
    if unread_only:
        stmt = stmt.where(models.Alert.is_read.is_(False))
    stmt = stmt.order_by(models.Alert.created_at.desc()).limit(limit)
    return [_alert_view(a) for a in session.scalars(stmt)]


def mark_read(session: Session, alert_id: str, *, owner_id: str) -> AlertView:
    alert = session.get(models.Alert, alert_id)
    if alert is None or alert.owner_id != owner_id:
        raise NotFound(f"alert {alert_id} not found")
    alert.is_read = True
    session.commit()
    return _alert_view(alert)


def mark_all_read(session: Session, *, owner_id: str) -> int:
    alerts = list(
        session.scalars(
            select(models.Alert).where(
                models.Alert.owner_id == owner_id,
                models.Alert.is_read.is_(False),
            )
        )
    )
    for alert in alerts:
        alert.is_read = True
    session.commit()
    return len(alerts)
