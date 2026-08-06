"""
Synthetic voter generator — DEMO / RESEARCH PROTOTYPE.

Generates N synthetic voters with NO relationship to any real person.
Voter codes are sequential/random demo identifiers, never real EPIC or
Aadhaar numbers or formats that could be confused with them.

Usage:
    python generate_synthetic_voters.py --count 100000 --election-id <uuid> \
        --constituencies <uuid1>,<uuid2>,... --out synthetic_voters.csv

Writes a CSV suitable for bulk COPY into eligibility.synthetic_voters, plus
a separate credentials-safe summary (never containing the raw OTP secret
material, only hashes) so the file itself is safe to share for review.
"""
import argparse
import csv
import random
import uuid
from pathlib import Path

import bcrypt

FAKE_LANGUAGES = ["en", "hi"]


def hash_dummy_otp_secret() -> str:
    # Each synthetic voter gets a random placeholder OTP secret hash.
    # Real OTPs are generated per-login at runtime (see eligibility_service.py);
    # this column exists for schema completeness in the generator/demo context.
    dummy = uuid.uuid4().hex
    return bcrypt.hashpw(dummy.encode(), bcrypt.gensalt()).decode()


def generate(count: int, constituency_ids: list[str], out_path: Path) -> None:
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "voter_id",
                "synthetic_voter_code",
                "constituency_id",
                "otp_secret_hash",
                "language_pref",
                "accessibility_prefs",
                "has_voted_flag",
                "is_eligible",
            ]
        )
        for i in range(count):
            voter_id = str(uuid.uuid4())
            code = f"DEMO-VOTER-{i:07d}"
            constituency_id = random.choice(constituency_ids)
            lang = random.choice(FAKE_LANGUAGES)
            writer.writerow(
                [
                    voter_id,
                    code,
                    constituency_id,
                    hash_dummy_otp_secret(),
                    lang,
                    "{}",
                    "false",
                    "true",
                ]
            )
    print(f"Wrote {count} synthetic voters to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic voters for the demo election.")
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument(
        "--constituencies",
        type=str,
        required=True,
        help="Comma-separated list of existing constituency UUIDs to assign voters to.",
    )
    parser.add_argument("--out", type=str, default="synthetic_voters.csv")
    args = parser.parse_args()

    constituency_ids = [c.strip() for c in args.constituencies.split(",") if c.strip()]
    if not constituency_ids:
        raise SystemExit("Provide at least one constituency UUID via --constituencies")

    generate(args.count, constituency_ids, Path(args.out))
    print(
        "To load into Postgres:\n"
        f"  \\copy eligibility.synthetic_voters(voter_id,synthetic_voter_code,constituency_id,"
        f"otp_secret_hash,language_pref,accessibility_prefs,has_voted_flag,is_eligible) "
        f"FROM '{args.out}' WITH (FORMAT csv, HEADER true)"
    )


if __name__ == "__main__":
    main()
