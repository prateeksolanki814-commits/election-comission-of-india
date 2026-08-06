"""
Separate SQLAlchemy async engines per Postgres ROLE — not just per schema.

This is intentional and is the technical enforcement of the eligibility /
ballot separation described in ARCHITECTURE.md: the ballot service's DB
session is opened with `role_ballot_svc`, a Postgres user that has no grant
on `eligibility.synthetic_voters` at all. Even a bug that tried to query
voter identity from the ballot router would fail at the database privilege
layer, not just be caught by code review.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# One engine per service role. Pool sizes tuned for the load-testing target
# (100k concurrent users funnelled through a bounded pool + async I/O, not
# 1:1 connections — see docs/SCALABILITY.md).
_engine_kwargs = dict(pool_size=20, max_overflow=40, pool_pre_ping=True, pool_recycle=1800)

eligibility_engine = create_async_engine(settings.eligibility_db_url, **_engine_kwargs)
ballot_engine = create_async_engine(settings.ballot_db_url, **_engine_kwargs)
admin_engine = create_async_engine(settings.admin_db_url, **_engine_kwargs)
analytics_engine = create_async_engine(settings.analytics_db_url, **_engine_kwargs)
auditor_engine = create_async_engine(settings.auditor_db_url, **_engine_kwargs)

EligibilitySession = async_sessionmaker(eligibility_engine, expire_on_commit=False, class_=AsyncSession)
BallotSession = async_sessionmaker(ballot_engine, expire_on_commit=False, class_=AsyncSession)
AdminSession = async_sessionmaker(admin_engine, expire_on_commit=False, class_=AsyncSession)
AnalyticsSession = async_sessionmaker(analytics_engine, expire_on_commit=False, class_=AsyncSession)
AuditorSession = async_sessionmaker(auditor_engine, expire_on_commit=False, class_=AsyncSession)


async def get_eligibility_db() -> AsyncGenerator[AsyncSession, None]:
    async with EligibilitySession() as session:
        yield session


async def get_ballot_db() -> AsyncGenerator[AsyncSession, None]:
    async with BallotSession() as session:
        yield session


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    async with AdminSession() as session:
        yield session


async def get_analytics_db() -> AsyncGenerator[AsyncSession, None]:
    async with AnalyticsSession() as session:
        yield session


async def get_auditor_db() -> AsyncGenerator[AsyncSession, None]:
    async with AuditorSession() as session:
        yield session
