import pandas as pd
import pytest

from scraper import build_rows, rate_on, to_mru

RATES = pd.Series({pd.Timestamp("2026-03-02"): 39.70, pd.Timestamp("2026-03-03"): 39.80})


@pytest.mark.parametrize("code,quote,expected", [
    ("USD", 39.7, 39.7),
    ("EUR", 1.10, 1.10 * 39.7),          # EUR/USD × MRU/USD
    ("CNY", 7.10, 39.7 / 7.10),          # CNY=X is CNY per USD → divide
    ("BTC", 90_000, 90_000 * 39.7),
    ("GOLD", 2_000, 2_000 * 39.7),
])
def test_to_mru(code, quote, expected):
    assert to_mru(code, quote, 39.7) == pytest.approx(expected)


def test_cny_regression_value_is_mru_per_yuan():
    # the v1 scraper stored the raw quote (~7.1, yuan per dollar) as the MRU price
    assert 5 < to_mru("CNY", 7.1, 39.7) < 6


def test_rate_carries_forward_over_weekend():
    assert rate_on(RATES, "2026-03-03") == 39.80
    assert rate_on(RATES, "2026-03-08") == 39.80          # Sunday → last published rate
    with pytest.raises(ValueError):
        rate_on(RATES, "2026-03-01")


def test_build_rows_skips_days_before_first_rate():
    quotes = pd.Series({pd.Timestamp("2026-03-01"): 1.1, pd.Timestamp("2026-03-04"): 1.2})
    rows = list(build_rows("EUR", quotes, RATES))
    assert rows == [(pd.Timestamp("2026-03-04").date(), round(1.2 * 39.80, 4), "Yahoo Finance")]
