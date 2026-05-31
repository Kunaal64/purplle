> **ENGINEERING** **HIRING** **CHALLENGE**
>
> PROBLEM STATEMENT

||
||
||
||
||
||
||
||
||

> **Read** **This** **First**
>
> This challenge is end-to-end by design. You start with raw camera
> footage and you finish with a working analytics API. There is no
> pre-processed dataset, no skeleton code, and no guardrails on how you
> build the pipeline in between. **Every** **architectural**
> **decision** **from** **frame** **to** **API** **response** **is**
> **yours** **to** **make.**
>
> We are not testing whether you know a specific library. We are testing
> whether you can **decompose** **a** **real** **problem,** **pick**
> **the** **right** **tools,** **build** **something** **that**
> **works,** **and** **explain** **every** **decision** **you**
> **made.**

**1.** **The** **Business** **Problem**

A specialty retail chain — **Apex** **Retail** — operates 40 physical
stores across 8 cities. Their online channel has mature analytics: every
session, click, and drop-off is tracked in real time. Their offline
stores are a complete data blind spot.

Your job is to build system — starting from the raw camera footage.

**2.** **What** **You** **Are** **Building**

You are building a complete pipeline — from raw video to live store
analytics. The diagram below shows the full system. Every stage is yours
to design and implement:

> 📹 **Raw** **CCTV**
>
> **Clips**
>
> Your input

🔍 **→Detection** **Layer** **→**

> You build this

⚡ **Event** **Stream**

> You design this

🧠 📊 **→Intelligence** **API** **→Live** **Dashboard**

> You build this You ship this

||
||
||
||
||
||
||

**3.** **The** **Dataset**

**3.1** **What** **You** **Receive**

You will receive a ZIP archive containing:

> • **CCTV** **clips** **—** **5** **stores,** **3** **camera**
> **angles** **each,** **20** **minutes** **per** **clip** (Entry
> camera, Main floor camera, Billing area camera)
>
> • **store_layout.json** — zone definitions for each store: zone names,
> camera coverage, and open hours
>
> • **pos_transactions.csv** — timestamped POS transaction records
> (store ID, amount, timestamp — no customer identity)
>
> • **sample_events.jsonl** — 200 example events in the expected output
> schema to help you validate your detection layer
>
> • **assertions.py** — 10 example test assertions your API must pass
> (not the full scoring test suite)

**3.2** **Video** **Clip** **Specifications**

||
||
||
||
||
||
||
||
||
||

**3.3** **Known** **Challenges** **in** **the** **Footage**

The clips are realistic — they include the same edge cases you would
encounter in a production deployment. Handling them is part of the
challenge:

||
||
||
||
||
||
||
||

||
||
||
||

**3.4** **POS** **Transactions**

pos_transactions.csv contains records in the format:

> **POS** **Schema**
>
> store_id, transaction_id, timestamp, basket_value_inr STORE_BLR_002,
> TXN_00441, 2026-03-03T14:38:12Z, 1240.00 STORE_BLR_002, TXN_00442,
> 2026-03-03T14:41:55Z, 680.00

Your pipeline must correlate POS transactions with visitor sessions to
compute conversion rate. There is no customer_id in the POS data —
correlation is done by **time** **window** **+** **store**. A visitor
who was in the billing zone in the 5-minute window before a transaction
timestamp counts as a converted visitor for that session.

**4.** **What** **to** **Build**

**Part** **A** **—** **Detection** **Pipeline** **\[30** **points\]**

> **The** **Goal**
>
> Process the CCTV clips and produce a stream of structured behavioural
> events. Your detection pipeline is the foundation — everything else
> depends on the quality of what it emits.

You choose the model, framework, and architecture. The output must be
structured events in the schema below. Use any combination of tools:

> • Object detection models: YOLOv8, YOLOv9, RT-DETR, MediaPipe, or any
> other • Tracking: ByteTrack, DeepSORT, StrongSORT, or custom
>
> • Re-ID: any OSNet / torchreid model, or a distance-based approach
> using bounding box trajectory
>
> • LLMs / VLMs: use them for zone classification, staff detection, or
> anything else you find useful

**Required** **Output** **Schema**

