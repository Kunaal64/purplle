"""
main.py — FastAPI REST API
Purplle Store Intelligence Challenge — Part B

Run:
    uvicorn main:app --reload --port 8000

Endpoints:
    POST /ingest          — ingest events from .jsonl
    GET  /metrics         — visitor count, dwell time, conversion rate
    GET  /funnel          — entry → browse → checkout → purchase funnel
    GET  /anomalies       — detect unusual patterns
    GET  /health          — health check
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
import os
import time
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

DB_PATH = os.getenv("DB_PATH", "store_intelligence.db")


# ── Database setup ─────────────────────────────────────────────────────────────

def get_db():
    global DB_PATH
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
        except PermissionError:
            print(f"Permission denied creating {db_dir}. Falling back to local store_intelligence.db")
            DB_PATH = "store_intelligence.db"
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id    TEXT PRIMARY KEY,
            store_id    TEXT NOT NULL,
            camera_id   TEXT NOT NULL,
            visitor_id  TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            zone_id     TEXT,
            dwell_ms    INTEGER DEFAULT 0,
            is_staff    INTEGER DEFAULT 0,
            confidence  REAL,
            session_seq INTEGER DEFAULT 0,
            metadata    TEXT,
            ingested_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id         TEXT NOT NULL,
            coupon_code      TEXT,
            offer_name       TEXT,
            discount_code    TEXT,
            invoice_number   TEXT,
            invoice_type     TEXT,
            order_date       TEXT,
            order_time       TEXT,
            store_id         TEXT,
            customer_name    TEXT,
            customer_number  TEXT,
            qty              INTEGER,
            gmv              REAL,
            nmv              REAL,
            total_amount     REAL,
            timestamp        TEXT,
            ingested_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_store    ON events(store_id);
        CREATE INDEX IF NOT EXISTS idx_visitor  ON events(visitor_id);
        CREATE INDEX IF NOT EXISTS idx_type     ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_camera   ON events(camera_id);
        CREATE INDEX IF NOT EXISTS idx_ts       ON events(timestamp);

        CREATE INDEX IF NOT EXISTS idx_trans_store ON transactions(store_id);
        CREATE INDEX IF NOT EXISTS idx_trans_ts    ON transactions(timestamp);

        CREATE TABLE IF NOT EXISTS media_assets (
            filename       TEXT PRIMARY KEY,
            cloudinary_url TEXT NOT NULL,
            public_id      TEXT,
            uploaded_at    TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    # Migration: Alter table if metadata doesn't exist
    try:
        conn.execute("ALTER TABLE events ADD COLUMN metadata TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


def load_pos_data():
    import csv
    import glob
    from datetime import datetime

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM transactions")
    if cursor.fetchone()["cnt"] > 0:
        correlate_purchases(conn)
        conn.close()
        return

    csv_files = glob.glob("*.csv")
    if not csv_files:
        conn.close()
        return

    csv_file = csv_files[0]
    print(f"Loading POS data from {csv_file}...")
    with open(csv_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row.get("order_date", "").strip()
            time_str = row.get("order_time", "").strip()
            try:
                dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
                timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                timestamp = None

            conn.execute("""
                INSERT INTO transactions (
                    order_id, coupon_code, offer_name, discount_code,
                    invoice_number, invoice_type, order_date, order_time,
                    store_id, customer_name, customer_number, qty, gmv, nmv,
                    total_amount, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("order_id"),
                row.get("coupon_code"),
                row.get("offer_name"),
                row.get("discount_code"),
                row.get("invoice_number"),
                row.get("invoice_type"),
                row.get("order_date"),
                row.get("order_time"),
                row.get("store_id"),
                row.get("customer_name"),
                row.get("customer_number"),
                int(row.get("qty", 1) or 1),
                float(row.get("GMV", 0.0) or 0.0),
                float(row.get("NMV", 0.0) or 0.0),
                float(row.get("total_amount", 0.0) or 0.0),
                timestamp
            ))
    conn.commit()
    print("POS data loaded.")
    correlate_purchases(conn)
    conn.close()


