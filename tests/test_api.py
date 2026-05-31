# PROMPT: Generate automated test suite for FastAPI Store Intelligence app with idempotency, database failure mock, and edge case assertions.
# CHANGES MADE: Added tests for event ingestion idempotency, DB 503 degradation, empty stores, staff exclusions, re-entry deduplication in funnel, and stale feed warnings in health endpoint.
"""
tests/test_api.py — API test suite
Run: pytest tests/ -v
"""

import pytest
import json
from fastapi.testclient import TestClient
from main import app, init_db, DB_PATH
import os

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use a fresh temp DB for each test."""
    db = str(tmp_path / "test.db")
    monkeypatch.setattr("main.DB_PATH", db)
    init_db()
    yield
    if os.path.exists(db):
        os.remove(db)


# ── Sample events ──────────────────────────────────────────────────────────────

SAMPLE_EVENTS = [
    {
        "event_id":   "evt-001",
        "store_id":   "STORE_PUR_001",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_AAAA0001",
        "event_type": "ENTRY",
        "timestamp":  "2026-04-10T20:10:00Z",
        "zone_id":    None,
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.91,
        "metadata":   {"session_seq": 1},
    },
    {
        "event_id":   "evt-002",
        "store_id":   "STORE_PUR_001",
        "camera_id":  "CAM_FLOOR_01",
        "visitor_id": "VIS_AAAA0001",
        "event_type": "ZONE_ENTER",
        "timestamp":  "2026-04-10T20:11:00Z",
        "zone_id":    "SKINCARE_AISLE",
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.88,
        "metadata":   {"session_seq": 2},
    },
    {
        "event_id":   "evt-003",
        "store_id":   "STORE_PUR_001",
        "camera_id":  "CAM_FLOOR_01",
        "visitor_id": "VIS_AAAA0001",
        "event_type": "ZONE_ENTER",
        "timestamp":  "2026-04-10T20:13:00Z",
        "zone_id":    "CHECKOUT",
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.85,
        "metadata":   {"session_seq": 3},
    },
    {
        "event_id":   "evt-004",
        "store_id":   "STORE_PUR_001",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_AAAA0001",
        "event_type": "EXIT",
        "timestamp":  "2026-04-10T20:15:00Z",
        "zone_id":    None,
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.90,
        "metadata":   {"session_seq": 4},
    },
    {
        "event_id":   "evt-005",
        "store_id":   "STORE_PUR_001",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_BBBB0002",
        "event_type": "ENTRY",
        "timestamp":  "2026-04-10T20:12:00Z",
        "zone_id":    None,
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.87,
        "metadata":   {"session_seq": 1},
    },
]


def ingest_samples():
    jsonl = "\n".join(json.dumps(e) for e in SAMPLE_EVENTS)
    return client.post(
        "/ingest",
        files={"file": ("events.jsonl", jsonl.encode(), "application/octet-stream")},
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ingest_valid_events():
    r = ingest_samples()
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] == 5
    assert data["rejected"] == 0
    assert data["duplicates"] == 0


def test_ingest_duplicate_events():
    ingest_samples()
    r = ingest_samples()
    assert r.status_code == 200
    data = r.json()
    assert data["duplicates"] == 5
    assert data["accepted"] == 0


def test_ingest_invalid_event():
    bad = json.dumps({"event_id": "bad-001", "store_id": "X"})  # missing required fields
    r = client.post(
        "/ingest",
        files={"file": ("bad.jsonl", bad.encode(), "application/octet-stream")},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] == 1


def test_metrics_visitor_count():
    ingest_samples()
    r = client.get("/metrics?store_id=STORE_PUR_001")
    assert r.status_code == 200
    data = r.json()
    assert data["total_visitors"] == 2   # VIS_AAAA0001 and VIS_BBBB0002
    assert data["checkout_visitors"] == 1
    assert data["conversion_rate_pct"] == 50.0


def test_metrics_no_data():
    r = client.get("/metrics?store_id=NONEXISTENT")
    assert r.status_code == 200
    assert r.json()["total_visitors"] == 0


def test_funnel():
    ingest_samples()
    r = client.get("/funnel?store_id=STORE_PUR_001")
    assert r.status_code == 200
    data = r.json()
    funnel = {f["stage"]: f["visitors"] for f in data["funnel"]}
    assert funnel["1_entered"] == 2
    assert funnel["3_at_checkout"] == 1
    assert data["conversion_rate_pct"] == 50.0


def test_visitor_journey():
    ingest_samples()
    r = client.get("/visitors/VIS_AAAA0001")
    assert r.status_code == 200
    data = r.json()
    assert data["visitor_id"] == "VIS_AAAA0001"
    assert data["total"] == 4


def test_visitor_not_found():
    r = client.get("/visitors/NONEXISTENT")
    assert r.status_code == 404


def test_events_filter():
    ingest_samples()
    r = client.get("/events?event_type=ENTRY")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert all(e["event_type"] == "ENTRY" for e in data["events"])


def test_anomalies_endpoint():
    ingest_samples()
    r = client.get("/anomalies?store_id=STORE_PUR_001")
    assert r.status_code == 200
    assert "anomalies" in r.json()


def test_batch_ingest():
    r = client.post("/ingest/batch", json=SAMPLE_EVENTS)
    assert r.status_code == 200
    assert r.json()["accepted"] == 5


# --- New tests addressing missing problem statement requirements ---

def test_events_ingest_idempotency():
    # Ingest batch first time
    r = client.post("/events/ingest", json=SAMPLE_EVENTS)
    assert r.status_code == 200
    assert r.json()["accepted"] == 5
    assert r.json()["duplicates"] == 0
    
    # Ingest batch second time (should trigger idempotency/duplicates)
    r2 = client.post("/events/ingest", json=SAMPLE_EVENTS)
    assert r2.status_code == 200
    assert r2.json()["accepted"] == 0
    assert r2.json()["duplicates"] == 5


def test_database_degradation(monkeypatch):
    import sqlite3
    def mock_connect(*args, **kwargs):
        raise sqlite3.OperationalError("Simulated database failure")
    monkeypatch.setattr(sqlite3, "connect", mock_connect)
    
    r = client.get("/metrics")
    assert r.status_code == 503
    assert r.json()["error"] == "Database Service Unavailable"
    assert "detail" in r.json()


def test_metrics_edge_cases():
    # Test empty store
    r = client.get("/stores/STORE_EMPTY/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data["total_visitors"] == 0
    assert data["unique_visitors"] == 0
    assert data["conversion_rate"] == 0.0
    
    # Test staff exclusion
    staff_evt = {
        "event_id":   "evt-staff-001",
        "store_id":   "STORE_STAFF",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_STAFF_01",
        "event_type": "ENTRY",
        "timestamp":  "2026-04-10T20:10:00Z",
        "is_staff":   True,
        "confidence": 0.95,
        "metadata":   {"session_seq": 1}
    }
    client.post("/events/ingest", json=[staff_evt])
    r2 = client.get("/stores/STORE_STAFF/metrics")
    assert r2.status_code == 200
    assert r2.json()["total_visitors"] == 0
    
    # Test zero purchases conversion rate
    visitor_evt = {
        "event_id":   "evt-vis-001",
        "store_id":   "STORE_NO_PURCHASE",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_AAAA0001",
        "event_type": "ENTRY",
        "timestamp":  "2026-04-10T20:10:00Z",
        "is_staff":   False,
        "confidence": 0.95,
        "metadata":   {"session_seq": 1}
    }
    client.post("/events/ingest", json=[visitor_evt])
    r3 = client.get("/stores/STORE_NO_PURCHASE/metrics")
    assert r3.status_code == 200
    assert r3.json()["total_visitors"] == 1
    assert r3.json()["conversion_rate"] == 0.0


def test_funnel_reentry_deduplication():
    reentry_events = [
        {
            "event_id":   "evt-re-001",
            "store_id":   "STORE_REENTRY",
            "camera_id":  "CAM_ENTRY_03",
            "visitor_id": "VIS_REENTRY_01",
            "event_type": "ENTRY",
            "timestamp":  "2026-04-10T20:10:00Z",
            "is_staff":   False,
            "confidence": 0.91,
            "metadata":   {"session_seq": 1},
        },
        {
            "event_id":   "evt-re-002",
            "store_id":   "STORE_REENTRY",
            "camera_id":  "CAM_ENTRY_03",
            "visitor_id": "VIS_REENTRY_01",
            "event_type": "EXIT",
            "timestamp":  "2026-04-10T20:12:00Z",
            "is_staff":   False,
            "confidence": 0.91,
            "metadata":   {"session_seq": 2},
        },
        {
            "event_id":   "evt-re-003",
            "store_id":   "STORE_REENTRY",
            "camera_id":  "CAM_ENTRY_03",
            "visitor_id": "VIS_REENTRY_01",
            "event_type": "REENTRY",
            "timestamp":  "2026-04-10T20:15:00Z",
            "is_staff":   False,
            "confidence": 0.91,
            "metadata":   {"session_seq": 3},
        },
    ]
    client.post("/events/ingest", json=reentry_events)
    r = client.get("/stores/STORE_REENTRY/funnel")
    assert r.status_code == 200
    data = r.json()
    funnel = {f["stage"]: f["visitors"] for f in data["funnel"]}
    assert funnel["1_entered"] == 1  # Should only be 1 instead of 2 (no double counting)


def test_health_stale_feed_warning():
    from datetime import datetime, timedelta
    ts_stale = (datetime.utcnow() - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_evt = {
        "event_id":   "evt-stale-001",
        "store_id":   "STORE_STALE",
        "camera_id":  "CAM_ENTRY_03",
        "visitor_id": "VIS_STALE_01",
        "event_type": "ENTRY",
        "timestamp":  ts_stale,
        "is_staff":   False,
        "confidence": 0.95,
        "metadata":   {"session_seq": 1}
    }
    client.post("/events/ingest", json=[stale_evt])
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "warnings" in data
    assert len(data["warnings"]) > 0
    assert any("STORE_STALE" in w for w in data["warnings"])
    assert data["stores"]["STORE_STALE"]["status"] == "STALE_FEED"
