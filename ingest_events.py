"""
ingest_events.py — Load generated .jsonl files into the API
Run this AFTER detect.py has processed all camera clips.

Usage:
    python ingest_events.py
    python ingest_events.py --events_dir output/events --api http://localhost:8000
"""

import json
import httpx
import argparse
from pathlib import Path

def ingest(events_dir: str, api_url: str):
    events_path = Path(events_dir)
    jsonl_files = list(events_path.glob("*.jsonl"))

    if not jsonl_files:
        print(f"[ERROR] No .jsonl files found in {events_dir}")
        print("        Run detect.py on your camera clips first!")
        return

    print(f"\nFound {len(jsonl_files)} event file(s) to ingest:\n")

    total_accepted = 0
    total_rejected = 0

    for jsonl_file in jsonl_files:
        events = []
        with open(jsonl_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        print(f"  {jsonl_file.name}: {len(events)} events")

        batch_size = 500
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            resp = httpx.post(
                f"{api_url}/ingest/batch",
                json=batch,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                total_accepted += data["accepted"]
                total_rejected += data["rejected"]
            else:
                print(f"    [ERROR] {resp.status_code}: {resp.text}")

    print(f"\n{'='*50}")
    print(f"  Ingestion Complete")
    print(f"  Accepted : {total_accepted}")
    print(f"  Rejected : {total_rejected}")
    print(f"{'='*50}")
    print(f"\nNow check your metrics:")
    print(f"  {api_url}/metrics")
    print(f"  {api_url}/funnel")
    print(f"  {api_url}/anomalies\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--events_dir", default="output/events")
    parser.add_argument("--api",        default="http://localhost:8000")
    args = parser.parse_args()
    ingest(args.events_dir, args.api)
