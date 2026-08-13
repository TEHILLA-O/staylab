"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter

from analytics.db import get_engine, ping
from api.schemas.experiment import HealthResponse

router = APIRouter(tags=["system"])

API_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health() -> HealthResponse:
    """Reports degraded rather than failing when the database is down.

    The dashboard can then render an explicit "analytics unavailable" state
    instead of a blank screen.
    """
    database_ok = ping(get_engine())
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        database=database_ok,
        version=API_VERSION,
    )
