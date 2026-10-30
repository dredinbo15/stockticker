import streamlit as st
from config.database import init_neo4j
from models.stock import Stock
from models.news import NewsArticle
from models.sec_form4 import SECForm4
from models.sec_8k import SEC8K
from modules.analysis.weather_correlation import WeatherCorrelationAnalyzer
from modules.modeling.xgboost_model import HORIZON_DAYS, XGBoostModel
from config.tickers import SYMBOL_CIK_MAP, SYMBOL_NAME_MAP, SYMBOL_SECTOR_MAP


def node_to_dict(node):
    try:
        return dict(node)
    except Exception:
        return {key: node[key] for key in node.keys()}


def load_stocks():
    return Stock.get_all_stocks(limit=200, skip=0)


def render_news_table(news_items):
    if not news_items:
        st.info("No news articles found for this stock.")
        return

    rows = []
    for node in news_items:
        article = node_to_dict(node)
        rows.append({
            "Title": article.get("title"),
            "Source": article.get("source"),
            "Published": article.get("published_date"),
            "Sentiment": article.get("sentiment"),
            "Related Stocks": ", ".join(article.get("related_stocks", [])),
            "URL": article.get("url"),
        })

    st.table(rows)


def render_transactions_table(transactions):
    if not transactions:
        st.info("No SEC Form 4 transactions found for this company CIK.")
        return

    rows = []
    for record in transactions:
        transaction = record.get("t") if isinstance(record, dict) and "t" in record else record
        if transaction is not None:
            row = {
                "Insider": record.get("insider"),
                "Date": transaction.get("date"),
                "Code": transaction.get("code"),
                "Shares": transaction.get("shares"),
                "Price": transaction.get("price"),
                "Security": transaction.get("security_title"),
                "Type": transaction.get("transaction_type"),
                "Ownership": transaction.get("ownership_nature"),
                "Form URL": transaction.get("form_url"),
            }
            rows.append(row)

    st.table(rows)


def render_8k_reports(reports):
    if not reports:
        st.info("No SEC 8-K reports found for this company CIK.")
        return

    rows = []
    for node in reports:
        report = node_to_dict(node)
        rows.append({
            "Filing Date": report.get("filing_date"),
            "Description": report.get("description"),
            "Item Summary": report.get("item_summary"),
            "LLM Summary": report.get("llm_summary"),
            "Impact": report.get("impact_assessment"),
            "Form URL": report.get("form_url"),
        })

    st.table(rows)


@st.cache_resource
def get_xgboost_model():
    # Loads the model saved by the API or the scheduled Celery job; only
    # trains here if nothing has been saved yet.
    model = XGBoostModel()
    if model.model is None:
        model.train_model()
    return model


def rerun_app():
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun is None:
        raise RuntimeError("Streamlit rerun API is unavailable. Upgrade to streamlit>=1.27.")
    rerun()


