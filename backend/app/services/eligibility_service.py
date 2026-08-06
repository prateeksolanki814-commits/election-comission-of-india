"""
Eligibility service: verifies a synthetic voter is who they claim to be and
is allowed to vote, then issues a one-time voting credential.

Hard rule enforced in this file: once `issue_voting_credential` returns,
this service has no further role. It never receives the candidate choice,
never sees the ballot, and the credential it hands out cannot be traced
back to the voter by anyone downstream (see AnonymousBallot model).
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import check_rate_limit
from app.core.security import (
    generate_demo_otp,
    generate_voting_token,
    hash_for_logging,
    verify_secret,
    voting_token_expiry,
)
from app.models.eligibility import AuthAttempt, SyntheticVoter, VotingCredential
from app.services.audit_service import append_audit_event

# In-memory demo OTP store keyed by hashed voter code -> (otp_hash, expiry).
# A real system would use a proper short-lived store (Redis) with strict
# TTL; kept simple here since OTP is simulated for the research prototype.
_DEMO_OTP_STORE: dict[str, tuple[str, datetime]] = {}


class EligibilityError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def start_login(
    session: AsyncSession,
    synthetic_voter_code: str,
    client_ip: str,
) -> str:
    """Step 1: voter submits their synthetic voter code. Returns a demo OTP
    (in a real system this would be sent via SMS/app, never returned in the
    API response)."""
    voter_code_hash = hash_for_logging(synthetic_voter_code)
    ip_hash = hash_for_logging(client_ip)

    await check_rate_limit(f"login:{voter_code_hash}", 5, 900)
    await check_rate_limit(f"login_ip:{ip_hash}", 20, 900)

    result = await session.execute(
        select(SyntheticVoter).where(SyntheticVoter.synthetic_voter_code == synthetic_voter_code)
    )
    voter = result.scalar_one_or_none()

    if voter is None or not voter.is_eligible:
        await _record_attempt(session, voter_code_hash, ip_hash, success=False, reason="not_eligible")
        raise EligibilityError("NOT_ELIGIBLE", "Voter is not eligible or does not exist.")

    if voter.has_voted_flag:
        await _record_attempt(session, voter_code_hash, ip_hash, success=False, reason="already_voted")
        raise EligibilityError("ALREADY_VOTED", "This synthetic voter has already voted.")

    otp = generate_demo_otp()
    from app.core.security import hash_secret

    _DEMO_OTP_STORE[voter_code_hash] = (
        hash_secret(otp),
        datetime.now(timezone.utc).replace(microsecond=0),
    )

    await _record_attempt(session, voter_code_hash, ip_hash, success=True, reason="otp_issued")
    # DEMO ONLY: return OTP directly so the prototype is testable end-to-end
    # without an SMS gateway. Real systems must never do this.
    return otp


async def verify_otp_and_issue_token(
    session: AsyncSession,
    synthetic_voter_code: str,
    otp: str,
    election_id: str,
    client_ip: str,
) -> tuple[str, datetime]:
    """Step 2: verify OTP, mark voter as having voted (boolean only), and
    issue a one-time voting credential. Returns (raw_token, expires_at).
    The raw token is returned to the caller exactly once and is never
    logged or stored — only its hash is persisted."""
    voter_code_hash = hash_for_logging(synthetic_voter_code)
    ip_hash = hash_for_logging(client_ip)

    await check_rate_limit(f"otp_verify:{voter_code_hash}", 5, 900)

    stored = _DEMO_OTP_STORE.get(voter_code_hash)
    if stored is None or not verify_secret(otp, stored[0]):
        await _record_attempt(session, voter_code_hash, ip_hash, success=False, reason="bad_otp")
        raise EligibilityError("INVALID_OTP", "OTP is invalid or expired.")

    result = await session.execute(
        select(SyntheticVoter)
        .where(SyntheticVoter.synthetic_voter_code == synthetic_voter_code)
        .with_for_update()
    )
    voter = result.scalar_one_or_none()
    if voter is None or not voter.is_eligible:
        raise EligibilityError("NOT_ELIGIBLE", "Voter is not eligible.")
    if voter.has_voted_flag:
        raise EligibilityError("ALREADY_VOTED", "This synthetic voter has already voted.")

    # Atomically flip has_voted_flag — this row lock plus the WHERE clause
    # below is what prevents two concurrent requests from both succeeding.
    await session.execute(
        update(SyntheticVoter)
        .where(SyntheticVoter.voter_id == voter.voter_id, SyntheticVoter.has_voted_flag.is_(False))
        .values(has_voted_flag=True)
    )

    raw_token, token_hash = generate_voting_token()
    expires_at = voting_token_expiry()

    credential = VotingCredential(
        token_hash=token_hash,
        election_id=election_id,
        constituency_id=voter.constituency_id,
        status="unused",
        expires_at=expires_at,
    )
    session.add(credential)

    await append_audit_event(
        session,
        event_type="voting_credential_issued",
        actor_role="system",
        payload={"election_id": election_id},  # no voter identity, no token
        election_id=election_id,
    )

    await session.commit()
    _DEMO_OTP_STORE.pop(voter_code_hash, None)

    return raw_token, expires_at


async def _record_attempt(
    session: AsyncSession, voter_code_hash: str, ip_hash: str, success: bool, reason: str
) -> None:
    session.add(
        AuthAttempt(voter_code_hash=voter_code_hash, ip_hash=ip_hash, success=success, reason=reason)
    )
    await session.commit()
