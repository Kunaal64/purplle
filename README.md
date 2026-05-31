# Purplle Retail Store Intelligence System

A computer vision pipeline that converts raw CCTV footage into actionable retail analytics.

## What It Does

- **Counts visitors** entering and exiting the store
- **Tracks movement** across zones (entry, aisles, checkout)
- **Measures dwell time** per zone per visitor
- **Detects purchases** at POS/checkout counter
- **Calculates conversion rate** (visitors → buyers)
- **Flags anomalies** (long dwell, repeated entries, low confidence)

## Camera Setup (Purplle Store)

| Camera | Zone | Role |
|--------|------|------|
| CAM 1 | Main floor / Skincare | Browsing + Checkout |
| CAM 2 | Makeup aisle / Billing desk | Browsing + Purchase |
| CAM 3 | Entry door | Visitor counting |
| CAM 4 | Stock room | Staff zone (excluded from metrics) |
| CAM 5 | POS terminal | Purchase conversion |

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Verify setup
```bash
python -c "from ultralytics import YOLO; m = YOLO('yolov8n.pt'); print('Ready!')"
```

### 3. Run detection on each camera
```bash
# Entry camera (visitor counting)
python pipeline/detect.py --video "clips/CAM 3.mp4" --store STORE_PUR_001 --camera CAM_ENTRY_03

# Checkout camera (purchase detection)
python pipeline/detect.py --video "clips/CAM 5.mp4" --store STORE_PUR_001 --camera CAM_CHECKOUT_05

# Floor cameras (browsing/dwell)
python pipeline/detect.py --video "clips/CAM 1.mp4" --store STORE_PUR_001 --camera CAM_FLOOR_01
python pipeline/detect.py --video "clips/CAM 2.mp4" --store STORE_PUR_001 --camera CAM_FLOOR_02

# Stock room (staff only)
python pipeline/detect.py --video "clips/CAM 4.mp4" --store STORE_PUR_001 --camera CAM_STOCKROOM_04
```

Add `--preview` to any command to see live detection boxes.

### 4. Start the API
```bash
uvicorn api.main:app --reload --port 8000
```

### 5. Load events into the API
```bash
python ingest_events.py
```

### 6. Check metrics
Open in browser:
- http://localhost:8000/metrics
- http://localhost:8000/funnel
- http://localhost:8000/anomalies
- http://localhost:8000/docs  ← interactive API docs

---

## Docker (Part C)

```bash
# Build and run
docker-compose up --build

# API will be available at http://localhost:8000
```

---

## Run Tests (Part C)

```bash
pytest tests/ -v
```

---

## Project Structure

```
store-intelligence/
├── pipeline/
│   └── detect.py          # Detection + tracking pipeline
├── api/
│   └── main.py            # FastAPI REST API
├── tests/
│   └── test_api.py        # API test suite
├── output/
│   ├── events/            # Generated .jsonl files
│   └── retail.db          # SQLite database
├── clips/                 # CCTV video files (not committed)
├── ingest_events.py       # Load events into API
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /ingest | Ingest events from pipeline |
| GET | /metrics | Store-level analytics |
| GET | /funnel | Visitor conversion funnel |
| GET | /anomalies | Unusual pattern detection |

---

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Detection | YOLOv8n | Fast, CPU-friendly, high accuracy |
| Tracking | ByteTrack | Persistent IDs across frames |
| Video I/O | OpenCV | Industry standard |
| API | FastAPI | Fast, auto-docs, Pydantic validation |
| Database | SQLite | Zero-config, sufficient for challenge |
| Container | Docker | Reproducible deployment |
| Tests | pytest | Simple, readable |

## AI Tools Used

- **Claude (Anthropic)** — Architecture design, code generation, debugging
- **YOLOv8 (Ultralytics)** — Pre-trained person detection model
- All AI usage documented in CHOICES.md
- 
## Known Limitations
- Visitor IDs are currently tracked independently per camera.
- Cross-camera re-identification (ReID) is not implemented in this prototype.

Because of this:
- A single customer moving across multiple cameras may receive different visitor IDs.
- Funnel metrics (browse, checkout, exit) may occasionally exceed ENTRY counts.
- Conversion percentages may therefore appear above 100% in some cases.

### Production Improvement

This can be improved by implementing:
- Cross-camera person re-identification using appearance embeddings
- Global visitor identity mapping across all cameras
- Centralized multi-camera tracking pipeline