def main():
    st.set_page_config(page_title="StockTicker Dashboard", layout="wide")
    st.title("StockTicker Streamlit Dashboard")
    st.write("A simple dashboard for stocks, enriched news, SEC Form 4 activity, and XGBoost modeling.")

    try:
        init_neo4j()
    except Exception as exc:
        st.error(f"Could not connect to Neo4j: {exc}. Ensure the database is running and credentials are set.")
        st.stop()

    stocks = load_stocks()
    # Fall back to the static sector map for any node that lacks a sector.
    for stock in stocks:
        if not stock.get("sector"):
            stock["sector"] = SYMBOL_SECTOR_MAP.get(stock["symbol"], "Unknown")

    sidebar = st.sidebar
    sidebar.header("Filters")

    sectors = sorted({stock["sector"] for stock in stocks})
    selected_sector = sidebar.selectbox("Sector", ["All"] + sectors)
    filtered_stocks = (
        stocks
        if selected_sector == "All"
        else [s for s in stocks if s["sector"] == selected_sector]
    )

    symbols = [stock["symbol"] for stock in filtered_stocks]
    selected_stock = sidebar.selectbox("Select stock symbol", symbols)
    # Default the SEC company to the selected stock so the page stays in sync.
    cik_symbols = list(SYMBOL_CIK_MAP)
    default_index = cik_symbols.index(selected_stock) if selected_stock in cik_symbols else 0
    cik_symbol = sidebar.selectbox(
        "SEC company",
        cik_symbols,
        index=default_index,
        format_func=lambda sym: f"{sym} – {SYMBOL_NAME_MAP.get(sym, sym)} (CIK {SYMBOL_CIK_MAP[sym]})",
    )
    selected_cik = SYMBOL_CIK_MAP[cik_symbol]

    if selected_stock:
        selected_stock_data = next((s for s in stocks if s["symbol"] == selected_stock), None)
        if selected_stock_data and selected_stock_data.get("price") is not None:
            st.metric("Latest price", f"${selected_stock_data['price']:.2f}")

    st.subheader("Stocks by Sector")
    grouped = {}
    for stock in filtered_stocks:
        grouped.setdefault(stock["sector"], []).append(stock)
    if not grouped:
        st.info("No stocks found.")
    for sector in sorted(grouped):
        sector_stocks = sorted(grouped[sector], key=lambda s: s["symbol"])
        st.markdown(f"**{sector}** ({len(sector_stocks)})")
        st.table([
            {
                "Symbol": s["symbol"],
                "Name": s.get("name") or "—",
                "Price": f"${s['price']:.2f}" if s.get("price") is not None else "—",
                "Last Updated": s.get("price_timestamp") or "—",
            }
            for s in sector_stocks
        ])

    if selected_stock:
        st.subheader(f"News for {selected_stock}")
        news_items = NewsArticle.get_news_by_stock(selected_stock)
        render_news_table(news_items)

    st.subheader("Latest SEC Form 4 Transactions")
    transactions = SECForm4.get_transactions_by_company(selected_cik)
    render_transactions_table(transactions)

    st.subheader("Latest SEC 8-K Reports")
    reports = SEC8K.get_reports_by_company(selected_cik)
    render_8k_reports(reports)

    st.subheader("XGBoost Modeling")
    st.caption(
        f"Predicts whether each stock beats the median of the tracked universe over the next "
        f"{HORIZON_DAYS} trading days, from price, news, insider and 8-K features."
    )
    xgb_model = get_xgboost_model()
    xgb_model.reload_if_changed()
    if xgb_model.metrics.get("error"):
        st.warning(xgb_model.metrics["error"])
    else:
        metrics = xgb_model.metrics
        cols = st.columns(4)
        cols[0].metric("Test accuracy", metrics.get("accuracy", 0.0))
        cols[1].metric("Baseline accuracy", metrics.get("baseline_accuracy", 0.0))
        cols[2].metric("ROC AUC", metrics.get("roc_auc") if metrics.get("roc_auc") is not None else "—")
        cols[3].metric("Training rows", metrics.get("train_rows", 0))
        if metrics.get("test_period"):
            st.caption(f"Test period: {metrics['test_period'][0]} → {metrics['test_period'][1]} · trained {metrics.get('trained_at', '')}")

        prediction = xgb_model.predict_stock(selected_stock) if selected_stock else None
        if prediction is not None:
            st.metric(
                f"{selected_stock}: probability of beating the median (as of {prediction['as_of']})",
                f"{prediction['probability']:.0%}",
            )

        predictions = xgb_model.predict_all()
        if predictions is not None and not predictions.empty:
            st.markdown("**Latest predictions**")
            st.dataframe(predictions, use_container_width=True, hide_index=True)

        importances = xgb_model.get_feature_importances()
        if importances is not None and not importances.empty:
            st.markdown("**Feature importances**")
            st.bar_chart(importances.set_index("feature"))

    st.subheader("Weather vs Sector Returns")
    try:
        correlations = WeatherCorrelationAnalyzer().run()
    except Exception as exc:
        correlations = []
        st.warning(f"Could not compute weather correlations: {exc}")
    if correlations:
        st.caption("Pearson correlation between each city's daily weather and equal-weighted sector returns. Exploratory — check n_days.")
        st.dataframe(correlations[:25], use_container_width=True, hide_index=True)
    else:
        st.info("Not enough overlapping weather and price days yet (need at least 10). Weather is collected every 3 hours by Celery beat.")

    if st.button("Retrain XGBoost model"):
        with st.spinner("Training..."):
            get_xgboost_model().train_model()
        rerun_app()

    if st.button("Refresh data"):
        rerun_app()


if __name__ == "__main__":
    main()
