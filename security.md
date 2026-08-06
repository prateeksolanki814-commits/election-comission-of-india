# Security

> DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS. This document
> describes demo-grade protections and is explicit about what is NOT
> covered. See `THREAT_MODEL.md` for the full analysis.

## What Is a Demonstration vs. What Is Real Protection

| Protection | Status |
|---|---|
| One-time voting tokens, hashed at rest | Real (SHA-256, single-use enforced at DB level) |
| Password/OTP hashing (argon2) | Real |
| No FK between voters and ballots | Real (architectural, verified by grants) |
| Append-only, hash-chained audit log | Real (DB trigger blocks UPDATE/DELETE) |
| Rate limiting | Real, Redis-backed, demo-scale tuned |
| TLS | Config-ready, **not enabled by default in local Docker Compose** — you must supply certs for anything beyond localhost |
| OTP delivery | **Simulated only** — demo OTP is returned in the API response, which a real system must never do |
| End-to-end vote verifiability | **Not implemented** |
| Protection against compromised voter device | **Not implemented — out of scope for any browser-based system** |
| Independent security audit | **Not performed** |
| Legal/regulatory certification | **Not obtained, not applicable — this is not a real voting system** |

## Security Checklist (for anyone extending this prototype)

- [ ] Rotate every credential in `.env.example` before any shared/non-local use
- [ ] Enable TLS termination in front of the API (nginx/Caddy/load balancer)
- [ ] Confirm `role_ballot_svc` has no grant on `eligibility.synthetic_voters` (`\dp` in psql)
- [ ] Run `pytest tests/security/` against a disposable test DB before any change to `ballot_service.py` or `eligibility_service.py`
- [ ] Run `python scripts/verify_audit_chain.py` after any bulk data operation
- [ ] Never add a foreign key from `ballots.anonymous_ballots` to any table in the `eligibility` schema
- [ ] Never log a raw OTP, password, voting token, or candidate_id (see `app/core/logging.py` redaction list — extend it if you add new sensitive field names)
- [ ] Keep `EMERGENCY_MODE` fallback tested — it should always be possible to disable online voting instantly

## Data Handling

- No real Aadhaar numbers, EPIC numbers, names, or political-party data are used anywhere in this codebase.
- All voter records are synthetic (`DEMO-VOTER-XXXXXXX` codes) — see `database/generate_synthetic_voters.py`.
- Sensitive fields (OTP secrets, JWT secret) are never committed; `.env.example` contains only placeholders.
- Backups: see `docs/BACKUP_RESTORE.md` for the demo backup/restore procedure and configurable retention settings.

## Responsible Disclosure

This is a research/educational prototype, not a production system, so
there is no bug bounty. If you find a flaw in the architectural
voter/ballot separation, the audit-chain integrity mechanism, or the
duplicate-vote prevention logic, please open an issue in this repository
describing the flaw and, if possible, a minimal reproduction using only
synthetic data. Do not test against any system other than your own local
deployment of this prototype.

## Independent Certification Requirement

**Software of this kind must never be used for a real, binding election
without: (1) independent third-party security certification, (2) explicit
legal authorization from the relevant election authority, (3) a public
source-review period, and (4) direct oversight by election officials.**
None of those conditions apply to this repository.
