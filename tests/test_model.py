import numpy as np
import pandas as pd

from services.ml_service.train import FEATURE_COLUMNS, engineer_features, evaluate, fit, forecast


def test_features_do_not_use_the_current_price(random_walk):
    """Changing the price on day t must not change any feature on day t (no leakage)."""
    a = engineer_features(random_walk.copy())
    shocked = random_walk.copy()
    shocked.loc[300, "value_mru"] *= 1.5
    b = engineer_features(shocked)
    pd.testing.assert_frame_equal(a.loc[300, FEATURE_COLUMNS].to_frame(), b.loc[300, FEATURE_COLUMNS].to_frame())
    assert not np.allclose(a.loc[301, FEATURE_COLUMNS].astype(float), b.loc[301, FEATURE_COLUMNS].astype(float))


def test_evaluate_reports_naive_baseline(random_walk):
    m = evaluate(random_walk)
    assert m["mae"] > 0 and m["mae_naive"] > 0
    assert abs(m["skill"] - (1 - m["mae"] / m["mae_naive"])) < 1e-12
    # on a pure random walk nothing should beat "tomorrow = today" by much
    assert m["skill"] < 0.05
    assert 0.3 < m["direction_accuracy"] < 0.7


def test_forecast_compounds_positive_prices(random_walk):
    model, importances = fit(random_walk)
    fc = forecast(model, random_walk, days_ahead=30)
    assert len(fc) == 30 and (fc["predicted_price"] > 0).all()
    assert fc["date"].iloc[0] == "2025-02-04"
    assert set(importances.index) == set(FEATURE_COLUMNS)