def correlate_purchases(conn):
    import uuid
    rows = conn.execute("""
        SELECT DISTINCT order_id, store_id, total_amount, timestamp, coupon_code
        FROM transactions
        WHERE timestamp IS NOT NULL
    """).fetchall()

    correlations_created = 0
    for r in rows:
        order_id = r["order_id"]
        store_id = r["store_id"]
        total_amt = r["total_amount"]
        ts = r["timestamp"]
        coupon = r["coupon_code"]

        chk = conn.execute("""
            SELECT 1 FROM events
            WHERE event_id = ?
        """, (f"purchase-{order_id}",)).fetchone()
        
        if chk:
            continue

        match = conn.execute("""
            SELECT visitor_id, timestamp,
                   (strftime('%s', ?) - strftime('%s', timestamp)) as diff
            FROM events
            WHERE event_type = 'ZONE_ENTER'
              AND zone_id IN ('POS_COUNTER', 'BILLING_DESK', 'CHECKOUT')
              AND (strftime('%s', ?) - strftime('%s', timestamp)) >= 0
              AND (strftime('%s', ?) - strftime('%s', timestamp)) <= 300
            ORDER BY diff ASC
            LIMIT 1
        """, (ts, ts, ts)).fetchone()

        if match:
            visitor_id = match["visitor_id"]
            conn.execute("""
                INSERT INTO events (
                    event_id, store_id, camera_id, visitor_id, event_type,
                    timestamp, zone_id, confidence, session_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"purchase-{order_id}",
                store_id,
                "CAM_CHECKOUT_05",
                visitor_id,
                "PURCHASE",
                ts,
                "POS_COUNTER",
                1.0,
                0
            ))
            correlations_created += 1

    if correlations_created > 0:
        conn.commit()
        print(f"Created {correlations_created} new PURCHASE events via time-based correlation.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        load_pos_data()
    except Exception as e:
        print(f"Error loading POS data: {e}")
    yield

app = FastAPI(
    title="Purplle Store Intelligence API",
    description="CCTV analytics — visitor tracking, dwell time, conversion",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Initialize request state
    request.state.event_count = 0
    request.state.store_id = None
    
    response = await call_next(request)
    
    process_time = int((time.time() - start_time) * 1000)
    
    # Read populated state
    event_count = getattr(request.state, "event_count", 0)
    store_id = getattr(request.state, "store_id", None) or request.path_params.get("store_id") or request.query_params.get("store_id") or "N/A"
    
    log_data = {
        "trace_id": trace_id,
        "store_id": store_id,
        "endpoint": request.url.path,
        "latency_ms": process_time,
        "status_code": response.status_code,
        "event_count": event_count
    }
    print(json.dumps(log_data))
    
    response.headers["X-Trace-ID"] = trace_id
    return response

@app.exception_handler(sqlite3.Error)
async def sqlite_exception_handler(request: Request, exc: sqlite3.Error):
    return JSONResponse(
        status_code=503,
        content={
            "error": "Database Service Unavailable",
            "detail": "The store intelligence datastore is temporarily unavailable or degraded."
        }
    )

@app.get("/videos/{filename}")
async def get_video(filename: str):
    conn = get_db()
    row = conn.execute("SELECT cloudinary_url FROM media_assets WHERE filename = ?", (filename,)).fetchone()
    conn.close()
    if row and row["cloudinary_url"]:
        return RedirectResponse(url=row["cloudinary_url"])
    
    # Fallback to local files
    local_path = Path("CCTV Footage") / filename
    if local_path.exists():
        return FileResponse(local_path)
    
    raise HTTPException(status_code=404, detail="Video not found")


# ── Schemas ────────────────────────────────────────────────────────────────────

class Event(BaseModel):
    event_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id:   str
    camera_id:  str
    visitor_id: str
    event_type: str
    timestamp:  str
    zone_id:    Optional[str] = None
    dwell_ms:   int = 0
    is_staff:   bool = False
    confidence: float = 1.0
    metadata:   Optional[dict] = None


class IngestResponse(BaseModel):
    accepted:   int
    rejected:   int
    duplicates: int
    total:      int


# ── Helpers ────────────────────────────────────────────────────────────────────

VALID_EVENT_TYPES = {
    "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
    "ZONE_DWELL", "PURCHASE", "QUEUE_JOIN", "QUEUE_LEAVE",
    "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"
}

def validate_event(evt: dict) -> tuple[bool, str]:
    required = ["store_id", "camera_id", "visitor_id", "event_type", "timestamp"]
    for field in required:
        if not evt.get(field):
            reason = f"Missing field: {field}"
            print(json.dumps({"event": "validation_failed", "event_id": evt.get("event_id"), "reason": reason}))
            return False, reason
    if evt["event_type"] not in VALID_EVENT_TYPES:
        reason = f"Invalid event_type: {evt['event_type']}"
        print(json.dumps({"event": "validation_failed", "event_id": evt.get("event_id"), "reason": reason}))
        return False, reason
    return True, ""


def insert_event(conn, evt: dict) -> bool:
    """Insert event, return False if duplicate."""
    try:
        meta = evt.get("metadata") or {}
        conn.execute("""
            INSERT INTO events
            (event_id, store_id, camera_id, visitor_id, event_type,
             timestamp, zone_id, dwell_ms, is_staff, confidence, session_seq, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evt.get("event_id", str(uuid.uuid4())),
            evt["store_id"],
            evt["camera_id"],
            evt["visitor_id"],
            evt["event_type"],
            evt["timestamp"],
            evt.get("zone_id"),
            evt.get("dwell_ms", 0),
            1 if evt.get("is_staff") else 0,
            evt.get("confidence", 1.0),
            meta.get("session_seq", 0) if isinstance(meta, dict) else 0,
            json.dumps(meta) if isinstance(meta, dict) else "{}"
        ))
        return True
    except sqlite3.IntegrityError:
        return False