> **Event** **Schema** **(your** **pipeline** **must** **emit**
> **this)** {
>
> "event_id": "uuid-v4", // you generate this — must be globally unique
> "store_id": "STORE_BLR_002", // from store_layout.json
>
> "camera_id": "CAM_ENTRY_01", // which camera produced this event
>
> "visitor_id": "VIS_c8a2f1",
>
> "event_type": "ZONE_DWELL",

// your Re-ID token — unique per visit session

> // see catalogue below
>
> "timestamp": "2026-03-03T14:22:10Z", // ISO-8601 UTC — derived from
> clip + frame offset
>
> "zone_id":
>
> "dwell_ms":

"SKINCARE",

> 8400,
>
> // null for ENTRY / EXIT events

// duration; 0 for instantaneous events

> "is_staff": false, // your model must classify this
>
> "confidence": 0.91, "metadata": {
>
> "queue_depth": null,

// your detection confidence — do not suppress low-conf events

> // integer; you populate for BILLING_QUEUE_JOIN
>
> "sku_zone": "MOISTURISER", // zone label from store_layout.json
> "session_seq": 5 // ordinal position of this event in visitor session
>
> } }

**Event** **Type** **Catalogue**

||
||
||
||
||
||
||
||
||
||
||

**Detection** **Scoring** **Criteria**

||
||
||
||
||
||
||
||
||

**Part** **B** **—** **Intelligence** **API** **\[35** **points\]**

> **The** **Goal**
>
> Build a REST API that ingests the events your detection pipeline
> emits, computes real-time store analytics, detects operational
> anomalies, and exposes a queryable intelligence surface.

||
||
||
||
||
||
||
||
||

**Part** **C** **—** **Production** **Readiness** **\[20** **points\]**

The API must be built as if it will be operated by a team that did not
write it:

> • **Containerised:** docker compose up starts everything. No manual
> steps beyond git clone.
>
> • **Structured** **logging:** Every request logs: trace_id, store_id,
> endpoint, latency_ms, event_count (for ingest), status_code.
>
> • **Idempotency:** POST /events/ingest is safe to call twice with the
> same payload. Tests must verify this.
>
> • **Graceful** **degradation:** Database unavailable → HTTP 503 with
> structured body. No raw stack traces in responses.
>
> • **Tests:** Statement coverage \>70%. Edge cases: empty store,
> all-staff clip, zero purchases, re-entry in funnel.
>
> • **README:** Setup complete in 5 commands. Includes how to run the
> detection pipeline against the clips and feed output into the API.

**Part** **D** **—** **AI** **Engineering** **\[15** **points\]**

This is evaluated for how you used AI — not whether you used it. Depth
and intentionality score more than volume:

||
||
||
||
||
||
||

**Part** **E** **—** **Live** **Dashboard** **\[+10** **bonus**
**points\]**

Run your detection pipeline on a clip in real time (or simulated real
time) and show at least one store metric updating live on screen. This
can be a terminal dashboard (rich, curses) or a web UI. We are looking
for proof that the pipeline and API are genuinely connected, not just

batch-processed.

**5.** **Scoring**

**5.1** **Point** **Breakdown**

||
||
||
||
||
||
||
||
||
||
||
||
||
||
||

**5.2** **Acceptance** **Gate**

A submission is scored only if it passes all of the following:

> 1\. **Runs:** docker compose up starts the API. No manual steps beyond
> git clone.
>
> 2\. **Produces** **events:** The README explains how to run the
> detection pipeline against the clips and where the output goes.
>
> 3\. **Ingests:** POST /events/ingest accepts events without a 5xx
> response.
>
> 4\. **Responds:** GET /stores/STORE_BLR_002/metrics returns a valid
> JSON response.
>
> 5\. **Documents:** DESIGN.md and CHOICES.md both exist and are
> non-trivial (\>250 words each).

Submissions that fail the gate get a 12-hour fix window before scoring
begins.

**5.3** **Contextual** **Follow-Up** **Questions**

After submission, you receive 5 questions generated from your specific
code and CHOICES.md. You answer in a 30-minute async video. The
questions are designed so that someone who genuinely built the system
answers each in under 2 minutes. Examples:

