"""API contract tests. The service layer is stubbed so these do not need Postgres."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import experiments as service


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("api.main.ping", lambda *_a, **_k: False)
    monkeypatch.setattr("analytics.db.ping", lambda *_a, **_k: False)
    with TestClient(app) as test_client:
        yield test_client

ANALYSIS = {
    "experiment": {
        "experiment_id": 1,
        "experiment_key": "EXP-024",
        "name": "Simplified booking experience",
        "surface": "Booking Flow",
        "status": "running",
        "primary_metric": "booking_conversion_rate",
        "randomisation_unit": "user",
        "significance_level": 0.05,
        "started_at": "2026-06-19",
        "ended_at": "2026-07-02",
        "users": 1000,
        "sessions": 1180,
        "is_simulated": True,
        "data_source": "Inside Airbnb London (listings) + simulated event stream",
        "hypothesis": "Variant B increases booking conversion.",
        "control_label": "Existing booking experience",
        "treatment_label": "Simplified booking experience",
        "duration_days": 14,
        "first_session_at": "2026-06-19T00:00:00+00:00",
        "last_session_at": "2026-07-02T23:00:00+00:00",
    },
    "summary": [
        {
            "variant": "A",
            "variant_label": "control",
            "users": 500,
            "sessions": 590,
            "converted_users": 49,
            "conversions": 49,
            "cta_clicks": 190,
            "checkout_starts": 80,
            "bounces": 400,
            "cancellations": 3,
            "gross_revenue": 12000.0,
            "net_revenue": 11000.0,
            "conversion_rate": 0.098,
            "session_conversion_rate": 0.083,
            "cta_click_rate": 0.322,
            "checkout_start_rate": 0.136,
            "bounce_rate": 0.678,
            "checkout_abandon_rate": 0.39,
            "cancellation_rate": 0.06,
            "average_booking_value": 224.49,
            "revenue_per_visitor": 22.0,
            "allocation_share": 0.5,
            "conversion_absolute_uplift": 0.0,
            "conversion_relative_uplift": 0.0,
        },
        {
            "variant": "B",
            "variant_label": "treatment",
            "users": 500,
            "sessions": 590,
            "converted_users": 54,
            "conversions": 54,
            "cta_clicks": 205,
            "checkout_starts": 90,
            "bounces": 385,
            "cancellations": 3,
            "gross_revenue": 13000.0,
            "net_revenue": 12000.0,
            "conversion_rate": 0.108,
            "session_conversion_rate": 0.092,
            "cta_click_rate": 0.347,
            "checkout_start_rate": 0.153,
            "bounce_rate": 0.653,
            "checkout_abandon_rate": 0.40,
            "cancellation_rate": 0.055,
            "average_booking_value": 222.22,
            "revenue_per_visitor": 24.0,
            "allocation_share": 0.5,
            "conversion_absolute_uplift": 0.01,
            "conversion_relative_uplift": 0.102,
        },
    ],
    "secondary_metrics": [],
    "guardrails": [],
    "statistics": {
        "primary": {
            "control_visitors": 500,
            "treatment_visitors": 500,
            "control_conversions": 49,
            "treatment_conversions": 54,
            "control_rate": 0.098,
            "treatment_rate": 0.108,
            "control_rate_ci": [0.07, 0.13],
            "treatment_rate_ci": [0.08, 0.14],
            "absolute_uplift": 0.01,
            "relative_uplift": 0.102,
            "confidence_interval": [-0.02, 0.04],
            "relative_confidence_interval": [-0.2, 0.4],
            "z_score": 0.52,
            "p_value": 0.60,
            "standard_error": 0.019,
            "confidence_level": 0.95,
            "significance_level": 0.05,
            "statistically_significant": False,
            "observed_power": 0.12,
        },
        "secondary": {},
        "revenue_per_visitor": {
            "control_mean": 22.0,
            "treatment_mean": 24.0,
            "absolute_uplift": 2.0,
            "relative_uplift": 0.09,
            "confidence_interval": [-1.0, 5.0],
            "t_statistic": 0.8,
            "p_value": 0.4,
            "statistically_significant": False,
        },
        "sample_ratio": {
            "control_units": 500,
            "treatment_units": 500,
            "expected_ratio": 0.5,
            "observed_ratio": 0.5,
            "chi_square": 0.0,
            "p_value": 1.0,
            "mismatch_detected": False,
        },
        "minimum_detectable_effect": {
            "baseline_rate": 0.098,
            "n_per_variant": 500,
            "alpha": 0.05,
            "power": 0.8,
            "mde_absolute": 0.04,
            "mde_relative": 0.4,
        },
        "planned_sample_size": {
            "baseline_rate": 0.098,
            "mde_relative": 0.05,
            "mde_absolute": 0.0049,
            "target_rate": 0.1029,
            "alpha": 0.05,
            "power": 0.8,
            "effect_size": 0.016,
            "required_per_variant": 58000,
            "required_total": 116000,
        },
    },
    "decision": {
        "verdict": "inconclusive",
        "decision": "keep_running",
        "headline": "Inconclusive — the interval still includes zero",
        "rationale": ["Need more data."],
        "guardrails_ok": True,
    },
    "projected_impact": {
        "annual_visitors": 26000,
        "revenue_per_visitor_delta": 2.0,
        "annualised_gross_booking_delta": 52000.0,
        "platform_take_rate": 0.15,
        "annualised_revenue_delta": 7800.0,
        "basis": "Projection from observed traffic.",
    },
    "validation": [],
}


def test_root_declares_simulated_events(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "simulated" in body["data_note"].lower()


def test_health_shape(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body
    assert body["version"]


def test_analysis_endpoint_validates_against_schema(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(service, "resolve_experiment_id", lambda _id: 1)
    monkeypatch.setattr(service, "get_analysis", lambda *_a, **_k: ANALYSIS)
    response = client.get("/experiments/EXP-024/analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["experiment"]["is_simulated"] is True
    assert body["decision"]["verdict"] == "inconclusive"
    assert body["statistics"]["primary"]["control_rate"] == 0.098


def test_unknown_experiment_is_404(client: TestClient, monkeypatch) -> None:
    def _missing(_id: str) -> int:
        raise service.ExperimentNotFound("No experiment matching 'NOPE'")

    monkeypatch.setattr(service, "resolve_experiment_id", _missing)
    response = client.get("/experiments/NOPE")
    assert response.status_code == 404


def test_sql_catalogue_is_read_only(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "list_sql_queries",
        lambda: [{"name": "conversion", "title": "Conversion",
                  "description": "Primary metric", "sql": "SELECT 1"}],
    )
    response = client.get("/experiments/sql")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "conversion"


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