def format_event(row) -> dict:
    evt = dict(row)
    evt["is_staff"] = bool(evt.get("is_staff", 0))
    meta = evt.get("metadata")
    if isinstance(meta, str):
        try:
            evt["metadata"] = json.loads(meta)
        except Exception:
            evt["metadata"] = {}
    elif meta is None:
        evt["metadata"] = {}
        
    # Ensure session_seq is inside metadata as per required schema
    if isinstance(evt["metadata"], dict) and "session_seq" not in evt["metadata"] and "session_seq" in evt:
        evt["metadata"]["session_seq"] = evt["session_seq"]
        
    # Clean up DB-specific top-level columns
    evt.pop("ingested_at", None)
    evt.pop("session_seq", None)
    return evt


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    conn = get_db()
    stores = conn.execute("SELECT DISTINCT store_id FROM events").fetchall()
    store_statuses = {}
    warnings = []
    
    for s in stores:
        store_id = s["store_id"]
        max_ts_row = conn.execute("""
            SELECT MAX(timestamp) as max_ts FROM events WHERE store_id = ?
        """, [store_id]).fetchone()
        
        if max_ts_row and max_ts_row["max_ts"]:
            last_ts_str = max_ts_row["max_ts"]
            try:
                # Parse timestamp
                ts_clean = last_ts_str.replace("Z", "")
                last_dt = datetime.fromisoformat(ts_clean)
                now_dt = datetime.utcnow()
                lag_seconds = (now_dt - last_dt).total_seconds()
                lag_minutes = lag_seconds / 60.0
                
                store_statuses[store_id] = {
                    "last_event_timestamp": last_ts_str,
                    "lag_minutes": round(lag_minutes, 1),
                    "status": "STALE_FEED" if lag_minutes > 10 else "OK"
                }
                
                if lag_minutes > 10:
                    warnings.append(f"STALE_FEED for store {store_id}: last event lag is {round(lag_minutes, 1)} minutes")
            except Exception as e:
                store_statuses[store_id] = {
                    "last_event_timestamp": last_ts_str,
                    "error": f"Failed to parse timestamp: {e}",
                    "status": "UNKNOWN"
                }
        else:
            store_statuses[store_id] = {
                "last_event_timestamp": None,
                "status": "NO_EVENTS"
            }
    conn.close()
    
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stores": store_statuses,
        "warnings": warnings
    }


@app.post("/ingest", response_model=IngestResponse)
async def ingest_events(request: Request, file: UploadFile = File(...)):
    """Upload a .jsonl file of events."""
    content = await file.read()
    lines   = content.decode("utf-8").strip().split("\n")
    
    non_empty_lines = [l for l in lines if l.strip()]
    request.state.event_count = len(non_empty_lines)

    accepted = rejected = duplicates = 0
    conn = get_db()

    for line in non_empty_lines:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            rejected += 1
            continue

        if not request.state.store_id and isinstance(evt, dict):
            request.state.store_id = evt.get("store_id")

        valid, reason = validate_event(evt)
        if not valid:
            rejected += 1
            continue

        inserted = insert_event(conn, evt)
        if inserted:
            accepted += 1
        else:
            duplicates += 1

    conn.commit()
    try:
        correlate_purchases(conn)
    except Exception as e:
        print(f"Error correlating purchases on ingest: {e}")
    conn.close()
    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        duplicates=duplicates,
        total=len(lines),
    )


