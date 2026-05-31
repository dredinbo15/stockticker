"""
XGBoost modeling module pulling data from Neo4j.

Feature window: 31-90 days ago (news sentiment and counts)
Label window: 0-30 days ago (insider buy > sell signal)

Using a lagged feature window ensures the model is strictly forward-looking:
no feature data overlaps with the label period, so the model cannot
"cheat" by reading news that reports on the very insider trades it is
predicting.
"""

from __future__ import annotations

import logging

from config.database import get_neo4j_session
from config.tickers import SYMBOL_CIK_MAP

logger = logging.getLogger(__name__)

try:
    import pandas as pad
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import OrdinalEncoder
    from xgboost import XGBClassifier
except ModuleNotFoundError as exc:
    pd = None
    accuracy_score = None
    classification_report = None
    train_test_split = None
    OrdinalEncoder = None
    XGBClassifier = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class XGBoostModel:
    def __init__(self):
        self.model = None
        self.feature_df = pd.DataFrame() if pd is not None else None
        self.metrics = {}
        self.sector_encoder = (
            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
            if OrdinalEncoder is not None
            else None
        )

    def _dependencies_ready(self) -> bool:
        if _IMPORT_ERROR is None:
            return True

        self.metrics = {
            "error": (
                "XGBoost modeling dependencies are not installed. "
                "Install pandas, scikit-learn, and xgboost."
            )
        }
        logger.warning("XGBoostModel dependency import failed: %s", _IMPORT_ERROR)
        return False

    def _empty_frame(self):
        if pd is None:
            return None
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def fetch_stock_news_features(self) -> pad.DataFrame:
        """Return per-stock news features drawn from the 31-90 day window."""
        if not self._dependencies_ready():
            return self._empty_frame()

        with get_neo4j_session() as session:
            query = """
            MATCH (s:Stock)
            OPTIONAL MATCH (n:NewsArticle)-[:MENTIONS]->(s)
            WHERE n IS NULL
               OR (
                    n.published_date IS NOT NULL
                AND datetime(n.published_date) >= datetime() - duration({days:90})
                AND datetime(n.published_date) <  datetime() - duration({days:30})
               )
            WITH s.symbol AS symbol, s.name AS name, s.sector AS sector,
                 count(n) AS news_count,
                 avg(
                   CASE n.sentiment
                     WHEN 'positive' THEN 1
                     WHEN 'negative' THEN -1
                     ELSE 0
                   END
                 ) AS avg_sentiment
            RETURN symbol, name, sector,
                   news_count,
                   coalesce(avg_sentiment, 0.0) AS avg_sentiment
            """
            result = session.run(query)
            rows = [record.data() for record in result]

        if not rows:
            return pad.DataFrame()

        df = pd.DataFrame(rows)
        df["avg_sentiment"] = df["avg_sentiment"].astype(float)
        return df

    def fetch_insider_labels(self, df: pad.DataFrame) -> pad.Series:
        """Return a binary buy-signal for each stock based on the last 30 days."""
        if not self._dependencies_ready():
            return None

        symbols = df["symbol"].tolist()
        valid_ciks = [SYMBOL_CIK_MAP[sym] for sym in symbols if sym in SYMBOL_CIK_MAP]

        cik_signals = {}
        if valid_ciks:
            with get_neo4j_session() as session:
                query = """
                UNWIND $ciks AS cik
                MATCH (c:Company {cik: cik})<-[:FOR_COMPANY]-(t:Transaction)
                WHERE datetime(t.date) >= datetime() - duration({days:30})
                WITH cik,
                     sum(CASE WHEN t.code = 'P' THEN 1 ELSE 0 END) AS buys,
                     sum(CASE WHEN t.code = 'S' THEN 1 ELSE 0 END) AS sells
                RETURN cik,
                       buys,
                       sells
                """
                result = session.run(query, ciks=valid_ciks)
                cik_signals = {
                    record["cik"]: (
                        1 if (record["buys"] or 0) > (record["sells"] or 0) else 0
                    )
                    for record in result
                }

        labels = [cik_signals.get(SYMBOL_CIK_MAP.get(sym), 0) for sym in symbols]
        return pd.Series(labels, name="insider_buy_signal", dtype=int)

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def build_feature_matrix(
        self, df: pad.DataFrame, *, fit: bool = False
    ) -> pad.DataFrame:
        """Convert raw rows into the numeric matrix expected by XGBoost."""
        if not self._dependencies_ready():
            return self._empty_frame()

        if df.empty:
            return df

        df = df.copy()
        sectors = df["sector"].fillna("unknown").to_numpy().reshape(-1, 1)
        if fit:
            df["sector_encoded"] = (
                self.sector_encoder.fit_transform(sectors).astype(int).flatten()
            )
        else:
            df["sector_encoded"] = (
                self.sector_encoder.transform(sectors).astype(int).flatten()
            )

        feature_columns = [
            "news_count",
            "avg_sentiment",
            "sector_encoded",
        ]
        return df[feature_columns]

    # ------------------------------------------------------------------
    # Training and evaluation
    # ------------------------------------------------------------------

    def train_model(self):
        if not self._dependencies_ready():
            return self.metrics

        self.feature_df = self.fetch_stock_news_features()
        if self.feature_df.empty:
            self.metrics = {"error": "No stock/news data available"}
            return self.metrics

        target = self.fetch_insider_labels(self.feature_df)
        features = self.build_feature_matrix(self.feature_df, fit=True)

        if features.empty or len(features) < 2:
            self.metrics = {"error": "Not enough data to train"}
            return self.metrics

        X_train, X_test, y_train, y_test = train_test_split(
            features,
            target,
            test_size=0.3,
            random_state=42,
            stratify=target if len(target.unique()) > 1 else None,
        )

        self.model = XGBClassifier(eval_metric="logloss")
        self.model.fit(X_train, y_train)

        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(
            y_test, y_pred, output_dict=True, zero_division=0
        )

        self.metrics = {
            "accuracy": round(float(accuracy), 4),
            "support": int(
                report["macro avg"]["support"]
                if "macro avg" in report
                else len(y_test)
            ),
            "classification_report": report,
        }
        return self.metrics

    # ------------------------------------------------------------------
    # Post-training utilities
    # ------------------------------------------------------------------

    def get_feature_importances(self) -> pad.DataFrame:
        if not self._dependencies_ready():
            return self._empty_frame()

        if self.model is None or self.feature_df is None:
            return pad.DataFrame()

        feature_names = ["news_count", "avg_sentiment", "sector_encoded"]
        importances = self.model.feature_importances_
        return (
            pad.DataFrame({"feature": feature_names, "importance": importances})
            .sort_values(by="importance", ascending=False)
            .reset_index(drop=True)
        )

    def predict_stock(self, symbol: str):
        """Predict the insider-buy signal for a single stock."""
        if not self._dependencies_ready():
            return None

        if self.model is None or self.feature_df is None or self.feature_df.empty:
            return None

        row = self.feature_df.loc[self.feature_df["symbol"] == symbol]
        if row.empty:
            return None

        features = self.build_feature_matrix(row, fit=False)
        return int(self.model.predict(features)[0])
