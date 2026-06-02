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

## Instructions to Run

### Local Setup

#### 1. Prerequisites
- Python 3.10+
- Git
- Docker and Docker Compose (optional, for containerized run)

#### 2. Install Dependencies
Create a virtual environment and install the required packages:
```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

#### 3. Verify setup
```bash
python -c "from ultralytics import YOLO; m = YOLO('yolov8n.pt'); print('Ready!')"
```

#### 4. Run the Pipeline
We provide a convenient script to run the detection pipeline across all videos:
```bash
python run_pipeline_all.py
```
*Note: Ensure the `CCTV Footage` directory contains the required `.mp4` video files.*

Alternatively, run individual cameras:
```bash
# Entry camera (visitor counting)
python pipeline/detect.py --video "CCTV Footage/CAM 3.mp4" --store STORE_PUR_001 --camera CAM_ENTRY_03

# Checkout camera (purchase detection)
python pipeline/detect.py --video "CCTV Footage/CAM 5.mp4" --store STORE_PUR_001 --camera CAM_CHECKOUT_05

# Floor cameras (browsing/dwell)
python pipeline/detect.py --video "CCTV Footage/CAM 1.mp4" --store STORE_PUR_001 --camera CAM_FLOOR_01
python pipeline/detect.py --video "CCTV Footage/CAM 2.mp4" --store STORE_PUR_001 --camera CAM_FLOOR_02

# Stock room (staff only)
python pipeline/detect.py --video "CCTV Footage/CAM 4.mp4" --store STORE_PUR_001 --camera CAM_STOCKROOM_04
```

Add `--preview` to any command to see live detection boxes.

#### 5. Start the FastAPI Server
Run the backend server to process events and serve analytics. Open a new terminal window, activate the virtual environment, and run:
```bash
uvicorn api.main:app --reload --port 8000
```

#### 6. Ingest Events to the Database
Once the API is running, open another terminal window, activate the virtual environment, and run the ingestion script to load the generated event logs into the SQLite database:
```bash
python ingest_events.py
```

#### 7. View Analytics
Access the API endpoints to view the insights in your browser:
- **Metrics**: http://localhost:8000/metrics
- **Funnel**: http://localhost:8000/funnel
- **Anomalies**: http://localhost:8000/anomalies
- **Swagger UI**: http://localhost:8000/docs (Interactive API documentation)

---

## Docker Deployment (Part C)

To run the entire application stack (API) using Docker:
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
├── CCTV Footage/          # CCTV video files (not committed)
├── ingest_events.py       # Load events into API
├── run_pipeline_all.py    # Run all pipeline scripts
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

