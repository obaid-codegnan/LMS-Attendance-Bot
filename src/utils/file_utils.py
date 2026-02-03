"""
File utility functions.
"""
import os
import logging
from pathlib import Path
from datetime import datetime
from src.config.settings import Config
from src.utils.image_utils import resize_frame, encode_jpeg

logger = logging.getLogger(__name__)


def generate_filename(prefix: str = "capture", extension: str = None) -> str:
    """
    Generate unique filename with timestamp.
    """
    extension = extension or Config.IMAGE_FORMAT
    if not extension.startswith('.'):
        extension = f'.{extension}'
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}{extension}"
    
    return os.path.join(Config.UPLOAD_FOLDER, filename)


def generate_face_filename(index: int, extension: str = None) -> str:
    """
    Generate unique filename for a face crop.
    """
    return generate_filename(prefix=f"face_{index}", extension=extension)


def generate_student_filename(student_id: str, student_name: str, extension: str) -> str:
    """
    Generate filename for a student image, sanitized.
    """
    ext = extension if extension.startswith('.') else f".{extension}"
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else "_" for c in student_name.strip() or "student")
    safe_id = "".join(c if c.isalnum() or c in ('-', '_') else "_" for c in student_id.strip() or "id")
    prefix = f"student_{safe_id}_{safe_name}"
    return generate_filename(prefix=prefix, extension=ext)


def ensure_upload_directory() -> None:
    """Ensure upload directory exists."""
    Path(Config.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)


def process_and_upload_face(
    face_img, 
    drive_service, 
    folder_id: str, 
    file_name: str
) -> bool:
    """
    Resize, encode, save to temp file, and upload a face image to Drive.
    """
    try:
        # Resize and Encode using new utils
        face_img = resize_frame(face_img)
        success, warning, buffer = encode_jpeg(face_img)
        
        if not success or buffer is None:
            logger.warning(f"Failed to encode face {file_name}: {warning}")
            return False
            
        # Create a temporary local file
        temp_path = Path(Config.UPLOAD_FOLDER) / file_name
        temp_path.write_bytes(buffer.tobytes())
        
        # Upload
        up_success, fid, err = drive_service.upload_file(
            str(temp_path),
            file_name=file_name,
            parent_id=folder_id
        )
        
        # Cleanup temp file
        try:
            temp_path.unlink()
        except Exception:
            pass
            
        if not up_success:
            logger.error(f"Failed to upload {file_name}: {err}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error processing/uploading {file_name}: {e}")
        return False
