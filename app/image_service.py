import os
import uuid
from PIL import Image
import pillow_avif  # registers the plugin automatically
from flask import current_app

_FLAG_RATIO_MIN = 1 / 3  # tallest allowed (1:3)
_FLAG_RATIO_MAX = 3      # widest allowed (3:1)
_FLAG_MAX_DIM   = 600    # cap longest side for file-size

# Fixed output sizes for non-flag image types
_FIXED_SIZES = {
    'banner': (1200, 400),
}

def _flag_output_size(w, h):
    """Return (w, h) preserving the original ratio, clamped to 1:3..3:1, capped at _FLAG_MAX_DIM."""
    ratio = w / h
    if ratio > _FLAG_RATIO_MAX:
        w = round(h * _FLAG_RATIO_MAX)
    elif ratio < _FLAG_RATIO_MIN:
        h = round(w / _FLAG_RATIO_MIN)
    if w > _FLAG_MAX_DIM:
        h = round(h * _FLAG_MAX_DIM / w)
        w = _FLAG_MAX_DIM
    if h > _FLAG_MAX_DIM:
        w = round(w * _FLAG_MAX_DIM / h)
        h = _FLAG_MAX_DIM
    return (w, h)

def process_and_save_image(file_storage, image_type='flag'):
    """
    Process an uploaded image: normalize, resize, and convert to AVIF.
    Flags and alliance_flag preserve original dimensions, clamped to a 1:3..3:1 ratio.
    Banners are resized to a fixed 1200x400.
    Returns: relative path to the saved file or None if failed.
    """
    if not file_storage:
        return None

    try:
        # Open image
        img = Image.open(file_storage)

        # Convert to RGB (strips alpha, prevents issues with some AVIF encoders)
        img = img.convert('RGB')

        if image_type in _FIXED_SIZES:
            target_size = _FIXED_SIZES[image_type]
        else:
            target_size = _flag_output_size(*img.size)

        img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # Ensure upload directories exist
        subfolder = 'banners' if image_type == 'banner' else 'flags'
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
