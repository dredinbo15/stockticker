import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from modules.modeling import xgboost_model as xm
from queues.celery_app import app as celery_app
from tests.test_model import synthetic_prices


@pytest.fixture
def client(monkeypatch, tmp_path):
    # No `with` block, so the lifespan (Neo4j connect) does not run.
    model = xm.XGBoostModel(model_path=str(tmp_path / "m.joblib"), autoload=False)
    monkeypatch.setattr(main, "xgb_model", model)
    return TestClient(main.app)


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert "/api/model/predictions" in body["endpoints"]


def test_model_endpoints_404_before_training(client):
    assert client.get("/api/model/metrics").status_code == 404
    assert client.get("/api/model/features").status_code == 404
    assert client.get("/api/model/predict/AAPL").status_code == 404


def test_model_endpoints_after_training(client):
    main.xgb_model.train_on_dataset(xm.build_dataset(synthetic_prices()))
    pred = client.get("/api/model/predict/aapl").json()
    assert pred["symbol"] == "AAPL" and pred["signal_label"] in ("outperform", "underperform")
    assert len(client.get("/api/model/predictions").json()) == 8
    assert client.get("/api/model/predict/ZZZZ").status_code == 404


def test_prices_rejects_bad_period(client):
    assert client.post("/api/collect/prices?period=7w").status_code == 422


def test_beat_schedule_points_at_registered_tasks():
    import queues.tasks  # noqa: F401  (registers tasks)
    for entry in celery_app.conf.beat_schedule.values():
        assert entry["task"] in celery_app.tasks, entry["task"]
