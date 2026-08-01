"""Small, dependency-free forecasting utilities for auditable method selection.

The industry agent must not claim that a machine-learning model ran merely
because prose evidence contains numbers.  This module therefore accepts only
an explicitly structured, same-metric time series.  When that input is absent
or too short, Future Intelligence falls back to causal scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean

from src.models.future import ForecastMethod, ForecastMethodology


@dataclass(frozen=True)
class TimeSeriesObservation:
    period: int
    value: float


@dataclass(frozen=True)
class ForecastResult:
    method: ForecastMethod
    forecasts: list[float]
    validation_smape: float | None
    lower_bounds: list[float]
    upper_bounds: list[float]


def _smape(actual: list[float], predicted: list[float]) -> float:
    terms = []
    for observed, forecast in zip(actual, predicted, strict=True):
        denominator = abs(observed) + abs(forecast)
        terms.append(0.0 if denominator == 0 else 2 * abs(observed - forecast) / denominator)
    return mean(terms) * 100 if terms else 0.0


def _linear_fit(values: list[float]) -> tuple[float, float]:
    x_values = list(range(len(values)))
    x_mean = mean(x_values)
    y_mean = mean(values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    slope = 0.0 if denominator == 0 else sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(x_values, values, strict=True)
    ) / denominator
    return y_mean - slope * x_mean, slope


def _one_step_predictions(values: list[float], method: ForecastMethod) -> list[float]:
    predictions: list[float] = []
    for index in range(3, len(values)):
        train = values[:index]
        if method == ForecastMethod.NAIVE_BASELINE:
            predictions.append(train[-1])
        elif method == ForecastMethod.EXPONENTIAL_SMOOTHING:
            level = train[0]
            for value in train[1:]:
                level = 0.4 * value + 0.6 * level
            predictions.append(level)
        else:
            intercept, slope = _linear_fit(train)
            predictions.append(intercept + slope * len(train))
    return predictions


def forecast_structured_series(
    observations: list[TimeSeriesObservation],
    *,
    periods_ahead: int,
) -> ForecastResult:
    """Select a small-sample model using rolling-origin sMAPE.

    This is intentionally conservative: regularized driver regression is only
    a candidate when a separate, sufficiently long driver matrix is supplied
    by a future extension.  A univariate series is evaluated against a naive
    baseline, exponential smoothing and trend regression.
    """

    ordered = sorted(observations, key=lambda item: item.period)
    if len(ordered) < 6 or len({item.period for item in ordered}) != len(ordered):
        raise ValueError("量化预测至少需要6个不重复期间的同口径结构化观测")
    values = [item.value for item in ordered]
    methods = (
        ForecastMethod.NAIVE_BASELINE,
        ForecastMethod.EXPONENTIAL_SMOOTHING,
        ForecastMethod.TREND_REGRESSION,
    )
    actual = values[3:]
    scores = {
        method: _smape(actual, _one_step_predictions(values, method))
        for method in methods
    }
    selected = min(methods, key=scores.get)
    if selected == ForecastMethod.NAIVE_BASELINE:
        forecasts = [values[-1]] * periods_ahead
    elif selected == ForecastMethod.EXPONENTIAL_SMOOTHING:
        level = values[0]
        for value in values[1:]:
            level = 0.4 * value + 0.6 * level
        forecasts = [level] * periods_ahead
    else:
        intercept, slope = _linear_fit(values)
        forecasts = [intercept + slope * (len(values) + step) for step in range(periods_ahead)]
    fitted = _one_step_predictions(values, selected)
    residuals = [observed - predicted for observed, predicted in zip(actual, fitted, strict=True)]
    residual_sd = sqrt(mean([value**2 for value in residuals])) if residuals else 0.0
    margin = 1.96 * residual_sd
    return ForecastResult(
        method=selected,
        forecasts=forecasts,
        validation_smape=round(scores[selected], 2),
        lower_bounds=[value - margin for value in forecasts],
        upper_bounds=[value + margin for value in forecasts],
    )


def build_forecast_methodology(
    observations: list[TimeSeriesObservation] | None = None,
) -> ForecastMethodology:
    """Return the method gate recorded on every Future Intelligence artifact."""

    observations = observations or []
    if len(observations) < 6:
        return ForecastMethodology(
            data_sufficiency="insufficient",
            structured_observation_count=len(observations),
            selected_method=ForecastMethod.CAUSAL_SCENARIO,
            benchmark_method=ForecastMethod.NAIVE_BASELINE,
            candidate_methods=[
                ForecastMethod.NAIVE_BASELINE,
                ForecastMethod.EXPONENTIAL_SMOOTHING,
                ForecastMethod.TREND_REGRESSION,
                ForecastMethod.REGULARIZED_DRIVER_REGRESSION,
            ],
            validation_design="取得同口径序列后采用滚动时间窗验证，并与朴素基准比较。",
            error_metrics=["sMAPE", "MAE"],
            prediction_interval="当前不输出数值区间；以基准、加速和受阻情景表达不确定性。",
            quantitative_forecast_used=False,
            selection_rationale="公开证据尚未形成至少6期同一指标、同一口径的结构化序列，因此降级为因果情景法。",
            model_limitations=[
                "网页证据中的零散数字不等同于可训练时间序列。",
                "结构突变、监管变化及口径调整可能使历史关系失效。",
            ],
        )
    result = forecast_structured_series(observations, periods_ahead=1)
    return ForecastMethodology(
        data_sufficiency="adequate",
        structured_observation_count=len(observations),
        selected_method=result.method,
        benchmark_method=ForecastMethod.NAIVE_BASELINE,
        candidate_methods=[
            ForecastMethod.NAIVE_BASELINE,
            ForecastMethod.EXPONENTIAL_SMOOTHING,
            ForecastMethod.TREND_REGRESSION,
        ],
        validation_design="滚动起点的一步预测验证；以sMAPE最低且优于朴素基准者为选定方法。",
        error_metrics=[f"rolling_sMAPE={result.validation_smape}", "MAE"],
        prediction_interval="依据滚动验证残差构造95%经验预测区间。",
        quantitative_forecast_used=True,
        selection_rationale=f"{result.method.value}在滚动验证中的sMAPE最低。",
        model_limitations=[
            "小样本模型只能作为因果情景与市场规模模型的交叉验证。",
            "发生结构突变或统计口径变化时必须重训并重新验证。",
        ],
    )