> **Examples** **of** **the** **Kind** **of** **Questions** **Asked**
>
> 6\. "You used YOLOv8 for detection. Walk me through what you tried
> when it struggled with the partial occlusion cases in the billing
> clip."
>
> 7\. "Your visitor_id assignment uses bounding box trajectory. What
> breaks when a customer leaves and a different customer enters from the
> same direction 3 seconds later?"
>
> 8\. "Your /funnel endpoint is accurate for the test clips. At 40 live
> stores sending events in real time, what is the first thing that
> breaks?"
>
> 9\. "In CHOICES.md you said you considered using a VLM for zone
> classification but chose rule-based instead. What would make you
> change that decision?"

These questions cannot be answered generically — they require you to
reason about your own submitted code. This is intentional.

**6.** **AI** **Usage** **Policy**

> **Use** **Every** **Tool** **You** **Have**
>
> Claude, ChatGPT, Cursor, GitHub Copilot, Gemini — use all of them. AI
> tools are not just allowed, they are **expected**. We specifically
> evaluate how you use AI, not whether you avoid it.
>
> What matters: Do you use AI to build something **better**? Do you
> critique its output? Can you explain and defend every line it helped
> you write? A candidate who uses AI intelligently to solve the hard
> parts (detection model selection, schema design, edge case handling)
> and documents that process scores higher than one who hand-codes
> boilerplate but ignores it for the interesting parts.

||
||
||
||
||
||

||
||
||

**7.** **Submission**

**7.1** **Suggested** **Repository** **Structure**

> **Suggested** **Layout** /store-intelligence/ ├── pipeline/
>
> │ ├── detect.py │ ├── tracker.py │ ├── emit.py
>
> │ └── run.sh
>
> \# Main detection + tracking script \# Re-ID / tracking logic
>
> \# Event schema + emission

\# One command to process all clips → events

> ├── app/
>
> │ ├── main.py
>
> │ ├── models.py │ ├── ingestion.py │ ├── metrics.py │ ├── funnel.py
>
> │ ├── anomalies.py
>
> │ └── health.py

\# FastAPI entrypoint

> \# Pydantic event schema \# Ingest, dedup

\# Real-time metric computation \# Funnel + session logic

> \# Anomaly detection
>
> ├── tests/
>
> │ ├── test_pipeline.py \# Include prompt block header │ ├──
> test_metrics.py
>
> │ └── test_anomalies.py ├── docs/
>
> │ ├── DESIGN.md
>
> │ └── CHOICES.md

\# Architecture + AI-assisted decisions

> \# 3 decisions with full reasoning
>
> ├── docker-compose.yml └── README.md

The structure is a suggestion — if your architecture dictates something
different, explain it in DESIGN.md. We do not penalise deviation from
the suggested layout.

**7.2** **Submission** **Checklist**

> • Git repository link (private — invite reviewer handle provided in
> challenge email) • docker compose up confirmed working on a clean
> machine before submission
>
> • README.md explains how to run the detection pipeline against the
> clips
>
> • DESIGN.md includes 'AI-Assisted Decisions' section
>
> • CHOICES.md covers: model selection, schema design, one API decision
> • Prompt blocks at top of each test file
>
> • If doing Part E (dashboard): local URL noted in README.md

**8.** **North** **Star**

Every component you build connects to a single business metric:

> **North** **Star** **Metric:** **Offline** **Store** **Conversion**
> **Rate**
>
> Conversion Rate = Visitors who completed a purchase ÷ Total unique
> visitors in a session window
>
> Every stage of your pipeline either improves the accuracy of this
> number (detection layer) or makes it actionable (API layer). When you
> make a design trade-off, ask yourself: does this make the metric more
> accurate or more useful?

||
||
||
||
||
||
||
||
||

**9.** **FAQ**

||
||
||

||
||
||
||
||
||
||
||
||
||
||

> **Contact** **&** **Timing**
>
> Your 48-hour window begins at the timestamp of your dataset download
> confirmation email.
>
> Questions: hiring-challenge@\[company\].com · Response SLA: 4 hours
> (10am–7pm IST)
>
> Good luck. Ship something you are proud of.
