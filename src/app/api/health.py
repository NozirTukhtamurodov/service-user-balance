"""Health check endpoints for Kubernetes probes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.base import get_db
from app.settings import Settings
from app.utils import get_idempotency_storage

ROUTER = APIRouter(tags=["Health"])


@ROUTER.get("/health")
async def health_check():
    """
    Liveness probe endpoint.

    Returns basic health status without checking external dependencies.
    Used by Kubernetes liveness probe.
    """
    return {"status": "healthy", "service": "balance-service"}


@ROUTER.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe endpoint.

    Checks if service is ready to handle requests by testing:
    - Database connectivity
    - Redis connectivity

    Used by Kubernetes readiness probe.
    """
    try:
        # Check database connectivity
        result = await db.execute(text("SELECT 1"))
        db_status = result.scalar() == 1

        if not db_status:
            raise HTTPException(status_code=503, detail="Database not ready")

        # Check Redis connectivity
        settings = Settings()
        redis_storage = get_idempotency_storage(redis_url=settings.redis_url)

        try:
            # Simple Redis ping test
            await redis_storage.set("health_check", "test", ttl=1)
            redis_status = True
        except Exception:
            redis_status = False

        if not redis_status:
            raise HTTPException(status_code=503, detail="Redis not ready")

        return {
            "status": "ready",
            "service": "balance-service",
            "dependencies": {"database": "ok", "redis": "ok"},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")
