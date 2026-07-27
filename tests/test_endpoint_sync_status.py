"""Tests de l'endpoint /api/admin/sync-status."""
from __future__ import annotations

import json
import os

import pytest

# NOTA: conftest.py fa import _bootstrap i sys.path.insert per app.py.
# Importem l'app amb un try/except perquè app.py pot fer warm-up de la BD
# al startup (crida obtenir_titols_infoanex, etc.), i no volem que això
# faci fallar el test si la BD no és accessible en aquest moment.


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Retorna Flask test client. Env var SYNC_STATUS_FILE apunta a tmp."""
    status_file = str(tmp_path / "sync_status.json")
    monkeypatch.setenv("SYNC_STATUS_FILE", status_file)

    # Importa app aquí per no fer-ho al collect
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c, status_file


def test_endpoint_state_not_running_quan_fitxer_no_existeix(client):
    c, status_file = client
    assert not os.path.exists(status_file)

    resp = c.get("/api/admin/sync-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["state"] == "not_running"
    assert "sync_status.json no existeix" in data["message"]
    assert data["status_file"] == status_file


def test_endpoint_state_running_llegeix_snapshot(client):
    c, status_file = client
    snapshot = {
        "started_at": "2026-07-27T09:00:00Z",
        "last_pass_at": "2026-07-27T10:00:00Z",
        "totals": {"trobades": 42, "ok": 40,
                   "error_motor": 1, "error_patch": 1, "error_altres": 0},
        "recent_passes": [
            {"ts": "2026-07-27T10:00:00Z", "trobades": 3, "ok": 3,
             "error_motor": 0, "error_patch": 0, "error_altres": 0,
             "dry_run": False, "elapsed_sec": 0.5, "errors": []},
        ],
        "config": {"interval_sec": 10.0, "max_per_pass": 50, "dry_run": False},
    }
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)

    resp = c.get("/api/admin/sync-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["state"] == "running"
    assert data["totals"]["trobades"] == 42
    assert data["totals"]["ok"] == 40
    assert len(data["recent_passes"]) == 1
    assert data["config"]["interval_sec"] == 10.0


def test_endpoint_state_error_amb_json_malformat(client):
    c, status_file = client
    with open(status_file, "w", encoding="utf-8") as f:
        f.write("això no és JSON vàlid { { {")

    resp = c.get("/api/admin/sync-status")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["ok"] is False
    assert data["state"] == "error_reading_status"
    assert "error" in data
