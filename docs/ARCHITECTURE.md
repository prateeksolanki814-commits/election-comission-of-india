# System Architecture — Remote Voting Research Prototype

> **DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS.**
> Synthetic data only. Not certified, not legally authorized, not affiliated
> with the Election Commission of India or any government body.

## 1. Design Goal

The core research question this prototype demonstrates: *can a system let
100,000 synthetic voters cast one ballot each, over a network, while making
it structurally impossible — not just policy-forbidden — for anyone
(including administrators) to link a stored ballot back to the voter who
cast it?*

Everything below is organized around one architectural rule:

> **Eligibility verification and ballot storage are two different services,
> two different databases/schemas, connected only by a one-time,
> unlinkable credential — never by a foreign key.**

## 2. High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Client Layer                              │
│   React SPA / Streamlit demo · EN+HI i18n · a11y (WCAG 2.1 AA)      │
└───────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS (TLS-ready)
┌───────────────────────────────▼────────────────────────────────────┐
│                        API Gateway / FastAPI                        │
│  - Rate limiting (Redis token bucket)                               │
│  - Request validation (Pydantic)                                    │
│  - RBAC (voter / admin / auditor / operator)                        │
│  - Structured audit logging (no PII, no OTP, no vote content)       │
└──────────┬───────────────────────────────┬──────────────────────────┘
           │                               │
┌──────────▼───────────────┐   ┌───────────▼────────────────────────┐
│  Eligibility Service      │   │  Anonymous Ballot Service           │
│  (Identity DB / schema A) │   │  (Ballot DB / schema B)             │
│  - synthetic_voters       │   │  - anonymous_ballots                │
│  - OTP simulation         │   │  - idempotency keys                 │
│  - issues ONE-TIME TOKEN  │──▶│  - accepts token, NOT voter identity│
│    (opaque, signed, no    │   │  - one ballot per token, enforced   │
│     voter_id inside)      │   │    by unique constraint on token    │
└──────────┬────────────────┘   └───────────┬──────────────────────────┘
           │                                │
           │        (no FK, no join path)   │
           ▼                                ▼
   voting_credentials table          anonymous_ballots table
   (token_hash, status, election_id) (ballot_id, election_id, choice,
                                       cast_at, no voter reference)
                                 │
┌────────────────────────────────▼───────────────────────────────────┐
│                  Background Workers (Celery + Redis broker)         │
│  - async ballot persistence confirmation                            │
│  - audit-log hash chaining                                          │
│  - metrics aggregation for dashboards                                │
└───────────────────────────────┬────────────────────────────────────┘
                                 │
┌───────────────────────────────▼────────────────────────────────────┐
│                    PostgreSQL (2 logical schemas)                   │
│  eligibility schema  |  ballots schema  |  audit schema             │
│  Row-level security, separate DB roles per schema, no cross-schema  │
│  foreign keys between voters and ballots.                           │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│              Analytics / Dashboard Service (read-only)              │
│  pandas + Plotly, reads AGGREGATES only, never per-voter joins      │
└───────────────────────────────────────────────────────────────────┘
```

## 3. How the Token Breaks the Link (Core Mechanism)

1. Voter authenticates (synthetic voter ID + simulated OTP) against the
   **Eligibility Service**.
2. On success, Eligibility Service marks `synthetic_voters.has_voted_flag`
   (boolean only — not *what* they voted) and issues a **one-time voting
   credential**: a cryptographically random 256-bit token. The token is
   hashed (SHA-256) before storage; only the hash is kept, exactly like a
   password. The raw token is returned to the client once and never logged.
3. The token is *opaque* — it contains no voter ID, no constituency-linking
   data beyond an election_id, and is not derived from any voter attribute
   (not HMAC'd from voter_id, not sequential). It is looked up by hash only.
4. Client presents the token to the **Anonymous Ballot Service**, a
   separate FastAPI router with its own DB session bound to a Postgres role
   that has **no SELECT grant** on `synthetic_voters`.
5. Ballot Service validates token status (`unused` → `used`, atomically via
   `SELECT ... FOR UPDATE` + unique constraint), stores the ballot keyed by
   a fresh random `ballot_id`, and never writes the token or any voter
   identifier into the ballot row.
6. Because the two services use different DB roles and there is no foreign
   key, even a full read of the `anonymous_ballots` table cannot be joined
   back to `synthetic_voters` — the join key simply does not exist in the
   ballot schema.

This is the same principle used in real-world "blind signature" e-voting
research (Chaum-style) simplified for demonstration: separate *who may
vote* from *what was voted*, and destroy the pointer between them at the
moment the vote is cast. **This prototype does not implement full
cryptographic blind signatures** — that is called out explicitly in
`THREAT_MODEL.md` as a known limitation, not a solved problem.

## 4. Technology Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (async) | native OpenAPI docs, Pydantic validation, async DB drivers |
| DB | PostgreSQL 16 | row-level security, strong constraint model, partitioning for scale |
| Cache/rate-limit | Redis 7 | token bucket rate limiting, Celery broker, session cache |
| Queue | Celery + Redis | async audit-log writes, metrics rollups |
| Frontend (demo) | Streamlit (v1) → React (v2) | Streamlit for fast functional demo; React for production-shaped UI |
| Analytics | pandas, NumPy, Plotly | aggregate-only dashboards |
| Load test | Locust | Python-native, scriptable ramp patterns for 100k VUs |
| Deployment | Docker Compose | reproducible local multi-service stack |
| Auth (demo) | synthetic ID + simulated OTP → JWT session (short-lived) | mirrors real flow without real identity systems |

## 5. Scalability Strategy (summary — full detail in `docs/SCALABILITY.md`)

- Stateless API pods behind a load balancer → horizontal scale.
- PgBouncer-style connection pooling (SQLAlchemy pool + external pooler for real deploys).
- Redis-based sliding-window rate limiter per voter-token and per IP.
- Ballot writes are idempotent via `Idempotency-Key` header + unique constraint,
  so retries under load never double-count.
- Read-heavy dashboard queries hit materialized views refreshed by Celery beat,
  never the live ballot table directly.
- Circuit breaker around Celery task submission; if the queue is saturated,
  API still accepts and durably stores the ballot synchronously before
  returning 202 — no ballot loss even if async processing lags.

## 6. Emergency Fallback Mode

A feature flag (`EMERGENCY_MODE=true` in `.env`) makes the API:
- Reject all new online ballot submissions with HTTP 503 and a structured
  message.
- Serve a static "physical voting instructions" page/response in every
  supported language.
- Keep the audit and dashboard services read-only and operational so
  officials can still monitor status.

## 7. What This Prototype Is *Not*

- Not a certified voting system.
- Not resistant to a compromised voter endpoint (malware on the voter's own
  device is out of scope for any remote-voting system — see `THREAT_MODEL.md`).
- Not using real cryptographic blind signatures or homomorphic tallying
  (documented as future work).
- Not legally authorized for binding elections of any kind.
