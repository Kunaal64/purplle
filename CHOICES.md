# Design Choices, Trade-offs, and Justifications

This document explains the key engineering decisions, model selections, and API trade-offs made during the development of the Purplle Store Intelligence Challenge. It provides deeper context into why specific technologies were chosen over alternatives.

---

## 1. Detection Model Selection: YOLOv8n (Nano)

### Options Considered
1. **YOLOv8m (Medium) / YOLOv8x (Extra Large)**: Higher parameter count, offering slightly better accuracy on partial occlusions and smaller objects at a distance.
2. **YOLOv8n (Nano)**: Lightweight model with 3.2 Million Parameters, optimized for edge-device compute.
3. **Faster R-CNN**: Highly accurate two-stage detector, but computationally heavy and not suitable for real-time without GPU.

### What AI Suggested
The AI suggested using YOLOv8n due to resource constraints inside a standard Docker container without GPU acceleration. It noted that retail CCTV footages generally have uniform lighting and consistent angles, making a lightweight model sufficient for robust person class tracking. Most importantly, YOLOv8n runs at real-time speeds (>30 FPS) on CPU.

### Final Choice & Justification
We selected **YOLOv8n**. It has an incredibly small memory footprint, starts up near-instantly, and performs person-detection at real-time rates inside standard CPU Docker containers. This ensures the pipeline is accessible, reproducible, and cheap to deploy without requiring expensive host GPU hardware. The slight trade-off in accuracy during severe occlusion is mitigated by ByteTrack's robust Kalman filter predictions, which interpolate missing detections.

---

## 2. Event Schema Design Rationale

### Options Considered
1. **Raw Centroid Coordinate Logging**: Logging coordinate coordinates stream directly to the API, offloading state calculations to the database/backend (e.g., emitting `{"x": 100, "y": 200, "timestamp": ...}` every frame).
2. **Discrete Event Catalogue (Standardized Schema)**: Defining behavioral events like `ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, and custom events, generated at the edge.

### What AI Suggested
The AI recommended a normalized JSON schema where coordinates are processed on the edge by the detection pipeline and emitted as high-level semantic events. It suggested including a `metadata` block to store contextual parameters like `queue_depth` or `session_seq` to keep the database flexible for future analytics.

### Final Choice & Justification
We chose the **Discrete Event Catalogue with a JSON metadata column**. The edge pipeline resolves spatial tracking (checking coordinate overlaps and door crossings) and posts standard events to the `/events/ingest` endpoint. This prevents overloading the REST API with continuous coordinate updates, keeps network payloads lightweight, and ensures query response times remain under 10ms. Edge processing reduces bandwidth costs significantly.

---

## 3. API Database Architecture Choice: SQLite

### Options Considered
1. **PostgreSQL**: Highly concurrent relational database, ideal for production workloads with multiple edge camera nodes writing in parallel. Requires a separate container and volume management.
2. **SQLite**: Serverless, zero-configuration, file-based relational database.
3. **MongoDB/NoSQL**: Good for unstructured event data, but complex to set up and less suited for the analytical aggregations (GROUP BY, JOIN) required for the metrics endpoints.

### What AI Suggested
The AI suggested starting with SQLite to avoid multi-container dependency and password configurations during challenge evaluation, noting that SQLite would easily handle the write volume of a single store's event stream.

### Final Choice & Justification
We chose **SQLite** as the API datastore. It runs in-process with FastAPI, requiring zero setup from the end user. It easily supports sub-millisecond query responses for metrics, funnel stages, and anomalies by placing appropriate indexes on the `store_id`, `visitor_id`, `event_type`, and `timestamp` columns. For graceful degradation, we wrapped all operations in an exception handler that returns an HTTP 503 structured body when database connectivity fails, ensuring production-ready stability. If this were to scale to thousands of stores, migration to PostgreSQL would be straightforward due to the standard SQL schema.

---

## 4. Instructions to Run

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

#### 3. Run the Pipeline
We provide a convenient script to run the detection pipeline across all videos:
```bash
python run_pipeline_all.py
```
*Note: Ensure the `CCTV Footage` directory contains the required `.mp4` video files.*

Alternatively, run individual cameras:
```bash
python pipeline/detect.py --video "CCTV Footage/CAM 1.mp4" --store STORE_PUR_001 --camera CAM_FLOOR_01
```
Add `--preview` to any command to see live detection boxes.

#### 4. Start the FastAPI Server
Run the backend server to process events and serve analytics:
```bash
uvicorn api.main:app --reload --port 8000
```

#### 5. Ingest Events to the Database
Once the API is running, open a new terminal window, activate the virtual environment, and run the ingestion script to load the generated event logs into the SQLite database:
```bash
python ingest_events.py
```

#### 6. View Analytics
Access the API endpoints to view the insights in your browser:
- **Metrics**: http://localhost:8000/metrics
- **Funnel**: http://localhost:8000/funnel
- **Anomalies**: http://localhost:8000/anomalies
- **Swagger UI**: http://localhost:8000/docs (Interactive API documentation)

### Docker Deployment (Part C)
To run the entire application stack (API) using Docker:
```bash
docker-compose up --build
```
The API will be available at http://localhost:8000.
