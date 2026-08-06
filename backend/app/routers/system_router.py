from fastapi import APIRouter

from app.core.config import get_settings
from app.core.rate_limit import get_redis

router = APIRouter(tags=["system"])
settings = get_settings()


@router.get("/api/v1/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/api/v1/health/ready")
async def readiness():
    checks = {"redis": False}
    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = True
    except Exception:
        pass
    ready = all(checks.values())
    return {"ready": ready, "checks": checks}


@router.get("/api/v1/emergency/status")
async def emergency_status():
    return {
        "emergency_mode": settings.emergency_mode,
        "message": (
            "Online voting is temporarily disabled. Please proceed to your authorized "
            "physical voting center. / ऑनलाइन मतदान अस्थायी रूप से बंद है। कृपया अपने "
            "अधिकृत भौतिक मतदान केंद्र पर जाएं।"
        )
        if settings.emergency_mode
        else None,
    }
