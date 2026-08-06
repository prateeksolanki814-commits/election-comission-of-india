"""
Tamper-evident audit log.

Every event stores sha256(prev_event_hash + canonical_json(payload)) as its
own hash, forming a hash chain (same idea as a simple blockchain, used here
strictly as an audit-log integrity check — NOT as a claim that "blockchain
secures the election"; see THREAT_MODEL.md and PRIVACY.md for why that
claim would be misleading).

Rules enforced by convention here AND by a DB trigger (see schema.sql,
`audit.reject_modification`) that blocks UPDATE/DELETE on the table:
  - payload_summary must never contain voter identity or candidate choice.
  - Only aggregate or structural facts go in the audit log
    (e.g. "ballot_cast" with election_id, NOT which candidate).
"""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GENESIS_HASH = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(prev_hash: str, event_type: str, payload: dict, created_at: str) -> str:
    material = f"{prev_hash}|{event_type}|{_canonical(payload)}|{created_at}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def _get_last_hash(session: AsyncSession) -> str:
    result = await session.execute(
        text("SELECT event_hash FROM audit.audit_events ORDER BY event_id DESC LIMIT 1")
    )
    row = result.first()
    return row[0] if row else GENESIS_HASH


_FORBIDDEN_KEYS = {"voter_id", "voter_code", "candidate_id", "candidate_choice", "otp", "password", "token"}


def _assert_payload_safe(payload: dict) -> None:
    lowered = {k.lower() for k in payload.keys()}
    leaked = lowered & _FORBIDDEN_KEYS
    if leaked:
        raise ValueError(
            f"Refusing to write audit event: payload contains forbidden keys {leaked}. "
            "Audit events must never carry voter identity or vote content."
        )


async def append_audit_event(
    session: AsyncSession,
    event_type: str,
    actor_role: str,
    payload: dict,
    election_id: str | None = None,
) -> int:
    _assert_payload_safe(payload)
    prev_hash = await _get_last_hash(session)
    created_at = datetime.now(timezone.utc).isoformat()
    event_hash = compute_event_hash(prev_hash, event_type, payload, created_at)

    result = await session.execute(
        text(
            """
            INSERT INTO audit.audit_events
                (event_type, actor_role, election_id, payload_summary, prev_hash, event_hash, created_at)
            VALUES
                (:event_type, :actor_role, :election_id, CAST(:payload AS JSONB), :prev_hash, :event_hash, :created_at)
            RETURNING event_id
            """
        ),
        {
            "event_type": event_type,
            "actor_role": actor_role,
            "election_id": election_id,
            "payload": _canonical(payload),
            "prev_hash": prev_hash,
            "event_hash": event_hash,
            "created_at": created_at,
        },
    )
    await session.commit()
    return result.scalar_one()


async def verify_audit_chain(session: AsyncSession) -> dict:
    """Walks the full audit log and re-derives each hash to detect any
    tampering, deletion, or reordering. Returns a report, not just a bool,
    so an auditor can see exactly where a break occurred."""
    result = await session.execute(
        text(
            "SELECT event_id, event_type, payload_summary, prev_hash, event_hash, created_at "
            "FROM audit.audit_events ORDER BY event_id ASC"
        )
    )
    rows = result.fetchall()

    expected_prev = GENESIS_HASH
    for row in rows:
        event_id, event_type, payload_summary, prev_hash, event_hash, created_at = row
        if prev_hash != expected_prev:
            return {
                "valid": False,
                "broken_at_event_id": event_id,
                "reason": "prev_hash does not match previous event's hash",
            }
        recomputed = compute_event_hash(prev_hash, event_type, payload_summary, created_at.isoformat())
        if recomputed != event_hash:
            return {
                "valid": False,
                "broken_at_event_id": event_id,
                "reason": "event_hash does not match recomputed hash — payload may be altered",
            }
        expected_prev = event_hash

    return {"valid": True, "events_verified": len(rows)}
