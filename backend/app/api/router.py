"""API v1 router — liveness and readiness endpoints.

Liveness (``/health``) answers "is the process up?" and never touches the database.
Readiness (``/ready``) answers "can the process serve traffic?" and returns 503 with
a reason when the database is unreachable. They are deliberately different questions.
"""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import check_db_ready

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Always 200 while the process is running."""
    return {"status": "ok", "version": settings.version}


@router.get("/ready")
async def ready(response: Response) -> dict[str, str]:
    """Readiness probe. 200 only when the database is reachable, else 503."""
    try:
        await check_db_ready()
    except Exception as exc:
        logger.warning("readiness_check_failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": str(exc)}
    return {"status": "ready"}
