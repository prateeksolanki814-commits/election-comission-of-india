# Data-Flow Diagrams

## 1. Voter Registration → Voting Credential Issuance

```mermaid
sequenceDiagram
    participant V as Voter (Client)
    participant API as FastAPI Gateway
    participant E as Eligibility Service
    participant R as Redis (rate limit)
    participant DB1 as Postgres: eligibility schema

    V->>API: POST /auth/login (synthetic_voter_id)
    API->>R: check rate limit(voter_id, ip)
    R-->>API: allowed
    API->>E: verify voter exists & election open
    E->>DB1: SELECT synthetic_voters WHERE voter_id
    DB1-->>E: voter row (eligible, has_voted=false)
    E-->>API: OTP challenge issued (simulated)
    API-->>V: 200 OTP sent (demo OTP shown on screen)

    V->>API: POST /auth/verify-otp
    API->>E: validate OTP (simulated, single-use)
    E->>DB1: mark has_voted_flag pending / lock row
    E->>E: generate 256-bit random token
    E->>DB1: INSERT voting_credentials(token_hash, election_id, status=unused)
    E-->>API: raw token (returned once)
    API-->>V: 200 { voting_token, expires_in }
    Note over V,API: Token is never logged. Voter identity stops here.
```

## 2. Anonymous Ballot Casting

```mermaid
sequenceDiagram
    participant V as Voter (Client)
    participant API as FastAPI Gateway
    participant B as Anonymous Ballot Service
    participant DB2 as Postgres: ballots schema
    participant C as Celery Worker
    participant AU as Audit Log (append-only)

    V->>API: POST /ballot/cast {voting_token, choice, Idempotency-Key}
    API->>B: forward request (no voter_id ever attached)
    B->>DB2: SELECT voting_credentials WHERE hash(token) FOR UPDATE
    alt token unused and not expired
        B->>DB2: BEGIN TX
        B->>DB2: INSERT anonymous_ballots(ballot_id, election_id, choice, cast_at)
        B->>DB2: UPDATE voting_credentials SET status='used'
        B->>DB2: COMMIT
        B->>C: enqueue audit-log-append (ballot_id hash only)
        C->>AU: append hash-chained audit event
        B-->>API: 201 { reference_number }
        API-->>V: 200 Receipt (reference_number only, no choice shown)
    else token already used / invalid / expired
        B-->>API: 409 Conflict (token reused) or 400 (invalid)
        API-->>V: Error — no ballot created
    end
```

## 3. Administrator: Close Election & Publish Results

```mermaid
sequenceDiagram
    participant A as Admin
    participant API as FastAPI Gateway
    participant B as Ballot Service
    participant DB2 as Postgres: ballots schema
    participant AN as Analytics Service
    participant AU as Audit Log

    A->>API: POST /admin/elections/{id}/close (admin role required)
    API->>B: set election.status = closed
    B->>DB2: UPDATE elections SET status='closed', closed_at=now()
    B->>AU: append audit event (election closed, actor=admin_id, no ballot data)
    A->>API: POST /admin/elections/{id}/publish-results
    API->>AN: aggregate anonymous_ballots GROUP BY candidate_id
    AN->>DB2: SELECT candidate_id, COUNT(*) FROM anonymous_ballots WHERE election_id=... GROUP BY candidate_id
    AN-->>API: aggregate counts only
    API->>AU: append audit event (results published, sha256 of result set)
    API-->>A: signed result report (JSON + hash signature)
```

## 4. Emergency Fallback Trigger

```mermaid
flowchart TD
    A[EMERGENCY_MODE flag or ops trigger] --> B{Online voting requested?}
    B -- Yes --> C[API returns 503 + fallback instructions payload]
    C --> D[Client renders physical-voting-center instructions in EN/HI]
    B -- No, dashboard/audit request --> E[Read-only services remain available]
    E --> F[Admin & auditor can still monitor system health]
```
