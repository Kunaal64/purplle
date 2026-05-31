# Design Choices, Trade-offs, and Justifications

This document explains the key engineering decisions, model selections, and API trade-offs made during the development of the Purplle Store Intelligence Challenge.

---

## 1. Detection Model Selection: YOLOv8n (Nano)

### Options Considered
1. **YOLOv8m (Medium) / YOLOv8x (Extra Large)**: Higher parameter count, offering slightly better accuracy on partial occlusions.
2. **YOLOv8n (Nano)**: Lightweight model with 3.2 Million Parameters, optimized for edge-device compute.

### What AI Suggested
The AI suggested using YOLOv8n due to resource constraints inside a Docker container without GPU acceleration. It noted that standard retail CCTV footages have uniform lighting, making a lightweight model sufficient for person class tracking, and that YOLOv8n would run at real-time speeds (>30 FPS) on CPU.

### Final Choice & Justification
We selected **YOLOv8n**. It has an incredibly small memory footprint, starts up instantly, and performs person-detection at near-real-time rates inside standard CPU Docker containers. This ensures the pipeline is accessible, reproducible, and cheap to deploy without requiring expensive host GPU hardware.

---

## 2. Event Schema Design Rationale

### Options Considered
1. **Raw Centroid Coordinate Logging**: Logging coordinate coordinates stream directly to the API, offloading state calculations to the database/backend.
2. **Discrete Event Catalogue (Standardized Schema)**: Defining behavioral events like `ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, and custom queue events like `BILLING_QUEUE_JOIN` containing nested metadata.

### What AI Suggested
The AI recommended a normalized JSON schema where coordinates are processed on the edge by the detection pipeline and emitted as high-level semantic events. It suggested including a `metadata` block to store contextual parameters like `queue_depth` or `session_seq` to keep the database flexible for future analytics.

### Final Choice & Justification
We chose the **Discrete Event Catalogue with a JSON metadata column**. The edge pipeline resolves spatial tracking (checking coordinate overlaps and door crossings) and posts standard events to `/events/ingest`. This prevents overloading the REST API with continuous coordinate updates, keeps network payloads lightweight, and ensures query response times remain under 10ms.

---

## 3. API Database Architecture Choice: SQLite

### Options Considered
1. **PostgreSQL**: Highly concurrent relational database, ideal for production workloads with multiple edge camera nodes writing in parallel.
2. **SQLite**: Serverless, zero-configuration, file-based relational database.

### What AI Suggested
The AI suggested starting with SQLite to avoid multi-container dependency and password configurations during challenge evaluation, noting that SQLite would easily handle the write volume of a single store's event stream.

### Final Choice & Justification
We chose **SQLite** as the API datastore. It runs in-process with FastAPI, requiring zero setup from the end user. It easily supports sub-millisecond query responses for metrics, funnel stages, and anomalies by placing appropriate indexes on the `store_id`, `visitor_id`, `event_type`, and `timestamp` columns. For graceful degradation, we wrapped all operations in an exception handler that returns an HTTP 503 structured body when database connectivity fails, ensuring production-ready stability.
