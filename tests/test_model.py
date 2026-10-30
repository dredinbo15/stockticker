import numpy as np
import pandas as pd
import pytest

from modules.modeling import xgboost_model as xm


def synthetic_prices(n_days=260, symbols=("AAPL", "MSFT", "XOM", "JPM", "KO", "PFE", "CAT", "NEE"), seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for sym in symbols:
        close = 100.0
        for date in dates:
            close *= 1 + rng.normal(0, 0.015)
            rows.append({"symbol": sym, "date": date.strftime("%Y-%m-%d"), "close": close,
                         "volume": int(rng.integers(1_000_000, 2_000_000))})
    return pd.DataFrame(rows)


def test_rolling_event_features_window_and_carry():
    panel = pd.DataFrame({"symbol": ["A"] * 4, "date": pd.to_datetime(["2026-01-01", "2026-01-05", "2026-01-08", "2026-01-20"])})
    events = pd.DataFrame({"symbol": ["A", "A"], "date": ["2026-01-02", "2026-01-05"], "n": [1.0, 1.0]})
    out = xm.rolling_event_features(panel, events, ["n"], window_days=7)
    # 01-01: none yet; 01-05: both; 01-08: 01-02 is 6 days back -> both; 01-20: expired.
    assert out["n"].tolist() == [0.0, 2.0, 2.0, 0.0]


def test_build_dataset_features_and_labels():
    prices = synthetic_prices()
    news = pd.DataFrame({"symbol": ["AAPL", "AAPL"], "date": ["2026-01-05T15:00:00+00:00", "2026-01-06T09:00:00+00:00"],
                         "sentiment": ["positive", "negative"]})
    insider = pd.DataFrame({"symbol": ["MSFT", "MSFT"], "date": ["2026-01-05", "2026-01-05"], "code": ["P", "S"]})
    eightk = pd.DataFrame({"symbol": ["XOM"], "date": ["2026-01-05"]})

    ds = xm.build_dataset(prices, news, insider, eightk)
    assert set(xm.FEATURE_COLUMNS) - {"sector_encoded"} <= set(ds.columns)
    assert ds[[c for c in xm.FEATURE_COLUMNS if c != "sector_encoded"]].notna().all().all()

    aapl = ds[ds.symbol == "AAPL"].set_index("date")
    # Events are shifted a day: news from 01-05 is not visible on 01-05.
    assert aapl.loc["2026-01-05", "news_count_7d"] == 0
    assert aapl.loc["2026-01-06", "news_count_7d"] == 1
    assert aapl.loc["2026-01-07", "news_count_7d"] == 2
    assert aapl.loc["2026-01-07", "news_sentiment_7d"] == 0.0
    msft = ds[ds.symbol == "MSFT"].set_index("date")
    assert msft.loc["2026-01-06", "insider_buys_30d"] == 1
    assert msft.loc["2026-01-06", "insider_sells_30d"] == 1

    # Labels are balanced around the cross-sectional median; last HORIZON days unlabelled.
    labelled = ds.dropna(subset=["label"])
    assert 0.4 < labelled["label"].mean() < 0.6
    last_dates = sorted(ds["date"].unique())[-xm.HORIZON_DAYS:]
    assert ds[ds["date"].isin(last_dates)]["label"].isna().all()


def test_time_split_has_gap():
    ds = xm.build_dataset(synthetic_prices())
    train, test = xm.time_split(ds)
    labelled_dates = sorted(ds.dropna(subset=["label"])["date"].unique())
    gap_dates = [d for d in labelled_dates if train["date"].max() < d < test["date"].min()]
    assert len(gap_dates) == xm.HORIZON_DAYS
    assert train["date"].max() < test["date"].min()


def test_train_save_load_predict(tmp_path):
    path = tmp_path / "model.joblib"
    model = xm.XGBoostModel(model_path=str(path), autoload=False)
    metrics = model.train_on_dataset(xm.build_dataset(synthetic_prices()))
    assert "error" not in metrics, metrics
    assert 0 <= metrics["accuracy"] <= 1
    assert metrics["train_rows"] >= xm.MIN_TRAIN_ROWS
    model.save()

    loaded = xm.XGBoostModel(model_path=str(path))
    assert loaded.model is not None
    assert loaded.metrics["accuracy"] == metrics["accuracy"]
    pred = loaded.predict_stock("AAPL")
    assert pred["symbol"] == "AAPL" and 0 <= pred["probability"] <= 1 and pred["signal"] in (0, 1)
    assert loaded.predict_stock("ZZZZ") is None
    assert len(loaded.predict_all()) == 8
    assert list(loaded.get_feature_importances()["feature"].sort_values()) == sorted(xm.FEATURE_COLUMNS)
    assert loaded.reload_if_changed() is False


def test_train_reports_insufficient_history(tmp_path):
    model = xm.XGBoostModel(model_path=str(tmp_path / "m.joblib"), autoload=False)
    metrics = model.train_on_dataset(xm.build_dataset(synthetic_prices(n_days=40)))
    assert "Not enough price history" in metrics["error"]
    assert model.model is None


class FakeRecord:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeSession:
    """Answers the model's three Cypher queries with canned rows."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        if "NewsArticle" in query:
            rows = [{"symbol": "AAPL", "date": "2026-05-01T10:00:00+00:00", "sentiment": "positive"}]
        elif "Transaction" in query:
            rows = [
                {"cik": "0000789019", "trade_date": "2026-05-01T00:00:00+00:00", "filing_date": "2026-05-04T00:00:00+00:00", "code": "P"},
                {"cik": "789019", "trade_date": "2026-05-05T00:00:00+00:00", "filing_date": None, "code": "S"},
                {"cik": "999999", "trade_date": "2026-05-05T00:00:00+00:00", "filing_date": None, "code": "S"},
            ]
        elif "EightKReport" in query:
            rows = [{"cik": "34088", "date": "2026-05-02T00:00:00+00:00"}]
        else:
            raise AssertionError(query)
        return [FakeRecord(r) for r in rows]


def test_train_model_end_to_end_with_fake_db(monkeypatch, tmp_path):
    from models.price import PricePoint

    prices = synthetic_prices()
    monkeypatch.setattr(PricePoint, "get_history", staticmethod(lambda symbols=None, since=None: prices.to_dict("records")))
    monkeypatch.setattr(xm, "get_neo4j_session", lambda: FakeSession())

    model = xm.XGBoostModel(model_path=str(tmp_path / "m.joblib"), autoload=False)
    _, _, insider, eightk = model.fetch_training_data()
    # Padded and unpadded CIKs both map to MSFT; untracked CIKs are dropped.
    assert insider["symbol"].tolist() == ["MSFT", "MSFT"]
    # Missing filing date falls back to trade date + 4 days.
    assert insider["date"].tolist() == ["2026-05-04", "2026-05-09"]
    assert eightk["symbol"].tolist() == ["XOM"]

    metrics = model.train_model()
    assert "error" not in metrics, metrics
    assert (tmp_path / "m.joblib").exists()