@app.post("/ingest/batch")
async def ingest_batch(request: Request, events: list[Event]):
    """Ingest a JSON array of events directly."""
    request.state.event_count = len(events)
    if events:
        request.state.store_id = events[0].store_id
        
    accepted = rejected = duplicates = 0
    conn = get_db()

    for evt in events:
        evt_dict = evt.model_dump()
        valid, reason = validate_event(evt_dict)
        if not valid:
            rejected += 1
            continue
        inserted = insert_event(conn, evt_dict)
        if inserted:
            accepted += 1
        else:
            duplicates += 1

    conn.commit()
    try:
        correlate_purchases(conn)
    except Exception as e:
        print(f"Error correlating purchases on batch ingest: {e}")
    conn.close()
    return {"accepted": accepted, "rejected": rejected, "duplicates": duplicates}


@app.get("/metrics")
def get_metrics(
    store_id:  Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    date:      Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Returns:
    - Total visitors (unique visitor IDs with ENTRY event, excluding staff)
    - Average dwell time per zone
    - Conversion rate (visitors who reached checkout / total visitors)
    - Peak hour
    """
    conn  = get_db()
    where = ["is_staff = 0"]
    params = []

    if store_id:
        where.append("store_id = ?")
        params.append(store_id)
    if camera_id:
        where.append("camera_id = ?")
        params.append(camera_id)
    if date:
        where.append("timestamp LIKE ?")
        params.append(f"{date}%")

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    # Total unique visitors
    row = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt
        FROM events
        {where_sql} AND event_type = 'ENTRY'
    """, params).fetchone()
    total_visitors = row["cnt"] if row else 0

    # Total exits
    row = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt
        FROM events
        {where_sql} AND event_type = 'EXIT'
    """, params).fetchone()
    total_exits = row["cnt"] if row else 0

    # Average dwell per zone
    zone_rows = conn.execute(f"""
        SELECT zone_id,
               AVG(dwell_ms) as avg_dwell_ms,
               COUNT(*)      as dwell_events
        FROM events
        {where_sql} AND event_type IN ('ZONE_DWELL', 'ZONE_EXIT') AND zone_id IS NOT NULL
        GROUP BY zone_id
        ORDER BY avg_dwell_ms DESC
    """, params).fetchall()

    zone_dwell = [
        {
            "zone_id":      r["zone_id"],
            "avg_dwell_ms": round(r["avg_dwell_ms"] or 0),
            "avg_dwell_s":  round((r["avg_dwell_ms"] or 0) / 1000, 1),
            "dwell_events": r["dwell_events"],
        }
        for r in zone_rows
    ]

    # Checkout visitors (anyone who entered CHECKOUT zone)
    checkout_zones = ("CHECKOUT", "POS_COUNTER", "BILLING_DESK")
    placeholders   = ",".join("?" * len(checkout_zones))
    checkout_params = params + list(checkout_zones)
    row = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt
        FROM events
        {where_sql} AND event_type = 'ZONE_ENTER' AND zone_id IN ({placeholders})
    """, checkout_params).fetchone()
    checkout_visitors = row["cnt"] if row else 0

    conversion_rate = (
        round((checkout_visitors / total_visitors) * 100, 1)
        if total_visitors > 0 else 0.0
    )

    # Peak hour
    peak_row = conn.execute(f"""
        SELECT strftime('%H', timestamp) as hour, COUNT(DISTINCT visitor_id) as cnt
        FROM events
        {where_sql} AND event_type = 'ENTRY'
        GROUP BY hour
        ORDER BY cnt DESC
        LIMIT 1
    """, params).fetchone()
    peak_hour = f"{peak_row['hour']}:00" if peak_row else "N/A"

    # Events by camera
    cam_rows = conn.execute(f"""
        SELECT camera_id, COUNT(*) as event_count
        FROM events
        {where_sql}
        GROUP BY camera_id
    """, params).fetchall()

    # POS integration metrics
    STORE_MAP = {
        "STORE_PUR_001": "ST1008",
        "ST1008": "STORE_PUR_001"
    }
    trans_store_id = store_id
    if store_id in STORE_MAP:
        if store_id == "STORE_PUR_001":
            trans_store_id = "ST1008"

    trans_where = []
    trans_params = []
    if store_id:
        trans_where.append("store_id = ?")
        trans_params.append(trans_store_id)
    if date:
        try:
            from datetime import datetime
            dt = datetime.strptime(date, "%Y-%m-%d")
            csv_date = dt.strftime("%d-%m-%Y")
            trans_where.append("order_date = ?")
            trans_params.append(csv_date)
        except ValueError:
            pass

    trans_where_sql = "WHERE " + " AND ".join(trans_where) if trans_where else ""

    daily_sales_transactions = conn.execute(f"""
        SELECT COUNT(DISTINCT order_id) as cnt
        FROM transactions
        {trans_where_sql}
    """, trans_params).fetchone()["cnt"]

    row = conn.execute(f"""
        SELECT SUM(qty) as total_qty,
               SUM(gmv) as total_gmv,
               SUM(nmv) as total_nmv,
               SUM(total_amount) as total_amt
        FROM transactions
        {trans_where_sql}
    """, trans_params).fetchone()

    daily_items_sold = row["total_qty"] if row and row["total_qty"] is not None else 0
    daily_revenue_gmv = round(row["total_gmv"] or 0.0, 2) if row and row["total_gmv"] is not None else 0.0
    daily_revenue_nmv = round(row["total_nmv"] or 0.0, 2) if row and row["total_nmv"] is not None else 0.0
    daily_sales_amount = round(row["total_amt"] or 0.0, 2) if row and row["total_amt"] is not None else 0.0

    actual_store_conversion_rate = (
        round((daily_sales_transactions / total_visitors) * 100, 1)
        if total_visitors > 0 else 0.0
    )

    # Queue Depth calculation (average queue_depth from BILLING_QUEUE_JOIN events)
    q_rows = conn.execute(f"""
        SELECT metadata FROM events
        {where_sql} AND event_type = 'BILLING_QUEUE_JOIN'
    """, params).fetchall()
    q_depths = []
    for r in q_rows:
        try:
            m = json.loads(r["metadata"] or "{}")
            val = m.get("queue_depth")
            if val is not None:
                q_depths.append(int(val))
        except Exception:
            pass
    queue_depth = round(sum(q_depths) / len(q_depths), 1) if q_depths else 0.0

    # Abandonment Rate calculation
    total_joins = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM events
        {where_sql} AND event_type = 'BILLING_QUEUE_JOIN'
    """, params).fetchone()["cnt"]
    total_abandons = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM events
        {where_sql} AND event_type = 'BILLING_QUEUE_ABANDON'
    """, params).fetchone()["cnt"]
    abandonment_rate = (
        round((total_abandons / total_joins) * 100, 1)
        if total_joins > 0 else 0.0
    )

    conn.close()

    return {
        "store_id":                      store_id or "ALL",
        "total_visitors":                total_visitors,
        "unique_visitors":               total_visitors,
        "total_exits":                   total_exits,
        "checkout_visitors":             checkout_visitors,
        "conversion_rate_pct":           conversion_rate,
        "conversion_rate":               actual_store_conversion_rate,
        "peak_hour":                     peak_hour,
        "zone_dwell":                    zone_dwell,
        "avg_dwell_per_zone":            {z["zone_id"]: z["avg_dwell_s"] for z in zone_dwell},
        "events_by_camera":              [dict(r) for r in cam_rows],
        "daily_sales_transactions":      daily_sales_transactions,
        "daily_items_sold":              daily_items_sold,
        "daily_revenue_gmv":             daily_revenue_gmv,
        "daily_revenue_nmv":             daily_revenue_nmv,
        "daily_sales_amount":            daily_sales_amount,
        "actual_store_conversion_rate_pct": actual_store_conversion_rate,
        "queue_depth":                   queue_depth,
        "abandonment_rate":              abandonment_rate,
    }


