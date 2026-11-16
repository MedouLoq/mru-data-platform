"""Price forecasting for MRU-denominated assets.

Design (v2):
  * Target = next-day log-return, not the price level. Tree ensembles cannot
    extrapolate beyond the price range seen in training, so a level model
    breaks on trending assets (BTC, gold). Returns are stationary-ish.
  * Features are scale-free: lagged returns, price / moving-average ratios,
    rolling volatility, calendar. Every feature only uses data up to t-1.
  * Every model is benchmarked against the naive persistence forecast
    ("tomorrow = today"), which is very hard to beat for prices. The headline
    metric is skill = 1 - MAE_model / MAE_naive (positive = better than naive).
  * Multi-day forecasts compound predicted returns day by day.
"""
import os
import warnings
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore")

def models_dir() -> str:
    return os.getenv("MODELS_DIR", "models")

FEATURE_COLUMNS = [
    "ret_1", "ret_2", "ret_3", "ret_5", "ret_7", "ret_14", "ret_30",
    "ratio_ma_7", "ratio_ma_30", "ratio_ma_90", "ratio_ema_7", "ratio_ema_30",
    "vol_7", "vol_30", "range_30",
    "day_of_week", "month", "is_month_end",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add scale-free features. Row t only uses prices up to t-1 (no leakage)."""
    df = df.sort_values("date").reset_index(drop=True)
    p = df["value_mru"].astype(float)
    prev = p.shift(1)
    logp = np.log(p)
    r = logp.diff()                                   # log-return at t (target)
    df["target"] = r
    for k in (1, 2, 3, 5, 7, 14, 30):                  # cumulative return ending at t-1
        df[f"ret_{k}"] = np.log(prev / p.shift(1 + k))
    for w in (7, 30, 90):
        df[f"ratio_ma_{w}"] = prev / prev.rolling(w, min_periods=max(3, w // 3)).mean() - 1
    for s in (7, 30):
        df[f"ratio_ema_{s}"] = prev / prev.ewm(span=s, adjust=False).mean() - 1
    r_prev = r.shift(1)
    df["vol_7"] = r_prev.rolling(7, min_periods=5).std()
    df["vol_30"] = r_prev.rolling(30, min_periods=15).std()
    df["range_30"] = (prev.rolling(30, min_periods=15).max() - prev.rolling(30, min_periods=15).min()) / prev
    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_month_end"] = df["date"].dt.is_month_end.astype(int)
    df["prev_price"] = prev
    return df


def make_model():
    return GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.03,
                                     subsample=0.8, min_samples_leaf=20, loss="huber", random_state=42)


def evaluate(df: pd.DataFrame, n_splits: int = 5) -> dict:
    """Walk-forward CV of 1-day-ahead price forecasts: model vs naive persistence."""
    feat = engineer_features(df).dropna(subset=FEATURE_COLUMNS + ["target", "prev_price"])
    X, y = feat[FEATURE_COLUMNS], feat["target"]
    price, prev = feat["value_mru"].astype(float).values, feat["prev_price"].values
    mae_m, mae_n, rmse_m, rmse_n, hit = [], [], [], [], []
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(X):
        model = make_model().fit(X.iloc[tr], y.iloc[tr])
        pred_price = prev[va] * np.exp(model.predict(X.iloc[va]))
        mae_m.append(mean_absolute_error(price[va], pred_price))
        mae_n.append(mean_absolute_error(price[va], prev[va]))
        rmse_m.append(np.sqrt(mean_squared_error(price[va], pred_price)))
        rmse_n.append(np.sqrt(mean_squared_error(price[va], prev[va])))
        moved = y.iloc[va].values != 0
        hit.append(np.mean(np.sign(model.predict(X.iloc[va]))[moved] == np.sign(y.iloc[va].values[moved])) if moved.any() else np.nan)
    mae, mae_naive = float(np.mean(mae_m)), float(np.mean(mae_n))
    last = float(df.sort_values("date")["value_mru"].iloc[-1])
    return {
        "n_samples": int(len(feat)),
        "mae": mae, "mae_naive": mae_naive,
        "rmse": float(np.mean(rmse_m)), "rmse_naive": float(np.mean(rmse_n)),
        "mape": 100 * mae / last, "mape_naive": 100 * mae_naive / last,
        "skill": 1 - mae / mae_naive if mae_naive else 0.0,
        "direction_accuracy": float(np.nanmean(hit)),
    }


def fit(df: pd.DataFrame):
    feat = engineer_features(df).dropna(subset=FEATURE_COLUMNS + ["target"])
    model = make_model().fit(feat[FEATURE_COLUMNS], feat["target"])
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    return model, importances


def forecast(model, df: pd.DataFrame, days_ahead: int = 30) -> pd.DataFrame:
    """Compound predicted daily returns, re-deriving features from the extended series."""
    base = df[["date", "value_mru"]].copy()
    base["value_mru"] = base["value_mru"].astype(float)
    out = []
    for _ in range(days_ahead):
        nxt = base["date"].max() + timedelta(days=1)
        tmp = pd.concat([base, pd.DataFrame({"date": [nxt], "value_mru": [np.nan]})], ignore_index=True)
        row = engineer_features(tmp).tail(1)
        price = float(row["prev_price"].iloc[0]) * float(np.exp(model.predict(row[FEATURE_COLUMNS])[0]))
        out.append({"date": nxt.strftime("%Y-%m-%d"), "predicted_price": round(price, 4)})
        base = pd.concat([base, pd.DataFrame({"date": [nxt], "value_mru": [price]})], ignore_index=True)
    return pd.DataFrame(out)


# ─────────────────────────── database + orchestration ───────────────────────────
def get_connection():
    import psycopg2
    return psycopg2.connect(dbname=os.getenv("DB_NAME", "currency_db"), user=os.getenv("DB_USER", "postgres"),
                            password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST", "db"),
                            port=os.getenv("DB_PORT", "5432"))


def fetch_asset_data(asset_code: str) -> pd.DataFrame:
    """Prices for one asset, from Django's ORM when available (any DB backend), else psycopg2."""
    try:
        from app.models import Price
        rows = Price.objects.filter(asset__code=asset_code).order_by("date").values_list("date", "value_mru")
        df = pd.DataFrame(list(rows), columns=["date", "value_mru"])
    except Exception:
        conn = get_connection()
        df = pd.read_sql("""SELECT p.date, p.value_mru FROM app_price p JOIN app_asset a ON p.asset_id = a.id
                            WHERE a.code = %s ORDER BY p.date""", conn, params=(asset_code,))
        conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["value_mru"] = df["value_mru"].astype(float)
    return df


def train_asset_model(asset_code: str, df: pd.DataFrame = None):
    df = fetch_asset_data(asset_code) if df is None else df
    if len(df) < 120:
        return None
    metrics = evaluate(df)
    model, importances = fit(df)
    os.makedirs(models_dir(), exist_ok=True)
    joblib.dump(model, os.path.join(models_dir(), f"{asset_code}_model.joblib"))
    last = df.sort_values("date").iloc[-1]
    metadata = {
        "asset_code": asset_code, "model_version": 2, "trained_at": datetime.now().isoformat(timespec="seconds"),
        "target": "next-day log-return", "features": FEATURE_COLUMNS, **metrics,
        "feature_importances": {k: float(v) for k, v in importances.items()},
        "last_known_date": last["date"].strftime("%Y-%m-%d"), "last_known_price": float(last["value_mru"]),
    }
    joblib.dump(metadata, os.path.join(models_dir(), f"{asset_code}_metadata.joblib"))
    return metadata


def predict_future(asset_code: str, days_ahead: int = 30):
    path = os.path.join(models_dir(), f"{asset_code}_model.joblib")
    if not os.path.exists(path):
        return None
    return forecast(joblib.load(path), fetch_asset_data(asset_code), days_ahead)


try:
    from prefect import flow, task, get_run_logger

    train_asset_task = task(train_asset_model, name="Train asset model")

    @flow(name="ML Training Pipeline")
    def training_flow():
        logger = get_run_logger()
        conn = get_connection()
        codes = pd.read_sql("SELECT code FROM app_asset", conn)["code"].tolist()
        conn.close()
        results = {}
        for code in codes:
            meta = train_asset_task(code)
            if meta:
                results[code] = meta
                logger.info("%s: MAE %.4f vs naive %.4f (skill %+.1f%%)", code, meta["mae"], meta["mae_naive"], 100 * meta["skill"])
        return results
except ImportError:  # Prefect is optional for local use
    def training_flow():
        raise RuntimeError("Install prefect to run the orchestrated training flow")


if __name__ == "__main__":
    training_flow()
