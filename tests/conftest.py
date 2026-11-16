import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def random_walk():
    """Synthetic geometric random walk: no real market data in the test suite."""
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates))))
    return pd.DataFrame({"date": dates, "value_mru": prices})
