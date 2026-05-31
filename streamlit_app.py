import streamlit as st
from config.database import init_neo4j
from models.stock import Stock
from models.news import NewsArticle
from models.sec_form4 import SECForm4
from models.sec_8k import SEC8K
from modules.modeling.xgboost_model import XGBoostModel
from config.tickers import SYMBOL_CIK_MAP


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
    model = XGBoostModel()
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

    init_neo4j()

    stocks = load_stocks()
    symbols = [stock["symbol"] for stock in stocks]

    sidebar = st.sidebar
    sidebar.header("Filters")
    selected_stock = sidebar.selectbox("Select stock symbol", symbols)
    cik_options = [f"{v} ({k})" for k, v in SYMBOL_CIK_MAP.items()]
    selected_cik_display = sidebar.selectbox("SEC company (CIK)", cik_options)
    selected_cik = selected_cik_display.split(" ")[0]  # Extract CIK number

    if selected_stock:
        selected_stock_data = next((s for s in stocks if s["symbol"] == selected_stock), None)
        if selected_stock_data and selected_stock_data.get("price") is not None:
            st.metric("Latest price", f"${selected_stock_data['price']:.2f}")


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
    xgb_model = get_xgboost_model()
    if xgb_model.metrics.get("error"):
        st.warning(xgb_model.metrics["error"])
    else:
        st.metric("Model accuracy", xgb_model.metrics.get("accuracy", 0.0))

        st.markdown("**Training dataset preview**")
        preview_cols = [
            c for c in ["symbol", "news_count", "avg_sentiment", "sector"]
            if c in xgb_model.feature_df.columns
        ]
        st.dataframe(xgb_model.feature_df[preview_cols], use_container_width=True)

        importances = xgb_model.get_feature_importances()
        if not importances.empty:
            st.markdown("**Feature importances**")
            importance_chart = importances.set_index("feature")
            st.bar_chart(importance_chart)

        predicted = xgb_model.predict_stock(selected_stock)
        if predicted is not None:
            st.metric("Predicted insider buy signal", "Yes" if predicted == 1 else "No")

    if st.button("Retrain XGBoost model"):
        get_xgboost_model.clear()
        rerun_app()

    if st.button("Refresh data"):
        rerun_app()


if __name__ == "__main__":
    main()
