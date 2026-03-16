"""
Migration script to convert external image URLs (flags/banners) into 
internally hosted and processed AVIF files.

Run from project root:
    python3 adhoc/migrate_images.py
"""

import os
import sys
from io import BytesIO
import urllib.request
from PIL import Image

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import app
from app import db
from app.models import Nation, Alliance
from app.image_service import process_and_save_image

def is_external(url):
    if not url:
        return False
    return url.startswith('http://') or url.startswith('https://')

def download_image(url):
    """Download image and return a BytesIO object."""
    try:
        # User-agent to avoid being blocked by some hosts
        headers = {'User-Agent': 'Mozilla/5.0 (NationsEngine-Migration-Bot/1.0)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return BytesIO(response.read())
    except Exception as e:
        print(f"  Failed to download {url}: {e}")
        return None

def migrate():
    with app.app_context():
        print("--- Migrating Nation Flags ---")
        nations = Nation.query.all()
        for nation in nations:
            if is_external(nation.flag_url):
                print(f"Processing flag for {nation.name} ({nation.flag_url})...")
                buffer = download_image(nation.flag_url)
                if buffer:
                    new_path = process_and_save_image(buffer, 'flag')
                    if new_path:
                        nation.flag_url = new_path
                        print(f"  Success: {new_path}")
                    else:
                        print("  Failed to process image.")
        
        print("
--- Migrating Nation Banners ---")
        for nation in nations:
            if is_external(nation.banner_url):
                print(f"Processing banner for {nation.name} ({nation.banner_url})...")
                buffer = download_image(nation.banner_url)
                if buffer:
                    new_path = process_and_save_image(buffer, 'banner')
                    if new_path:
                        nation.banner_url = new_path
                        print(f"  Success: {new_path}")
                    else:
                        print("  Failed to process image.")

        print("
--- Migrating Alliance Flags ---")
        alliances = Alliance.query.all()
        for alliance in alliances:
            if is_external(alliance.flag_url):
                print(f"Processing flag for alliance {alliance.name} ({alliance.flag_url})...")
                buffer = download_image(alliance.flag_url)
                if buffer:
                    new_path = process_and_save_image(buffer, 'alliance_flag')
                    if new_path:
                        alliance.flag_url = new_path
                        print(f"  Success: {new_path}")
                    else:
                        print("  Failed to process image.")

        db.session.commit()
        print("
Migration complete.")

if __name__ == '__main__':
    migrate()
