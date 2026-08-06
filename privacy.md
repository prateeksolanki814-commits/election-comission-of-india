# Privacy Model

> DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS.

## Consent & Transparency Notice (shown to every synthetic voter)

> By continuing, you acknowledge this is a research prototype using only
> synthetic data. No real votes, identities, or results are involved. Your
> ballot choice is never linked to your identity in this system.

This notice is rendered on every voter-facing screen (`frontend/app.py`)
before login.

## How Identity Is Separated From Ballot Content

1. **Two schemas, two Postgres roles.** `eligibility.*` tables (voter
   identity, OTP, has_voted flag) are only reachable by `role_eligibility_svc`.
   `ballots.*` tables (candidates, anonymous ballots) are only reachable by
   `role_ballot_svc`. Neither role can read the other's core tables — this
   is enforced by `GRANT`/absence-of-`GRANT` in `database/schema.sql`, not
   just by application code discipline.
2. **No foreign key** exists from `ballots.anonymous_ballots` to
   `eligibility.synthetic_voters`. There is no `voter_id` column on the
   ballot table at all. A database administrator with full read access to
   `anonymous_ballots` still cannot answer "how did voter X vote" — the
   information needed to answer that question does not exist in that
   table.
3. **The bridge is a token, not an identity.** `eligibility.voting_credentials`
   holds only a hashed token, an election ID, and a constituency ID — never
   a voter ID. The raw token is generated from a cryptographically secure
   random source (`secrets.token_urlsafe`), not derived in any way from the
   voter's identity, so it cannot be reversed to find out who received it.
4. **Minimum data collected.** We log only: hashed voter code + hashed IP
   for rate-limiting/audit (not plaintext), a boolean has-voted flag, and
   aggregate timestamps. We do not log device fingerprints, browser
   fingerprints, or geolocation.

## What Administrators Can and Cannot See

| Can see | Cannot see |
|---|---|
| Whether a given synthetic voter has voted (boolean) | Which candidate a given synthetic voter chose |
| Aggregate vote counts per constituency (after election close) | Any row-level ballot-to-voter mapping (doesn't exist) |
| Failed login/rate-limit events (hashed identifiers) | Raw voter codes or IPs in plaintext logs |
| Audit log of administrative actions | Individual ballot content tied to an actor |

## Data Retention & Deletion (configurable)

- `RETENTION_AUTH_ATTEMPTS_DAYS` (default 90): purge job removes
  `eligibility.auth_attempts` rows older than this window.
- `RETENTION_AUDIT_EVENTS_DAYS`: audit events are append-only and NOT
  auto-deleted by default, since deleting them would break the hash chain;
  any retention policy for audit logs should archive-and-re-anchor rather
  than delete, and is documented as a manual, audited operation.
- Synthetic voter and ballot data for a demo election can be fully dropped
  via `scripts/purge_demo_election.py <election_id>` for local cleanup
  between test runs.

## Why We Don't Use "Blockchain Solves This" Language

The optional audit-log hash-chain in this prototype (`audit_service.py`)
is a tamper-evidence mechanism for the *log of administrative and system
events* — it is not a distributed ledger, has no consensus mechanism, and
does not by itself guarantee election integrity. Claiming "blockchain
secures the election" would be misleading; see `THREAT_MODEL.md` section 4
for what is and is not solved by this prototype.
