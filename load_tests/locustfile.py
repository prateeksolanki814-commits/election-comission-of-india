"""
Locust load test — simulates up to 100,000 concurrent synthetic voters
performing the full login -> verify-otp -> cast-ballot flow.

IMPORTANT — run this only against a local/non-production environment
seeded with synthetic voters (see database/generate_synthetic_voters.py).
Never point this at a real system.

Run:
    locust -f locustfile.py --host http://localhost:8000

For a scripted 100k-user ramp (headless):
    locust -f locustfile.py --host http://localhost:8000 \
        --users 100000 --spawn-rate 500 --run-time 20m --headless \
        --csv=results/run1

See docs/SCALABILITY.md for the recommended staged ramp plan and how to
read p50/p95/p99 output.
"""
import random
import uuid

from locust import HttpUser, between, task

# Populated by an external fixture step (see load_tests/README.md) that
# lists which synthetic voter codes are available to this test run, plus
# valid election/constituency/candidate IDs for the seeded demo election.
VOTER_CODE_POOL = [f"DEMO-VOTER-{i:07d}" for i in range(100_000)]
ELECTION_ID = "REPLACE_WITH_SEEDED_ELECTION_ID"
CONSTITUENCY_CANDIDATES = {
    # "constituency_id": ["candidate_id_1", "candidate_id_2", ...]
}


class VoterFlow(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.voter_code = VOTER_CODE_POOL.pop() if VOTER_CODE_POOL else f"DEMO-VOTER-{random.randint(0, 99999):07d}"

    @task
    def full_voting_flow(self):
        # Step 1: login
        with self.client.post(
            "/api/v1/auth/login",
            json={"synthetic_voter_code": self.voter_code},
            catch_response=True,
        ) as login_resp:
            if login_resp.status_code != 200:
                login_resp.failure(f"login failed: {login_resp.status_code}")
                return
            otp = login_resp.json().get("demo_otp")

        # Step 2: verify OTP -> get voting token
        with self.client.post(
            "/api/v1/auth/verify-otp",
            json={
                "synthetic_voter_code": self.voter_code,
                "otp": otp,
                "election_id": ELECTION_ID,
            },
            catch_response=True,
        ) as verify_resp:
            if verify_resp.status_code != 200:
                verify_resp.failure(f"verify-otp failed: {verify_resp.status_code}")
                return
            voting_token = verify_resp.json().get("voting_token")

        if not CONSTITUENCY_CANDIDATES:
            return  # not seeded; skip ballot step so login/otp still gets measured

        constituency_id = random.choice(list(CONSTITUENCY_CANDIDATES.keys()))
        candidate_id = random.choice(CONSTITUENCY_CANDIDATES[constituency_id])

        # Step 3: cast ballot
        idempotency_key = str(uuid.uuid4())
        with self.client.post(
            "/api/v1/ballot/cast",
            json={
                "voting_token": voting_token,
                "election_id": ELECTION_ID,
                "constituency_id": constituency_id,
                "candidate_id": candidate_id,
            },
            headers={"Idempotency-Key": idempotency_key},
            catch_response=True,
        ) as cast_resp:
            if cast_resp.status_code != 200:
                cast_resp.failure(f"cast failed: {cast_resp.status_code}")

    @task(1)
    def repeat_vote_attempt_should_fail(self):
        """Adversarial task: intentionally try to reuse a stale/invalid
        token to confirm the API correctly rejects it under load, not just
        in unit tests."""
        idempotency_key = str(uuid.uuid4())
        with self.client.post(
            "/api/v1/ballot/cast",
            json={
                "voting_token": "intentionally-invalid-token",
                "election_id": ELECTION_ID,
                "constituency_id": "00000000-0000-0000-0000-000000000000",
                "candidate_id": "00000000-0000-0000-0000-000000000000",
            },
            headers={"Idempotency-Key": idempotency_key},
            catch_response=True,
        ) as resp:
            if resp.status_code == 409:
                resp.success()
            else:
                resp.failure(f"expected 409 for invalid token, got {resp.status_code}")
