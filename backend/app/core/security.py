"""
Security primitives. Rules enforced here:
  - Raw OTPs, passwords, and voting tokens are NEVER written to logs.
  - Voting tokens are cryptographically random and stored only as SHA-256
    hashes (the raw value is returned to the client exactly once).
  - Passwords use argon2 (via passlib) — not a fast hash like MD5/SHA1.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password / OTP hashing (for admin accounts and simulated OTP secrets)
# ---------------------------------------------------------------------------

def hash_secret(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_secret(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


# ---------------------------------------------------------------------------
# Voter-code / IP hashing for audit-safe logging (one-way, not reversible)
# ---------------------------------------------------------------------------

def hash_for_logging(value: str) -> str:
    """One-way hash used ONLY so we can rate-limit/audit without storing
    the raw voter code or IP address in plaintext anywhere."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# One-time voting token
# ---------------------------------------------------------------------------

def generate_voting_token() -> tuple[str, str]:
    """Returns (raw_token, token_hash). Caller stores ONLY token_hash and
    returns raw_token to the client exactly once. Never log raw_token."""
    raw_token = secrets.token_urlsafe(settings.voting_token_bytes)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def voting_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.voting_token_expire_minutes)


# ---------------------------------------------------------------------------
# Reference numbers (voter-facing receipt — reveals nothing about choice)
# ---------------------------------------------------------------------------

def generate_reference_number() -> str:
    return f"REF-{secrets.token_hex(8).upper()}"


# ---------------------------------------------------------------------------
# JWT session tokens (admin/auditor/operator login, and short-lived voter
# session between OTP verification and ballot casting)
# ---------------------------------------------------------------------------

def create_access_token(subject: str, role: str, extra_claims: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ---------------------------------------------------------------------------
# Simulated OTP (research/demo only — NOT a real SMS/authenticator flow)
# ---------------------------------------------------------------------------

def generate_demo_otp() -> str:
    """6-digit numeric OTP, cryptographically random. In this DEMO the
    value is returned in the API response so the prototype is testable
    without an SMS gateway. A real system would never do this."""
    return f"{secrets.randbelow(1_000_000):06d}"
