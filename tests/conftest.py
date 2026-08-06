"""
Shared pytest fixtures.

Requires a disposable Postgres test database (never point this at a real
deployment). Set TEST_DATABASE_ELIGIBILITY_URL / TEST_DATABASE_BALLOT_URL
env vars, or run via `docker compose -f docker-compose.test.yml up` which
provisions a throwaway Postgres with database/schema.sql applied.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import generate_voting_token

ELIGIBILITY_URL = os.environ.get(
    "TEST_DATABASE_ELIGIBILITY_URL",
    "postgresql+asyncpg://role_eligibility_svc:change_me_eligibility@localhost:5432/vote_research_demo",
)
BALLOT_URL = os.environ.get(
    "TEST_DATABASE_BALLOT_URL",
    "postgresql+asyncpg://role_ballot_svc:change_me_ballot@localhost:5432/vote_research_demo",
)


@pytest_asyncio.fixture
async def ballot_db_session_factory():
    engine = create_async_engine(BALLOT_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def ballot_db_session(ballot_db_session_factory):
    async with ballot_db_session_factory() as session:
        yield session


async def _seed_election(admin_engine, raw_token_expiry_minutes=15):
    election_id = str(uuid.uuid4())
    constituency_id = str(uuid.uuid4())
    candidate_id = str(uuid.uuid4())
    raw_token, token_hash = generate_voting_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=raw_token_expiry_minutes)

    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO ballots.elections (election_id, title, status) VALUES (:e, 'Test Election', 'open')"),
            {"e": election_id},
        )
        await conn.execute(
            text(
                "INSERT INTO ballots.constituencies (constituency_id, election_id, name, code) "
                "VALUES (:c, :e, 'Test Constituency', :code)"
            ),
            {"c": constituency_id, "e": election_id, "code": f"TC-{uuid.uuid4().hex[:6]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO ballots.fictional_candidates "
                "(candidate_id, election_id, constituency_id, name, symbol, manifesto_summary) "
                "VALUES (:cand, :e, :c, 'Fictional Candidate A', 'Lantern', 'Demo manifesto')"
            ),
            {"cand": candidate_id, "e": election_id, "c": constituency_id},
        )
        await conn.execute(
            text(
                "INSERT INTO eligibility.voting_credentials "
                "(token_hash, election_id, constituency_id, status, expires_at) "
                "VALUES (:th, :e, :c, 'unused', :exp)"
            ),
            {"th": token_hash, "e": election_id, "c": constituency_id, "exp": expires_at},
        )

    return {
        "election_id": election_id,
        "constituency_id": constituency_id,
        "candidate_id": candidate_id,
        "raw_token": raw_token,
    }


@pytest_asyncio.fixture
async def seeded_election():
    admin_url = os.environ.get(
        "TEST_DATABASE_ADMIN_URL",
        "postgresql+asyncpg://role_admin_svc:change_me_admin@localhost:5432/vote_research_demo",
    )
    engine = create_async_engine(admin_url)
    data = await _seed_election(engine)
    yield data
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_election_expired_token():
    admin_url = os.environ.get(
        "TEST_DATABASE_ADMIN_URL",
        "postgresql+asyncpg://role_admin_svc:change_me_admin@localhost:5432/vote_research_demo",
    )
    engine = create_async_engine(admin_url)
    data = await _seed_election(engine, raw_token_expiry_minutes=-15)  # already expired
    yield data
    await engine.dispose()
