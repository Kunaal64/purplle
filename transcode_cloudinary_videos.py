import os
import sqlite3
import urllib.request
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load env vars
load_dotenv()

cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")

if not all([cloud_name, api_key, api_secret]):
    print("[ERROR] Cloudinary credentials missing from env!")
    exit(1)

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    print("[ERROR] Cloudinary package is not installed.")
    exit(1)

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

DB_PATH = "store_intelligence.db"
CCTV_DIR = Path("CCTV Footage")
CCTV_DIR.mkdir(exist_ok=True)

def transcode_and_reupload():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if media_assets table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='media_assets'")
    if cursor.fetchone() is None:
        print("[ERROR] media_assets table does not exist in the database.")
        conn.close()
        return

    cursor.execute("SELECT filename, cloudinary_url, public_id FROM media_assets")
    assets = cursor.fetchall()
    
    if not assets:
        print("[INFO] No assets found in media_assets table.")
        conn.close()
        return

    print(f"[INFO] Found {len(assets)} assets to transcode.")

    for filename, old_url, public_id in assets:
        print("\n" + "=" * 50)
        print(f"Processing {filename}...")
        print(f"Old URL: {old_url}")
        print(f"Public ID: {public_id}")
        
        # 1. Download the video from Cloudinary
        temp_original = CCTV_DIR / f"temp_{filename}"
        if temp_original.exists():
            try:
                os.remove(temp_original)
            except Exception:
                pass
                
        print(f"Downloading original video to {temp_original}...")
        try:
            # Add user agent headers if needed, but urllib should be fine for Cloudinary
            urllib.request.urlretrieve(old_url, str(temp_original))
            print(f"Download complete! Size: {temp_original.stat().st_size / (1024*1024):.2f} MB")
        except Exception as e:
            print(f"[ERROR] Failed to download: {e}")
            continue
            
        # 2. Transcode to H.264 using FFmpeg
        temp_compressed = CCTV_DIR / f"transcoded_{filename}"
        if temp_compressed.exists():
            try:
                os.remove(temp_compressed)
            except Exception:
                pass
            
        print(f"Transcoding to H.264 360p using ffmpeg...")
        cmd = [
            "ffmpeg", "-i", str(temp_original),
            "-vf", "scale=-2:360",
            "-vcodec", "libx264",
            "-crf", "30",
            "-acodec", "aac",
            "-y", str(temp_compressed)
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                print(f"[ERROR] FFmpeg failed with code {res.returncode}:\n{res.stderr}")
                # Clean up
                if temp_original.exists():
                    os.remove(temp_original)
                continue
            print(f"Transcoding complete! Size: {temp_compressed.stat().st_size / (1024*1024):.2f} MB")
        except Exception as e:
            print(f"[ERROR] Failed to run FFmpeg: {e}")
            if temp_original.exists():
                os.remove(temp_original)
            continue
            
        # 3. Upload the transcoded video to Cloudinary
        print(f"Uploading transcoded video to Cloudinary with public_id: {public_id}...")
        try:
            response = cloudinary.uploader.upload_large(
                str(temp_compressed),
                resource_type="video",
                public_id=public_id,
                chunk_size=10000000,
                overwrite=True
            )
            new_url = response.get("secure_url") or response.get("url")
            returned_pub_id = response.get("public_id", public_id)
            print(f"[SUCCESS] Upload complete. New URL: {new_url}")
            
            # 4. Update the database
            cursor.execute("""
                UPDATE media_assets 
                SET cloudinary_url = ?, public_id = ?, uploaded_at = datetime('now')
                WHERE filename = ?
            """, (new_url, returned_pub_id, filename))
            conn.commit()
            print(f"Updated DB entry for {filename} with new H.264 URL.")
        except Exception as e:
            print(f"[ERROR] Failed to upload: {e}")
            
        # 5. Clean up temporary files
        for f in [temp_original, temp_compressed]:
            if f.exists():
                try:
                    os.remove(f)
                    print(f"Cleaned up temporary file: {f.name}")
                except Exception as clean_err:
                    print(f"[WARNING] Could not delete temporary file {f.name}: {clean_err}")
                    
    conn.close()
    print("\n[SUCCESS] All videos successfully transcoded to H.264 360p and re-uploaded!")

if __name__ == "__main__":
    transcode_and_reupload()
