from __future__ import annotations

import pytest

from src.models.future import ForecastMethod
from src.services.forecasting import (
    TimeSeriesObservation,
    build_forecast_methodology,
    forecast_structured_series,
)


def test_sparse_evidence_degrades_to_causal_scenarios() -> None:
    methodology = build_forecast_methodology(
        [TimeSeriesObservation(period=2024, value=100.0)]
    )

    assert methodology.selected_method == ForecastMethod.CAUSAL_SCENARIO
    assert methodology.quantitative_forecast_used is False
    assert methodology.structured_observation_count == 1
    assert "降级" in methodology.selection_rationale


def test_structured_series_uses_rolling_validation() -> None:
    observations = [
        TimeSeriesObservation(period=year, value=value)
        for year, value in zip(
            range(2018, 2026),
            [100.0, 108.0, 116.0, 126.0, 137.0, 149.0, 162.0, 176.0],
            strict=True,
        )
    ]

    result = forecast_structured_series(observations, periods_ahead=3)
    methodology = build_forecast_methodology(observations)

    assert len(result.forecasts) == 3
    assert result.validation_smape is not None
    assert methodology.quantitative_forecast_used is True
    assert methodology.selected_method in {
        ForecastMethod.NAIVE_BASELINE,
        ForecastMethod.EXPONENTIAL_SMOOTHING,
        ForecastMethod.TREND_REGRESSION,
    }
    assert "rolling_sMAPE" in methodology.error_metrics[0]


def test_quantitative_forecast_rejects_short_or_duplicate_series() -> None:
    with pytest.raises(ValueError, match="至少需要6个"):
        forecast_structured_series(
            [TimeSeriesObservation(period=2024, value=100.0)] * 6,
            periods_ahead=1,
        )
