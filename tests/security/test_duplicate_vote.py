"""
Security tests: duplicate voting and token replay.

These tests exercise the exact atomic-update logic in
backend/app/services/ballot_service.py against a real (test) Postgres
instance — the guarantee we care about is a DB-level race condition
guarantee, which cannot be verified with mocks alone.

Run with: pytest tests/security/test_duplicate_vote.py -v
Requires: TEST_DATABASE_URL env var pointing at a disposable test DB with
the schema from database/schema.sql applied.
"""
import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ballot_service import BallotError, cast_ballot
from app.services.eligibility_service import verify_otp_and_issue_token


@pytest.mark.asyncio
async def test_same_token_cannot_cast_two_ballots(ballot_db_session: AsyncSession, seeded_election):
    """A single voting token must only ever succeed once, even though the
    two attempts here are issued back-to-back rather than concurrently."""
    token = seeded_election["raw_token"]
    election_id = seeded_election["election_id"]
    constituency_id = seeded_election["constituency_id"]
    candidate_id = seeded_election["candidate_id"]

    ref1 = await cast_ballot(
        ballot_db_session,
        raw_voting_token=token,
        election_id=election_id,
        constituency_id=constituency_id,
        candidate_id=candidate_id,
        idempotency_key=str(uuid.uuid4()),
        client_ip="127.0.0.1",
    )
    assert ref1.startswith("REF-")

    with pytest.raises(BallotError) as exc_info:
        await cast_ballot(
            ballot_db_session,
            raw_voting_token=token,
            election_id=election_id,
            constituency_id=constituency_id,
            candidate_id=candidate_id,
            idempotency_key=str(uuid.uuid4()),  # different idempotency key on purpose
            client_ip="127.0.0.1",
        )
    assert exc_info.value.code == "TOKEN_INVALID_OR_USED"


@pytest.mark.asyncio
async def test_concurrent_double_spend_only_one_wins(ballot_db_session_factory, seeded_election):
    """Fire two concurrent cast_ballot calls with the SAME token from two
    separate DB sessions (simulating two simultaneous HTTP requests) and
    assert exactly one succeeds. This is the real double-vote attack
    scenario, not just sequential reuse."""
    token = seeded_election["raw_token"]
    election_id = seeded_election["election_id"]
    constituency_id = seeded_election["constituency_id"]
    candidate_id = seeded_election["candidate_id"]

    async def attempt():
        async with ballot_db_session_factory() as session:
            try:
                ref = await cast_ballot(
                    session,
                    raw_voting_token=token,
                    election_id=election_id,
                    constituency_id=constituency_id,
                    candidate_id=candidate_id,
                    idempotency_key=str(uuid.uuid4()),
                    client_ip="127.0.0.1",
                )
                return ("ok", ref)
            except BallotError as e:
                return ("error", e.code)

    results = await asyncio.gather(attempt(), attempt())
    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, f"expected exactly one success, got {results}"
    assert outcomes.count("error") == 1


@pytest.mark.asyncio
async def test_replayed_request_with_same_idempotency_key_returns_same_reference(
    ballot_db_session: AsyncSession, seeded_election
):
    """A client that retries the exact same request (e.g. after a network
    timeout, using the same Idempotency-Key) must get back the SAME
    reference number, not a second ballot."""
    token = seeded_election["raw_token"]
    election_id = seeded_election["election_id"]
    constituency_id = seeded_election["constituency_id"]
    candidate_id = seeded_election["candidate_id"]
    idem_key = str(uuid.uuid4())

    ref1 = await cast_ballot(
        ballot_db_session, token, election_id, constituency_id, candidate_id, idem_key, "127.0.0.1"
    )
    ref2 = await cast_ballot(
        ballot_db_session, token, election_id, constituency_id, candidate_id, idem_key, "127.0.0.1"
    )
    assert ref1 == ref2


@pytest.mark.asyncio
async def test_expired_token_is_rejected(ballot_db_session: AsyncSession, seeded_election_expired_token):
    with pytest.raises(BallotError) as exc_info:
        await cast_ballot(
            ballot_db_session,
            raw_voting_token=seeded_election_expired_token["raw_token"],
            election_id=seeded_election_expired_token["election_id"],
            constituency_id=seeded_election_expired_token["constituency_id"],
            candidate_id=seeded_election_expired_token["candidate_id"],
            idempotency_key=str(uuid.uuid4()),
            client_ip="127.0.0.1",
        )
    assert exc_info.value.code == "TOKEN_INVALID_OR_USED"


@pytest.mark.asyncio
async def test_garbage_token_never_matches_any_row(ballot_db_session: AsyncSession, seeded_election):
    with pytest.raises(BallotError) as exc_info:
        await cast_ballot(
            ballot_db_session,
            raw_voting_token="not-a-real-token-" + str(uuid.uuid4()),
            election_id=seeded_election["election_id"],
            constituency_id=seeded_election["constituency_id"],
            candidate_id=seeded_election["candidate_id"],
            idempotency_key=str(uuid.uuid4()),
            client_ip="127.0.0.1",
        )
    assert exc_info.value.code == "TOKEN_INVALID_OR_USED"
