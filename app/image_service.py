import os
import uuid
from PIL import Image
import pillow_avif  # registers the plugin automatically
from flask import current_app

def process_and_save_image(file_storage, image_type='flag'):
    """
    Process an uploaded image: normalize, resize, and convert to AVIF.
    image_type: 'flag' (320x200) or 'banner' (1200x400)
    Returns: relative path to the saved file or None if failed.
    """
    if not file_storage:
        return None

    # Configurable dimensions
    SIZES = {
        'flag': (320, 200),
        'banner': (1200, 400),
        'alliance_flag': (320, 200),
    }
    
    target_size = SIZES.get(image_type, (320, 200))
    
    try:
        # Open image
        img = Image.open(file_storage)
        
        # Convert to RGB (strips alpha if needed, prevents issues with some AVIF encoders)
        # Note: If you want to keep transparency for flags, use 'RGBA'
        img = img.convert('RGB')
        
        # Resize using Lanczos for high quality
        # Maintain aspect ratio? For flags/banners, usually better to force or crop.
        # Here we'll use thumbnail + padding or just resize. 
        # For simple gaming flags, forcing dimensions is often expected.
        img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # Ensure upload directories exist
        subfolder = 'flags' if image_type == 'flag' else 'banners'
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.avif"
        relative_path = f"/uploads/{subfolder}/{filename}"
        absolute_path = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder, filename)
        
        # Save as AVIF
        # Quality 65 is excellent for AVIF
        img.save(absolute_path, 'AVIF', quality=65, speed=6)
        
        return relative_path
        
    except Exception as e:
        current_app.logger.error(f"Image processing failed: {str(e)}")
        return None

def delete_old_image(relative_path):
    """Delete a previously uploaded image from disk."""
    if not relative_path or not relative_path.startswith('/uploads/'):
        return
    
    # Remove leading slash and 'uploads/' to match physical path
    # relative_path is e.g. /uploads/flags/xyz.avif
    # We need to map this back to Config['UPLOAD_FOLDER']
    parts = relative_path.strip('/').split('/')
    if len(parts) < 3:
        return
        
    filename = parts[-1]
    subfolder = parts[-2]
    
    absolute_path = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder, filename)
    
    if os.path.exists(absolute_path):
        try:
            os.remove(absolute_path)
        except Exception as e:
            current_app.logger.error(f"Failed to delete image {absolute_path}: {str(e)}")
