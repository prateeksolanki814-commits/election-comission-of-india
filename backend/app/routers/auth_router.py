from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import RateLimitExceeded
from app.db.session import get_eligibility_db
from app.schemas.schemas import LoginRequest, LoginResponse, VerifyOtpRequest, VerifyOtpResponse
from app.services.eligibility_service import EligibilityError, start_login, verify_otp_and_issue_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_eligibility_db),
):
    if settings.emergency_mode:
        raise HTTPException(status_code=503, detail="Online voting is disabled (emergency fallback mode).")
    try:
        otp = await start_login(db, payload.synthetic_voter_code, request.client.host)
    except EligibilityError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Retry after {e.retry_after_seconds}s.")

    return LoginResponse(
        message="Demo OTP generated. In a real deployment this would be sent via SMS, not returned here.",
        demo_otp=otp,
    )


@router.post("/verify-otp", response_model=VerifyOtpResponse)
async def verify_otp(
    payload: VerifyOtpRequest,
    request: Request,
    db: AsyncSession = Depends(get_eligibility_db),
):
    if settings.emergency_mode:
        raise HTTPException(status_code=503, detail="Online voting is disabled (emergency fallback mode).")
    try:
        raw_token, expires_at = await verify_otp_and_issue_token(
            db,
            payload.synthetic_voter_code,
            payload.otp,
            payload.election_id,
            request.client.host,
        )
    except EligibilityError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Retry after {e.retry_after_seconds}s.")

    return VerifyOtpResponse(voting_token=raw_token, expires_at=expires_at)
