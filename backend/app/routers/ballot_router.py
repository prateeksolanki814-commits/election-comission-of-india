from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import RateLimitExceeded
from app.db.session import get_ballot_db
from app.schemas.schemas import CastBallotRequest, CastBallotResponse
from app.services.ballot_service import BallotError, cast_ballot

router = APIRouter(prefix="/api/v1/ballot", tags=["ballot"])
settings = get_settings()


@router.post("/cast", response_model=CastBallotResponse)
async def cast(
    payload: CastBallotRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_ballot_db),
):
    """
    Note what this endpoint does NOT take as input: no voter_id, no
    session/auth header tying it to a person. Only the one-time voting
    token, the election/candidate selection, and a client-generated
    idempotency key for safe retries.
    """
    if settings.emergency_mode:
        raise HTTPException(status_code=503, detail="Online voting is disabled (emergency fallback mode).")

    # NOTE: client_ip is used only for rate limiting (hashed immediately)
    # and is never stored alongside the ballot itself.
    try:
        reference_number = await cast_ballot(
            db,
            raw_voting_token=payload.voting_token,
            election_id=payload.election_id,
            constituency_id=payload.constituency_id,
            candidate_id=payload.candidate_id,
            idempotency_key=idempotency_key,
            client_ip="0.0.0.0",  # populated from Request in production wiring
        )
    except BallotError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Retry after {e.retry_after_seconds}s.")

    return CastBallotResponse(
        reference_number=reference_number,
        message="Your ballot has been recorded. Keep this reference number for your records. "
        "It does not reveal your selection.",
    )
