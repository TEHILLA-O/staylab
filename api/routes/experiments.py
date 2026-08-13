"""Experiment endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, status

from api.schemas.experiment import (
    ExperimentAnalysis,
    ExperimentDetail,
    ExperimentSummaryCard,
    FunnelStep,
    MarketplaceOverview,
    SegmentResponse,
    SqlQuery,
    StatisticsBundle,
    TimeseriesPoint,
    VariantSummary,
)
from api.services import experiments as service

router = APIRouter(prefix="/experiments", tags=["experiments"])

SegmentType = Literal["device", "traffic_source", "neighbourhood", "room_type"]

ExperimentId = Path(
    ...,
    description="Numeric experiment id or experiment key such as EXP-024",
    examples=["EXP-024"],
)


def _resolve(identifier: str) -> int:
    try:
        return service.resolve_experiment_id(identifier)
    except service.ExperimentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _guard(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except service.ExperimentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("", response_model=list[ExperimentSummaryCard],
            summary="List all experiments")
def list_experiments() -> list[ExperimentSummaryCard]:
    return service.list_experiments()


@router.get("/sql", response_model=list[SqlQuery],
            summary="The SQL behind each metric")
def list_sql() -> list[SqlQuery]:
    """Read-only catalogue of the queries powering the dashboard.

    Registered by name only. There is no endpoint that executes caller-supplied
    SQL.
    """
    return service.list_sql_queries()


@router.get("/sql/{name}", response_model=SqlQuery, summary="A single SQL query")
def get_sql(name: str) -> SqlQuery:
    return _guard(service.get_sql_query, name)


@router.get("/{experiment}", response_model=ExperimentDetail,
            summary="Experiment metadata")
def get_experiment(experiment: str = ExperimentId) -> ExperimentDetail:
    return _guard(service.get_experiment, _resolve(experiment))


@router.get("/{experiment}/summary", response_model=list[VariantSummary],
            summary="Per-variant metric summary")
def get_summary(experiment: str = ExperimentId) -> list[VariantSummary]:
    return _guard(service.get_summary, _resolve(experiment))


@router.get("/{experiment}/timeseries", response_model=list[TimeseriesPoint],
            summary="Daily and cumulative conversion")
def get_timeseries(experiment: str = ExperimentId) -> list[TimeseriesPoint]:
    return _guard(service.get_timeseries, _resolve(experiment))


@router.get("/{experiment}/segments", response_model=SegmentResponse,
            summary="Segment breakdown")
def get_segments(
    experiment: str = ExperimentId,
    segment_type: SegmentType = Query("device", description="Segment dimension"),
    limit: int = Query(25, ge=1, le=100),
) -> SegmentResponse:
    return _guard(service.get_segments, _resolve(experiment), segment_type, limit)


@router.get("/{experiment}/funnel", response_model=list[FunnelStep],
            summary="Funnel step analysis")
def get_funnel(experiment: str = ExperimentId) -> list[FunnelStep]:
    return _guard(service.get_funnel, _resolve(experiment))


@router.get("/{experiment}/statistics", response_model=StatisticsBundle,
            summary="Significance tests and power")
def get_statistics(experiment: str = ExperimentId) -> StatisticsBundle:
    return _guard(service.get_statistics, _resolve(experiment))


@router.get("/{experiment}/analysis", response_model=ExperimentAnalysis,
            summary="Everything the dashboard needs in one call")
def get_analysis(
    experiment: str = ExperimentId,
    include_validation: bool = Query(True),
) -> ExperimentAnalysis:
    """Single round trip for the main dashboard page.

    Six separate requests would each re-run the same aggregates, so the
    headline view is served as one composed payload.
    """
    return _guard(service.get_analysis, _resolve(experiment), include_validation)


@router.get("/{experiment}/marketplace", response_model=MarketplaceOverview,
            summary="Underlying real listing data")
def get_marketplace(experiment: str = ExperimentId) -> MarketplaceOverview:
    return _guard(service.get_marketplace, _resolve(experiment))
