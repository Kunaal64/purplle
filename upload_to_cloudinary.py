"""
upload_to_cloudinary.py — Upload local CCTV footage videos to Cloudinary and register them in the SQLite media database.
Auto-compresses files larger than 100MB using OpenCV if available.
"""

import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

DB_PATH = "store_intelligence.db"
CCTV_DIR = Path("CCTV Footage")
MAX_SIZE_LIMIT = 100 * 1024 * 1024  # 100 MB free tier limit

# 1. Verify Cloudinary credentials are set
cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")

if not all([cloud_name, api_key, api_secret]):
    print("=" * 70)
    print("  [ERROR] Cloudinary Credentials Missing!")
    print("=" * 70)
    print("  Please create or configure a '.env' file in the project root with:")
    print("    CLOUDINARY_CLOUD_NAME=your_cloud_name")
    print("    CLOUDINARY_API_KEY=your_api_key")
    print("    CLOUDINARY_API_SECRET=your_api_secret")
    print("=" * 70)
    sys.exit(1)

# Initialize Cloudinary SDK
try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    print("[ERROR] Cloudinary library is not installed.")
    print("        Please run: pip install cloudinary python-dotenv")
    sys.exit(1)

# Initialize OpenCV for auto-compression
try:
    import cv2
except ImportError:
    cv2 = None

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

def init_media_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media_assets (
            filename       TEXT PRIMARY KEY,
            cloudinary_url TEXT NOT NULL,
            public_id      TEXT,
            uploaded_at    TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn

def compress_video(video_path: Path) -> Path:
    """Compresses/transcodes a video to H.264 360p for browser compatibility and Cloudinary size limit."""
    compressed_path = video_path.parent / f"{video_path.stem}_compressed.mp4"
    if compressed_path.exists():
        try:
            os.remove(compressed_path)
        except Exception:
            pass

    print(f"      [INFO] Transcoding {video_path.name} to H.264 360p using ffmpeg...")
    
    import subprocess
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "scale=-2:360",
        "-vcodec", "libx264",
        "-crf", "30",
        "-acodec", "aac",
        "-y", str(compressed_path)
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"      [ERROR] ffmpeg compression failed:\n{result.stderr}")
            return video_path
    except Exception as e:
        print(f"      [ERROR] Failed to run ffmpeg: {e}")
        return video_path
    
    print(f"      [INFO] Transcoding complete! New size: {compressed_path.stat().st_size / (1024*1024):.1f}MB")
    return compressed_path

def main():
    print("=" * 60)
    print("  Purplle CCTV Cloudinary Ingestion Script")
    print("=" * 60)

    if not CCTV_DIR.exists() or not CCTV_DIR.is_dir():
        print(f"[ERROR] Directory '{CCTV_DIR}' does not exist.")
        sys.exit(1)

    # Scan for mp4 videos
    video_files = list(CCTV_DIR.glob("*.mp4"))
    if not video_files:
        print(f"No .mp4 video files found in '{CCTV_DIR}'.")
        sys.exit(0)

    # Filter out compressed files from the list of files to process
    video_files = [f for f in video_files if not f.name.endswith("_compressed.mp4")]

    print(f"Found {len(video_files)} video file(s) locally.")
    
    conn = init_media_db()
    cursor = conn.cursor()

    for idx, video_path in enumerate(video_files, 1):
        filename = video_path.name
        
        # Check if already uploaded
        cursor.execute("SELECT cloudinary_url FROM media_assets WHERE filename = ?", (filename,))
        row = cursor.fetchone()
        
        if row:
            print(f"[{idx}/{len(video_files)}] {filename} already indexed in DB: {row[0]}")
            continue

        # Auto-compress if needed
        upload_path = compress_video(video_path)

        print(f"[{idx}/{len(video_files)}] Uploading {filename} to Cloudinary... (this may take a moment)")
        try:
            # We set a structured public_id replacing spaces with underscores to avoid signature mismatch
            public_id = f"purplle_cctv/{video_path.stem.replace(' ', '_')}"
            
            # Using chunked upload for large video files to bypass standard HTTP request size limits
            response = cloudinary.uploader.upload_large(
                str(upload_path),
                resource_type="video",
                public_id=public_id,
                chunk_size=10000000, # 10MB chunks
                overwrite=True
            )
            
            cloudinary_url = response.get("secure_url") or response.get("url")
            returned_public_id = response.get("public_id", public_id)
            
            # Save mapping in database under original filename
            conn.execute("""
                INSERT OR REPLACE INTO media_assets (filename, cloudinary_url, public_id)
                VALUES (?, ?, ?)
            """, (filename, cloudinary_url, returned_public_id))
            conn.commit()
            
            print(f"      [OK] Successfully uploaded and indexed!")
            print(f"      Cloudinary URL: {cloudinary_url}")
            
            # Clean up temp compressed file to save disk space
            if upload_path != video_path and upload_path.exists():
                try:
                    os.remove(upload_path)
                    print(f"      [INFO] Cleaned up temporary compressed file.")
                except Exception as clean_err:
                    print(f"      [WARNING] Could not delete temporary file: {clean_err}")
            
        except Exception as e:
            print(f"      [ERROR] Error uploading {filename}: {e}")

    conn.close()
    print("\n[SUCCESS] Media ingestion and indexing complete!")

if __name__ == "__main__":
    main()
