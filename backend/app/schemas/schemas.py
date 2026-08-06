from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    synthetic_voter_code: str = Field(..., min_length=4, max_length=20)


class LoginResponse(BaseModel):
    message: str
    demo_otp: str  # DEMO ONLY — real system sends via SMS, never in response


class VerifyOtpRequest(BaseModel):
    synthetic_voter_code: str = Field(..., min_length=4, max_length=20)
    otp: str = Field(..., min_length=6, max_length=6)
    election_id: str


class VerifyOtpResponse(BaseModel):
    voting_token: str
    expires_at: datetime


class CastBallotRequest(BaseModel):
    voting_token: str
    election_id: str
    constituency_id: str
    candidate_id: str


class CastBallotResponse(BaseModel):
    reference_number: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiError(BaseModel):
    success: bool = False
    error: ErrorDetail