@app.get("/funnel")
def get_funnel(
    store_id: Optional[str] = Query(None),
    date:     Optional[str] = Query(None, description="YYYY-MM-DD")
):
    """
    Customer journey funnel:
    ENTRY → Browse (any ZONE_ENTER) → Checkout zone → PURCHASE → EXIT
    """
    conn   = get_db()
    params = []
    where  = ["is_staff = 0"]
    if store_id:
        where.append("store_id = ?")
        params.append(store_id)
    if date:
        where.append("timestamp LIKE ?")
        params.append(f"{date}%")
    where_sql = "WHERE " + " AND ".join(where)

    # Stage 1: entered store (using visitor_id to deduplicate and prevent double-counting on re-entry)
    r = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
        {where_sql} AND event_type IN ('ENTRY', 'REENTRY')
    """, params).fetchone()
    entered = r["cnt"] if r else 0

    # Stage 2: browsed (entered any product zone)
    product_zones = ("SKINCARE_AISLE", "MAKEUP_AISLE", "FLOOR_LEFT",
                     "FLOOR_RIGHT", "CENTER_FLOOR", "FLOOR_UPPER", "FLOOR_LOWER", "ACCESSORIES")
    ph = ",".join("?" * len(product_zones))
    r = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
        {where_sql} AND event_type = 'ZONE_ENTER' AND zone_id IN ({ph})
    """, params + list(product_zones)).fetchone()
    browsed = min(r["cnt"] if r else 0, entered)

    # Stage 3: reached checkout
    checkout_zones = ("CHECKOUT", "POS_COUNTER", "BILLING_DESK")
    ph2 = ",".join("?" * len(checkout_zones))
    r = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
        {where_sql} AND event_type = 'ZONE_ENTER' AND zone_id IN ({ph2})
    """, params + list(checkout_zones)).fetchone()
    at_checkout = min(r["cnt"] if r else 0, browsed)

    # Stage 4: purchased
    r = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
        {where_sql} AND event_type = 'PURCHASE'
    """, params).fetchone()
    purchased = min(r["cnt"] if r else 0, at_checkout)

    # Stage 5: exited (completed visit)
    r = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
        {where_sql} AND event_type = 'EXIT'
    """, params).fetchone()
    exited = min(r["cnt"] if r else 0, entered)  

    def pct(num, denom):
        return round((num / denom * 100), 1) if denom > 0 else 0.0

    conn.close()
    return {
        "funnel": [
            {"stage": "1_entered",     "visitors": entered,    "pct_of_entry": 100.0},
            {"stage": "2_browsed",     "visitors": browsed,    "pct_of_entry": pct(browsed, entered)},
            {"stage": "3_at_checkout", "visitors": at_checkout,"pct_of_entry": pct(at_checkout, entered)},
            {"stage": "4_purchased",   "visitors": purchased,  "pct_of_entry": pct(purchased, entered)},
            {"stage": "5_exited",      "visitors": exited,     "pct_of_entry": pct(exited, entered)},
        ],
        "conversion_rate_pct": pct(at_checkout, entered),
        "purchase_conversion_rate_pct": pct(purchased, entered),
        "drop_off": {
            "entry_to_browse":    max(0, pct(entered - browsed, entered)),
            "browse_to_checkout": max(0, pct(browsed - at_checkout, browsed)),
            "checkout_to_purchase": max(0, pct(at_checkout - purchased, at_checkout)) if at_checkout > 0 else 0.0,
        }
    }


@app.get("/anomalies")
def get_anomalies(store_id: Optional[str] = Query(None)):
    if not store_id:
        store_id = "STORE_PUR_001"
    return get_store_anomalies(store_id=store_id)


@app.get("/visitors/{visitor_id}")
def get_visitor_journey(visitor_id: str):
    """Full journey for a specific visitor."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM events
        WHERE visitor_id = ?
        ORDER BY timestamp, session_seq
    """, (visitor_id,)).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Visitor not found")

    return {
        "visitor_id": visitor_id,
        "events":     [format_event(r) for r in rows],
        "total":      len(rows),
    }


@app.get("/events")
def list_events(
    store_id:   Optional[str] = Query(None),
    camera_id:  Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit:      int           = Query(100, le=1000),
    offset:     int           = Query(0),
):
    """List events with filters."""
    conn   = get_db()
    where  = []
    params = []

    if store_id:
        where.append("store_id = ?");   params.append(store_id)
    if camera_id:
        where.append("camera_id = ?");  params.append(camera_id)
    if event_type:
        where.append("event_type = ?"); params.append(event_type)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(f"""
        SELECT * FROM events {where_sql}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    total = conn.execute(f"SELECT COUNT(*) as cnt FROM events {where_sql}", params).fetchone()
    conn.close()

    return {
        "events": [format_event(r) for r in rows],
        "total":  total["cnt"],
        "limit":  limit,
        "offset": offset,
    }


