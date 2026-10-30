"""
XGBoost modeling module pulling data from Neo4j.

One row per (stock, trading day). Features are computed only from data
available at that day's close:

- Price: 1/5/20-day returns, 20-day volatility, volume vs 20-day average,
  distance from the 20-day moving average
- News: article count and mean sentiment over the prior 7 days
- Insider (Form 4): open-market buys and sells over the prior 30 days,
  dated by *filing* date (when the market learns of them)
- 8-K: number of filings over the prior 30 days
- Sector

Target: does the stock beat the cross-sectional median return over the next
HORIZON_DAYS trading days? Using the median keeps classes balanced and makes
the label market-neutral.

Train/test split is by date (last 20% of days held out) with a HORIZON_DAYS
gap so no training label overlaps the test period.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from config.database import get_neo4j_session
from config.tickers import SYMBOL_CIK_MAP, SYMBOL_SECTOR_MAP, normalize_cik

logger = logging.getLogger(__name__)

try:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
    from sklearn.preprocessing import OrdinalEncoder
    from xgboost import XGBClassifier
except ModuleNotFoundError as exc:
    joblib = np = pd = None
    accuracy_score = classification_report = roc_auc_score = None
    OrdinalEncoder = XGBClassifier = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

HORIZON_DAYS = 5
LOOKBACK_DAYS = 730
TEST_FRACTION = 0.2
MIN_TRAIN_ROWS = 200

FEATURE_COLUMNS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "volatility_20d",
    "volume_ratio_20d",
    "close_vs_ma20",
    "news_count_7d",
    "news_sentiment_7d",
    "insider_buys_30d",
    "insider_sells_30d",
    "eightk_count_30d",
    "sector_encoded",
]

DEFAULT_MODEL_PATH = os.getenv("MODEL_PATH", os.path.join("artifacts", "xgb_model.joblib"))


# ----------------------------------------------------------------------
# Pure feature engineering (no database access; unit-testable)
# ----------------------------------------------------------------------

def price_features(prices: "pd.DataFrame", horizon: int = HORIZON_DAYS) -> "pd.DataFrame":
    """Per-symbol price features plus the forward return used for labels."""
    df = prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    grouped = df.groupby("symbol", group_keys=False)

    close = df["close"]
    df["ret_1d"] = grouped["close"].pct_change(1, fill_method=None)
    df["ret_5d"] = grouped["close"].pct_change(5, fill_method=None)
    df["ret_20d"] = grouped["close"].pct_change(20, fill_method=None)
    df["volatility_20d"] = df.groupby("symbol")["ret_1d"].transform(lambda s: s.rolling(20).std())
    ma20 = grouped["close"].transform(lambda s: s.rolling(20).mean())
    df["close_vs_ma20"] = close / ma20 - 1
    vol_ma20 = grouped["volume"].transform(lambda s: s.rolling(20).mean())
    df["volume_ratio_20d"] = (df["volume"] / vol_ma20.replace(0, np.nan)).fillna(1.0)
    df["fwd_return"] = grouped["close"].shift(-horizon) / close - 1
    return df


def rolling_event_features(panel: "pd.DataFrame", events: "pd.DataFrame",
                           value_cols: list, window_days: int) -> "pd.DataFrame":
    """Sum `value_cols` over events in the `window_days` calendar days up to each panel date.

    panel: symbol, date. events: symbol, date, *value_cols.
    Returns panel[symbol, date] with one column per value_col.
    """
    out = panel[["symbol", "date"]].copy()
    if events is None or events.empty:
        for col in value_cols:
            out[col] = 0.0
        return out

    events = events.copy()
    events["date"] = pd.to_datetime(events["date"]).dt.normalize()
    daily = events.groupby(["symbol", "date"])[value_cols].sum()
    end = out["date"].max()

    rolled_parts = []
    for symbol, frame in daily.groupby(level="symbol"):
        frame = frame.droplevel("symbol")
        index = pd.date_range(min(frame.index.min(), out["date"].min()), max(frame.index.max(), end), freq="D")
        frame = frame.reindex(index, fill_value=0)
        rolled = frame.rolling(f"{window_days}D").sum()
        rolled.index.name = "date"
        rolled = rolled.reset_index()
        rolled["symbol"] = symbol
        rolled_parts.append(rolled)

    rolled = pd.concat(rolled_parts, ignore_index=True)
    out = out.merge(rolled, on=["symbol", "date"], how="left")
    out[value_cols] = out[value_cols].fillna(0.0)
    return out


def build_dataset(prices, news=None, insider=None, eightk=None, horizon: int = HORIZON_DAYS):
    """Assemble the (symbol, date) panel with features and label.

    prices:  symbol, date, close, volume
    news:    symbol, date, sentiment ('positive'|'negative'|'neutral')
    insider: symbol, date (filing date), code ('P' buy, 'S' sale, ...)
    eightk:  symbol, date (filing date)

    Events are shifted forward one day so that anything published on day t
    only affects features from day t+1, avoiding intraday look-ahead.
    """
    panel = price_features(prices, horizon=horizon)

    def shifted(frame):
        if frame is None or frame.empty:
            return None
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=True, format="ISO8601").dt.tz_localize(None).dt.normalize() + np.timedelta64(1, "D")
        return frame

    news = shifted(news)
    if news is not None:
        news["news_count_7d"] = 1.0
        news["sentiment_sum"] = news["sentiment"].map({"positive": 1.0, "negative": -1.0}).fillna(0.0)
    news_feats = rolling_event_features(panel, news, ["news_count_7d", "sentiment_sum"], 7)
    panel["news_count_7d"] = news_feats["news_count_7d"].to_numpy()
    panel["news_sentiment_7d"] = np.where(
        panel["news_count_7d"] > 0,
        news_feats["sentiment_sum"].to_numpy() / panel["news_count_7d"].replace(0, 1).to_numpy(),
        0.0,
    )

    insider = shifted(insider)
    if insider is not None:
        insider["insider_buys_30d"] = (insider["code"] == "P").astype(float)
        insider["insider_sells_30d"] = (insider["code"] == "S").astype(float)
    insider_feats = rolling_event_features(panel, insider, ["insider_buys_30d", "insider_sells_30d"], 30)
    panel["insider_buys_30d"] = insider_feats["insider_buys_30d"].to_numpy()
    panel["insider_sells_30d"] = insider_feats["insider_sells_30d"].to_numpy()

    eightk = shifted(eightk)
    if eightk is not None:
        eightk["eightk_count_30d"] = 1.0
    eightk_feats = rolling_event_features(panel, eightk, ["eightk_count_30d"], 30)
    panel["eightk_count_30d"] = eightk_feats["eightk_count_30d"].to_numpy()

    panel["sector"] = panel["symbol"].map(SYMBOL_SECTOR_MAP).fillna("unknown")

    median_fwd = panel.groupby("date")["fwd_return"].transform("median")
    panel["label"] = np.where(panel["fwd_return"].notna(), (panel["fwd_return"] > median_fwd).astype(float), np.nan)

    # Rows need the full 20-day price history to have valid features.
    panel = panel.dropna(subset=["ret_20d", "volatility_20d", "close_vs_ma20"])
    return panel.reset_index(drop=True)


def time_split(dataset, test_fraction: float = TEST_FRACTION, gap: int = HORIZON_DAYS):
    """Split labelled rows by date: train | gap | test."""
    labelled = dataset.dropna(subset=["label"])
    dates = np.sort(labelled["date"].unique())
    if len(dates) < gap + 2:
        return labelled.iloc[0:0], labelled.iloc[0:0]
    n_test = max(1, int(len(dates) * test_fraction))
    test_dates = dates[-n_test:]
    train_dates = dates[: max(0, len(dates) - n_test - gap)]
    train = labelled[labelled["date"].isin(train_dates)]
    test = labelled[labelled["date"].isin(test_dates)]
    return train, test


# ----------------------------------------------------------------------
# Model wrapper
# ----------------------------------------------------------------------

class XGBoostModel:
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, autoload: bool = True):
        self.model_path = model_path
        self._loaded_mtime = None
        self.model = None
        self.metrics = {}
        self.feature_df = pd.DataFrame() if pd is not None else None
        self.sector_encoder = (
            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
            if OrdinalEncoder is not None
            else None
        )
        if autoload and _IMPORT_ERROR is None:
            self.load()

    def _dependencies_ready(self) -> bool:
        if _IMPORT_ERROR is None:
            return True
        self.metrics = {
            "error": (
                "XGBoost modeling dependencies are not installed. "
                "Install pandas, scikit-learn, joblib, and xgboost."
            )
        }
        logger.warning("XGBoostModel dependency import failed: %s", _IMPORT_ERROR)
        return False

    # -- data fetching ---------------------------------------------------

    def fetch_training_data(self, lookback_days: int = LOOKBACK_DAYS):
        from models.price import PricePoint

        since_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        since = since_dt.strftime("%Y-%m-%d")
        prices = pd.DataFrame(PricePoint.get_history(symbols=list(SYMBOL_CIK_MAP), since=since))

        cik_to_symbol = {cik: sym for sym, cik in SYMBOL_CIK_MAP.items()}
        with get_neo4j_session() as session:
            news = pd.DataFrame([r.data() for r in session.run(
                """
                MATCH (n:NewsArticle)-[:MENTIONS]->(s:Stock)
                WHERE n.published_date >= $since
                RETURN s.symbol AS symbol, n.published_date AS date, n.sentiment AS sentiment
                """, since=since)])
            insider = pd.DataFrame([r.data() for r in session.run(
                """
                MATCH (t:Transaction)-[:FOR_COMPANY]->(c:Company)
                WHERE c.cik IN $ciks AND t.date >= $since
                RETURN c.cik AS cik, t.date AS trade_date, t.filing_date AS filing_date, t.code AS code
                """, ciks=list(cik_to_symbol), since=since)])
            eightk = pd.DataFrame([r.data() for r in session.run(
                """
                MATCH (r:EightKReport)-[:ABOUT_COMPANY]->(c:Company)
                WHERE c.cik IN $ciks AND r.filing_date >= $since
                RETURN c.cik AS cik, r.filing_date AS date
                """, ciks=list(cik_to_symbol), since=since)])

        if not insider.empty:
            insider["symbol"] = insider["cik"].map(lambda c: cik_to_symbol.get(normalize_cik(c)))
            # Older rows lack filing_date; Form 4 is due within 2 business days.
            trade = pd.to_datetime(insider["trade_date"], utc=True, format="ISO8601")
            filed = pd.to_datetime(insider["filing_date"], utc=True, format="ISO8601")
            insider["date"] = filed.fillna(trade + np.timedelta64(4, "D")).dt.strftime("%Y-%m-%d")
            insider = insider.dropna(subset=["symbol"])[["symbol", "date", "code"]]
        if not eightk.empty:
            eightk["symbol"] = eightk["cik"].map(lambda c: cik_to_symbol.get(normalize_cik(c)))
            eightk = eightk.dropna(subset=["symbol"])[["symbol", "date"]]

        return prices, news, insider, eightk

    # -- training --------------------------------------------------------

    def _matrix(self, df, fit: bool = False):
        sectors = df[["sector"]].to_numpy()
        encoded = self.sector_encoder.fit_transform(sectors) if fit else self.sector_encoder.transform(sectors)
        X = df.copy()
        X["sector_encoded"] = encoded.astype(int).flatten()
        return X[FEATURE_COLUMNS].astype(float)

    def train_on_dataset(self, dataset):
        train, test = time_split(dataset)
        if len(train) < MIN_TRAIN_ROWS or test.empty or train["label"].nunique() < 2:
            self.metrics = {
                "error": (
                    f"Not enough price history to train (have {len(train)} training rows, "
                    f"need {MIN_TRAIN_ROWS}). Backfill with POST /api/collect/prices?period=2y."
                )
            }
            return self.metrics

        X_train = self._matrix(train, fit=True)
        X_test = self._matrix(test)
        y_train = train["label"].astype(int)
        y_test = test["label"].astype(int)

        self.model = XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
        )
        self.model.fit(X_train, y_train)

        proba = self.model.predict_proba(X_test)[:, 1]
        y_pred = (proba >= 0.5).astype(int)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        majority = int(y_train.mode()[0])

        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, proba)), 4) if y_test.nunique() > 1 else None,
            "baseline_accuracy": round(float((y_test == majority).mean()), 4),
            "horizon_days": HORIZON_DAYS,
            "target": f"beats cross-sectional median {HORIZON_DAYS}-day forward return",
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_period": [str(train["date"].min().date()), str(train["date"].max().date())],
            "test_period": [str(test["date"].min().date()), str(test["date"].max().date())],
            "n_symbols": int(dataset["symbol"].nunique()),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "classification_report": report,
        }

        # Latest row per symbol = what we predict from today.
        latest_idx = dataset.groupby("symbol")["date"].idxmax()
        self.feature_df = dataset.loc[latest_idx].reset_index(drop=True)
        return self.metrics

    def train_model(self):
        if not self._dependencies_ready():
            return self.metrics
        prices, news, insider, eightk = self.fetch_training_data()
        if prices.empty:
            self.metrics = {"error": "No price history available. Run POST /api/collect/prices?period=2y first."}
            return self.metrics
        dataset = build_dataset(prices, news, insider, eightk)
        metrics = self.train_on_dataset(dataset)
        if self.model is not None and "error" not in metrics:
            self.save()
        return metrics

    # -- persistence -----------------------------------------------------

    def save(self):
        directory = os.path.dirname(self.model_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "sector_encoder": self.sector_encoder,
                "metrics": self.metrics,
                "feature_df": self.feature_df,
                "feature_columns": FEATURE_COLUMNS,
            },
            self.model_path,
        )
        self._loaded_mtime = os.path.getmtime(self.model_path)
        logger.info("Saved XGBoost model to %s", self.model_path)

    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            return False
        try:
            state = joblib.load(self.model_path)
        except Exception as exc:
            logger.warning("Could not load model from %s: %s", self.model_path, exc)
            return False
        if state.get("feature_columns") != FEATURE_COLUMNS:
            logger.warning("Saved model uses different features; retrain required.")
            return False
        self.model = state["model"]
        self.sector_encoder = state["sector_encoder"]
        self.metrics = state["metrics"]
        self.feature_df = state["feature_df"]
        self._loaded_mtime = os.path.getmtime(self.model_path)
        return True

    def reload_if_changed(self) -> bool:
        """Pick up a model saved by another process (e.g. the Celery worker)."""
        if _IMPORT_ERROR is not None or not os.path.exists(self.model_path):
            return False
        if os.path.getmtime(self.model_path) == self._loaded_mtime:
            return False
        return self.load()

    # -- post-training utilities ----------------------------------------

    def get_feature_importances(self):
        if not self._dependencies_ready() or self.model is None:
            return pd.DataFrame() if pd is not None else None
        return (
            pd.DataFrame({"feature": FEATURE_COLUMNS, "importance": self.model.feature_importances_})
            .sort_values(by="importance", ascending=False)
            .reset_index(drop=True)
        )

    def predict_all(self):
        """Probability each stock beats the median over the next HORIZON_DAYS."""
        if not self._dependencies_ready() or self.model is None or self.feature_df is None or self.feature_df.empty:
            return pd.DataFrame() if pd is not None else None
        proba = self.model.predict_proba(self._matrix(self.feature_df))[:, 1]
        return (
            pd.DataFrame({
                "symbol": self.feature_df["symbol"],
                "as_of": self.feature_df["date"].dt.strftime("%Y-%m-%d"),
                "probability": np.round(proba, 4),
                "signal": (proba >= 0.5).astype(int),
            })
            .sort_values("probability", ascending=False)
            .reset_index(drop=True)
        )

    def predict_stock(self, symbol: str):
        """Return {symbol, as_of, probability, signal} or None if unknown."""
        predictions = self.predict_all()
        if predictions is None or predictions.empty:
            return None
        row = predictions.loc[predictions["symbol"] == symbol]
        if row.empty:
            return None
        record = row.iloc[0]
        return {
            "symbol": symbol,
            "as_of": record["as_of"],
            "probability": round(float(record["probability"]), 4),
            "signal": int(record["signal"]),
        }
