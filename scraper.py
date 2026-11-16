"""Daily data acquisition: official MRU rates (BCM) + market prices (Yahoo Finance).

Every price is stored in MRU (Mauritanian ouguiya):
  * USD   : official BCM reference rate (MRU per USD)
  * EUR   : EUR/USD cross rate × MRU per USD
  * CNY   : Yahoo "CNY=X" is CNY per USD, so MRU per CNY = MRU per USD ÷ quote
  * BTC, gold, iron ore, copper : USD prices × MRU per USD
"""
import logging
import os
from datetime import date

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BCM_URL = "https://connect.bcm.mr/api/cours_change_reference"
HISTORY_START = os.getenv("HISTORY_START", "2024-01-01")

ASSETS = [
    {"code": "BTC", "name": "Bitcoin", "cat": "currency", "ticker": "BTC-USD"},
    {"code": "EUR", "name": "Euro", "cat": "currency", "ticker": "EURUSD=X"},
    {"code": "CNY", "name": "Chinese Yuan", "cat": "currency", "ticker": "CNY=X"},
    {"code": "GOLD", "name": "Gold (troy oz)", "cat": "commodity", "ticker": "GC=F"},
    {"code": "IRON", "name": "Iron Ore (tonne)", "cat": "commodity", "ticker": "TIO=F"},
    {"code": "COPPER", "name": "Copper (lb)", "cat": "commodity", "ticker": "HG=F"},
    {"code": "USD", "name": "US Dollar", "cat": "currency", "ticker": None},
]


def to_mru(asset_code: str, quote: float, mru_per_usd: float) -> float:
    """Convert a Yahoo quote to MRU, given the BCM MRU/USD rate for that day."""
    if asset_code == "USD":
        return quote
    if asset_code == "CNY":
        return mru_per_usd / quote          # quote = CNY per USD
    return quote * mru_per_usd              # EUR/USD, BTC, commodities: USD prices


def rate_on(rates: pd.Series, day) -> float:
    """BCM rate for `day`, carrying the last published rate forward (weekends, holidays)."""
    known = rates[rates.index <= pd.Timestamp(day)]
    if known.empty:
        raise ValueError(f"No BCM rate on or before {day}")
    return float(known.iloc[-1])


def fetch_bcm_rates(start: str = HISTORY_START, end: str = None) -> pd.Series:
    """MRU per USD by date, from the Central Bank of Mauritania's public API."""
    end = end or date.today().isoformat()
    resp = requests.get(BCM_URL, params={"from": start, "to": end, "currency": "*"}, timeout=30)
    resp.raise_for_status()
    rates = {entry["date"]: float(entry["value"]) / float(entry.get("weight") or 1)
             for entry in resp.json() if entry.get("currency") == "USD"}
    series = pd.Series(rates, dtype=float)
    series.index = pd.to_datetime(series.index)
    logger.info("BCM: %d daily USD rates (%s → %s)", len(series), series.index.min().date(), series.index.max().date())
    return series.sort_index()


def fetch_quotes(ticker: str) -> pd.Series:
    import yfinance as yf
    df = yf.download(ticker, start=HISTORY_START, interval="1d", progress=False, auto_adjust=False)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # newer yfinance returns a column per ticker
        close = close.iloc[:, 0]
    return close.dropna()


def build_rows(asset_code: str, quotes: pd.Series, rates: pd.Series):
    source = "BCM" if asset_code == "USD" else "Yahoo Finance"
    for ts, quote in quotes.items():
        try:
            yield ts.date(), round(to_mru(asset_code, float(quote), rate_on(rates, ts)), 4), source
        except ValueError:
            continue  # before the first BCM rate


def save_prices(asset: dict, rows, conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM app_asset WHERE code = %s", (asset["code"],))
        found = cur.fetchone()
        if found:
            asset_id = found[0]
        else:
            cur.execute("INSERT INTO app_asset (code, name, category) VALUES (%s, %s, %s) RETURNING id",
                        (asset["code"], asset["name"], asset["cat"]))
            asset_id = cur.fetchone()[0]
        n = 0
        for day, value, source in rows:
            cur.execute("""INSERT INTO app_price (date, value_mru, asset_id, source) VALUES (%s, %s, %s, %s)
                           ON CONFLICT (asset_id, date) DO UPDATE SET value_mru = EXCLUDED.value_mru,
                                                                       source = EXCLUDED.source""",
                        (day, value, asset_id, source))
            n += 1
    conn.commit()
    logger.info("%s: %d prices saved", asset["code"], n)
    return n


def get_db_connection():
    import psycopg2
    return psycopg2.connect(dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                            host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"))


def run():
    rates = fetch_bcm_rates()
    conn = get_db_connection()
    try:
        for asset in ASSETS:
            quotes = rates if asset["ticker"] is None else fetch_quotes(asset["ticker"])
            save_prices(asset, build_rows(asset["code"], quotes, rates), conn)
    finally:
        conn.close()


try:
    from prefect import flow, task

    fetch_bcm_rates = task(fetch_bcm_rates, retries=3, retry_delay_seconds=60, name="Fetch BCM Rates")
    fetch_quotes = task(fetch_quotes, retries=3, retry_delay_seconds=60, name="Fetch Yahoo quotes")

    @flow(name="MRU Data Acquisition Pipeline")
    def scraper_flow():
        run()
except ImportError:
    scraper_flow = run


if __name__ == "__main__":
    scraper_flow()