@app.post("/events/ingest")
async def events_ingest(request: Request, payload: list[dict]):
    request.state.event_count = len(payload)
    if payload:
        request.state.store_id = payload[0].get("store_id")
    if len(payload) > 500:
        raise HTTPException(status_code=400, detail="Batch size exceeds maximum limit of 500 events")
    
    accepted = rejected = duplicates = 0
    errors = []
    conn = get_db()
    
    for idx, raw_evt in enumerate(payload):
        valid, reason = validate_event(raw_evt)
        if not valid:
            rejected += 1
            errors.append({"index": idx, "reason": reason})
            continue
        inserted = insert_event(conn, raw_evt)
        if inserted:
            accepted += 1
        else:
            duplicates += 1
            
    conn.commit()
    try:
        correlate_purchases(conn)
    except Exception as e:
        print(f"Error correlating purchases: {e}")
    conn.close()
    
    return {
        "accepted": accepted,
        "rejected": rejected,
        "duplicates": duplicates,
        "total": len(payload),
        "errors": errors
    }


@app.get("/stores/{store_id}/metrics")
def get_store_metrics(
    store_id:  str,
    camera_id: Optional[str] = Query(None),
    date:      Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    return get_metrics(store_id=store_id, camera_id=camera_id, date=date)


@app.get("/stores/{store_id}/funnel")
def get_store_funnel(
    store_id: str,
    date:     Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    return get_funnel(store_id=store_id, date=date)


@app.get("/stores/{store_id}/heatmap")
def get_store_heatmap(
    store_id: str,
    date:     Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    conn = get_db()
    where = ["store_id = ?", "is_staff = 0"]
    params = [store_id]
    if date:
        where.append("timestamp LIKE ?")
        params.append(f"{date}%")
    where_sql = "WHERE " + " AND ".join(where)

    # Fetch total sessions for confidence flag
    sess_row = conn.execute(f"""
        SELECT COUNT(DISTINCT visitor_id || '-' || session_seq) as cnt
        FROM events
        {where_sql}
    """, params).fetchone()
    total_sessions = sess_row["cnt"] if sess_row else 0
    data_confidence = total_sessions >= 20

    # Fetch visits and dwell times per zone
    rows = conn.execute(f"""
        SELECT zone_id, 
               COUNT(DISTINCT visitor_id || '-' || session_seq) as visits,
               AVG(dwell_ms) as avg_dwell_ms
        FROM events
        {where_sql} AND zone_id IS NOT NULL AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL', 'ZONE_EXIT')
        GROUP BY zone_id
    """, params).fetchall()

    max_visits = max([r["visits"] for r in rows]) if rows else 0
    max_dwell = max([r["avg_dwell_ms"] for r in rows]) if rows else 0

    heatmap = []
    for r in rows:
        norm_freq = round((r["visits"] / max_visits) * 100, 1) if max_visits > 0 else 0.0
        norm_dwell = round((r["avg_dwell_ms"] / max_dwell) * 100, 1) if max_dwell > 0 else 0.0
        heatmap.append({
            "zone_id": r["zone_id"],
            "visits": r["visits"],
            "avg_dwell_ms": round(r["avg_dwell_ms"] or 0),
            "normalized_frequency": norm_freq,
            "normalized_dwell": norm_dwell
        })

    conn.close()
    return {
        "store_id": store_id,
        "heatmap": heatmap,
        "total_sessions": total_sessions,
        "data_confidence": data_confidence
    }


@app.get("/stores/{store_id}/anomalies")
def get_store_anomalies(
    store_id: str,
    date:     Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    conn = get_db()
    
    where = ["store_id = ?", "is_staff = 0"]
    params = [store_id]
    if date:
        where.append("timestamp LIKE ?")
        params.append(f"{date}%")
    where_sql = "WHERE " + " AND ".join(where)
    
    anomalies = []
    
    # 1. Queue Spike
    q_rows = conn.execute(f"""
        SELECT metadata FROM events
        {where_sql} AND event_type = 'BILLING_QUEUE_JOIN'
    """, params).fetchall()
    q_depths = []
    for r in q_rows:
        try:
            m = json.loads(r["metadata"] or "{}")
            val = m.get("queue_depth")
            if val is not None:
                q_depths.append(int(val))
        except Exception:
            pass
    max_q = max(q_depths) if q_depths else 0
    if max_q > 3:
        anomalies.append({
            "type": "BILLING_QUEUE_SPIKE",
            "severity": "CRITICAL" if max_q > 5 else "WARN",
            "note": f"Queue depth reached a peak of {max_q} customers.",
            "suggested_action": "Open additional billing registers immediately."
        })
        
    # 2. Conversion Drop (Preceding 7-Day Average)
    query_date = date
    if not query_date:
        max_ts_row = conn.execute("""
            SELECT MAX(timestamp) as max_ts FROM events WHERE store_id = ?
        """, [store_id]).fetchone()
        if max_ts_row and max_ts_row["max_ts"]:
            query_date = max_ts_row["max_ts"][:10]
        else:
            query_date = datetime.utcnow().strftime("%Y-%m-%d")

    def get_daily_conversion_rate(db_conn, st_id: str, dt_str: str) -> float:
        # Total entries
        entries = db_conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) as cnt
            FROM events
            WHERE store_id = ? AND is_staff = 0 AND event_type IN ('ENTRY', 'REENTRY') AND timestamp LIKE ?
        """, (st_id, f"{dt_str}%")).fetchone()["cnt"]
        if entries == 0:
            return 0.0
        # Total purchases
        purchases = db_conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) as cnt
            FROM events
            WHERE store_id = ? AND is_staff = 0 AND event_type = 'PURCHASE' AND timestamp LIKE ?
        """, (st_id, f"{dt_str}%")).fetchone()["cnt"]
        return (purchases / entries) * 100

    try:
        from datetime import datetime as dt_parser, timedelta
        curr_dt = dt_parser.strptime(query_date, "%Y-%m-%d")
        prev_rates = []
        for i in range(1, 8):
            prev_date = (curr_dt - timedelta(days=i)).strftime("%Y-%m-%d")
            rate = get_daily_conversion_rate(conn, store_id, prev_date)
            if rate > 0:
                prev_rates.append(rate)
        avg_7day = sum(prev_rates) / len(prev_rates) if prev_rates else 0.0
        today_conv = get_daily_conversion_rate(conn, store_id, query_date)
        
        # Fallback to historical conversion rate if no 7-day preceding data is found
        if avg_7day == 0.0:
            prev_vis = conn.execute("""
                SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
                WHERE store_id = ? AND is_staff = 0 AND event_type IN ('ENTRY', 'REENTRY') AND timestamp < ?
            """, (store_id, f"{query_date}%")).fetchone()["cnt"]
            
            prev_pur = conn.execute("""
                SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'PURCHASE' AND timestamp < ?
            """, (store_id, f"{query_date}%")).fetchone()["cnt"]
            
            avg_7day = (prev_pur / prev_vis) * 100 if prev_vis > 0 else 0.0

        if avg_7day > 0 and today_conv < avg_7day * 0.8:
            anomalies.append({
                "type": "CONVERSION_DROP",
                "severity": "CRITICAL",
                "note": f"Store conversion rate ({round(today_conv, 1)}%) is significantly lower than average ({round(avg_7day, 1)}%).",
                "suggested_action": "Check checkout queues or review zone pricing mismatches."
            })
    except Exception as e:
        print(f"Error calculating conversion drop anomaly: {e}")
        
    # 3. Dead Zone (No visits in 30 minutes)
    max_ts_row = conn.execute(f"""
        SELECT MAX(timestamp) as max_ts FROM events
        {where_sql}
    """, params).fetchone()
    if max_ts_row and max_ts_row["max_ts"]:
        max_ts_str = max_ts_row["max_ts"]
        zones_row = conn.execute(f"""
            SELECT DISTINCT zone_id FROM events
            WHERE store_id = ? AND zone_id IS NOT NULL AND zone_id != 'STOCKROOM'
        """, [store_id]).fetchall()
        
        for z in zones_row:
            zone_id = z["zone_id"]
            recent_row = conn.execute(f"""
                SELECT 1 FROM events
                {where_sql} AND zone_id = ? AND event_type = 'ZONE_ENTER'
                  AND ABS(strftime('%s', timestamp) - strftime('%s', ?)) <= 1800
                LIMIT 1
            """, params + [zone_id, max_ts_str]).fetchone()
            
            if not recent_row:
                anomalies.append({
                    "type": "DEAD_ZONE",
                    "severity": "INFO",
                    "note": f"Zone '{zone_id}' has recorded no visitor entries in the last 30 minutes.",
                    "suggested_action": "Inspect zone display layout and check camera coverage."
                })
                
    conn.close()
    return {"anomalies": anomalies, "total": len(anomalies)}

frontend_dist = Path("frontend/dist")
if frontend_dist.exists() and frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

