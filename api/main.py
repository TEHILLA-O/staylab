"""StayLab API.

Serves the analysis the SQL views and the statistics package produce. It never
computes a dashboard number of its own, and it never executes SQL supplied by
a caller.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from analytics.db import get_engine, ping
from analytics.logging_config import configure_logging, get_logger
from api.routes import experiments, health
from api.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("staylab.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if ping(get_engine()):
        log.info("database reachable")
    else:
        # Deliberately non-fatal: /health should be able to report the outage.
        log.error("database unreachable at startup — endpoints will return 503")
    yield


app = FastAPI(
    title="StayLab Experimentation API",
    version=health.API_VERSION,
    description=(
        "A/B experiment analytics over Inside Airbnb London data.\n\n"
        "**Data note.** Listing and calendar data are real (Inside Airbnb, "
        "London snapshot). The experiment assignments, sessions, funnel events "
        "and bookings are simulated: Inside Airbnb publishes no user-level "
        "experiment data. Metrics are computed from the stored simulated events, "
        "never hard-coded."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request failed", extra={
            "request_id": request_id, "path": request.url.path,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        raise
    duration = round((time.perf_counter() - started) * 1000, 1)
    log.info("request", extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": duration,
    })
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(duration)
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Surface database outages as 503 with a message the UI can render."""
    log.error("database error", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The analytics database is unavailable. "
                      "Start it with `docker compose up -d db` and reload.",
            "code": "database_unavailable",
        },
    )


app.include_router(health.router)
app.include_router(experiments.router)


@app.get("/", tags=["system"], summary="Service metadata")
def root() -> dict:
    return {
        "service": "StayLab Experimentation API",
        "version": health.API_VERSION,
        "docs": "/docs",
        "default_experiment": settings.default_experiment_key,
        "data_note": (
            "Real Inside Airbnb London listings; simulated randomised experiment "
            "event stream."
        ),
    }
