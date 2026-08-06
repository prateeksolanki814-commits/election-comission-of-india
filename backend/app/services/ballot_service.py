"""
Anonymous Ballot Service.

This service NEVER receives a voter identifier — only an opaque one-time
token. Its DB session is bound to `role_ballot_svc`, a Postgres role with
no grant on `eligibility.synthetic_voters` (see database/schema.sql), so
even a coding mistake here cannot leak voter identity by querying it.

Two independent mechanisms prevent a double vote:
  1. Token single-use: `voting_credentials.status` flips 'unused' -> 'used'
     in one atomic UPDATE ... WHERE status = 'unused'. If two requests race
     for the same token, only one UPDATE affects a row; the other gets
     rowcount == 0 and is rejected.
  2. Idempotency key: `anonymous_ballots` has a UNIQUE(election_id,
     idempotency_key) constraint, so if a client retries the same request
     (e.g. due to a network timeout) after the ballot was already recorded,
     the duplicate INSERT fails safely and the original reference number
     can be returned instead of creating a second ballot.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import check_rate_limit
from app.core.security import generate_reference_number, hash_for_logging, hash_token
from app.models.ballots import AnonymousBallot
from app.services.audit_service import append_audit_event


class BallotError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def cast_ballot(
    session: AsyncSession,
    raw_voting_token: str,
    election_id: str,
    constituency_id: str,
    candidate_id: str,
    idempotency_key: str,
    client_ip: str,
) -> str:
    """Returns a reference_number. Raises BallotError on any failure. Never
    logs raw_voting_token or candidate_id."""
    ip_hash = hash_for_logging(client_ip)
    await check_rate_limit(f"ballot_ip:{ip_hash}", 10, 60)

    token_hash = hash_token(raw_voting_token)

    # --- Idempotency check first: if this exact request already succeeded,
    # return the same reference number rather than erroring, so client
    # retries after a network blip are safe. ---
    existing = await session.execute(
        select(AnonymousBallot.reference_number).where(
            AnonymousBallot.election_id == election_id,
            AnonymousBallot.idempotency_key == idempotency_key,
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row:
        return existing_row

    # --- Atomically consume the token. This single UPDATE is the crux of
    # the duplicate-vote defense; only one concurrent request can win it. ---
    result = await session.execute(
        update_credential_status_query(token_hash)
    )
    if result.rowcount == 0:
        await append_audit_event(
            session,
            event_type="token_reuse_or_invalid_blocked",
            actor_role="system",
            payload={"election_id": election_id},
            election_id=election_id,
        )
        await session.commit()
        raise BallotError("TOKEN_INVALID_OR_USED", "Voting token is invalid, expired, or already used.", 409)

    reference_number = generate_reference_number()
    ballot = AnonymousBallot(
        election_id=election_id,
        constituency_id=constituency_id,
        candidate_id=candidate_id,
        idempotency_key=idempotency_key,
        reference_number=reference_number,
    )
    session.add(ballot)

    try:
        await append_audit_event(
            session,
            event_type="ballot_cast",
            actor_role="system",
            payload={"election_id": election_id, "constituency_id": constituency_id},
            election_id=election_id,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Race on idempotency key: someone else's retry beat us. Return
        # their reference number instead of erroring the voter.
        existing = await session.execute(
            select(AnonymousBallot.reference_number).where(
                AnonymousBallot.election_id == election_id,
                AnonymousBallot.idempotency_key == idempotency_key,
            )
        )
        existing_row = existing.scalar_one_or_none()
        if existing_row:
            return existing_row
        raise BallotError("BALLOT_SUBMISSION_FAILED", "Could not record ballot. Please retry.", 500)

    return reference_number


def update_credential_status_query(token_hash: str):
    """Separated out so it's easy to unit-test the exact atomic condition:
    only rows with status='unused' AND not expired can transition to
    'used'. Uses the eligibility.voting_credentials table via the ballot
    service's limited grant (UPDATE only on that one table — see
    database/schema.sql grants section)."""
    from sqlalchemy import text

    return text(
        """
        UPDATE eligibility.voting_credentials
        SET status = 'used', used_at = now()
        WHERE token_hash = :token_hash
          AND status = 'unused'
          AND expires_at > now()
        """
    ).bindparams(token_hash=token_hash)
