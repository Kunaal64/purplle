import subprocess
import sys
import sqlite3
from pathlib import Path

def main():
    cameras = [
        {"video": "CCTV Footage/CAM 3.mp4", "camera_id": "CAM_ENTRY_03"},
        {"video": "CCTV Footage/CAM 5.mp4", "camera_id": "CAM_CHECKOUT_05"},
        {"video": "CCTV Footage/CAM 1.mp4", "camera_id": "CAM_FLOOR_01"},
        {"video": "CCTV Footage/CAM 2.mp4", "camera_id": "CAM_FLOOR_02"},
        {"video": "CCTV Footage/CAM 4.mp4", "camera_id": "CAM_STOCKROOM_04"},
    ]

    print("=" * 60)
    print("  Purplle CCTV Store Intelligence - Master Pipeline")
    print("=" * 60)

    # Connect to SQLite database to check for Cloudinary URLs
    conn = sqlite3.connect("store_intelligence.db")
    cursor = conn.cursor()
    
    # Check if media_assets table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='media_assets'")
    has_media_assets = cursor.fetchone() is not None

    for cam in cameras:
        filename = Path(cam["video"]).name
        video_source = None

        if has_media_assets:
            cursor.execute("SELECT cloudinary_url FROM media_assets WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if row and row[0]:
                video_source = row[0]
                print(f"\n[INFO] Streaming {filename} from Cloudinary: {video_source}")

        if not video_source:
            # Fallback to local files
            video_path = Path(cam["video"])
            if video_path.exists():
                video_source = str(video_path)
                print(f"\n[INFO] Using local file for {filename}")
            else:
                print(f"\n[ERROR] Video file not found locally and not indexed in Cloudinary: {filename}")
                continue

        cmd = [
            "python", "pipeline/detect.py",
            "--video", video_source,
            "--store", "STORE_PUR_001",
            "--camera", cam["camera_id"]
        ]
        print(f"\n[RUNNING] Processing {cam['camera_id']}...")
        print(f"Command: {' '.join(cmd)}\n")
        
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"\n[ERROR] Pipeline failed on camera {cam['camera_id']} with code {res.returncode}")
            sys.exit(res.returncode)

    conn.close()

    print("\n" + "=" * 60)
    print("  Ingesting newly generated event logs into database...")
    print("=" * 60 + "\n")
    
    ingest_cmd = ["python", "ingest_events.py"]
    res = subprocess.run(ingest_cmd)
    if res.returncode != 0:
        print(f"\n[ERROR] Event ingestion failed with code {res.returncode}")
        sys.exit(res.returncode)

    print("\n[SUCCESS] All pipeline executions and event ingestions completed successfully!")

if __name__ == "__main__":
    main()
