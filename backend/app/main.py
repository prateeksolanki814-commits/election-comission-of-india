"""
DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS.

FastAPI application entrypoint. Wires up routers, CORS, and a global
exception handler that guarantees we never accidentally leak stack traces
or internal details (which could contain sensitive info) to the client.
"""
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routers import auth_router, ballot_router, system_router

settings = get_settings()
logger = structlog.get_logger()

app = FastAPI(
    title="Remote Voting Research Prototype (DEMO)",
    description=(
        "DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS. "
        "Synthetic data only. Not affiliated with the Election Commission of India."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(ballot_router.router)
app.include_router(system_router.router)


@app.middleware("http")
async def add_demo_banner_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Demo-Notice"] = "DEMO-RESEARCH-PROTOTYPE-NOT-FOR-REAL-ELECTIONS"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak internal exception details to the client. Log server-side
    # only, and structlog is configured (see core/logging.py) to redact
    # known-sensitive field names automatically.
    logger.error("unhandled_exception", path=str(request.url), error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
    )


@app.get("/")
async def root():
    return {
        "notice": "DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS. Synthetic data only.",
        "docs": "/docs",
    }
