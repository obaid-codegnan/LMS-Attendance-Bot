"""
Image processing utilities.
Extracted from CameraService to decouple dependencies.
"""
import logging
from typing import Tuple, Optional
import cv2
import numpy as np
from src.config.settings import Config

logger = logging.getLogger(__name__)

def resize_frame(frame: np.ndarray) -> np.ndarray:
    """
    Resize the frame to fit within Config.IMAGE_MAX_WIDTH/HEIGHT 
    while maintaining aspect ratio.
    
    Args:
        frame: Input image frame
        
    Returns:
        Resized frame
    """
    if frame is None or frame.size == 0:
        logger.warning("Invalid frame provided to resize_frame")
        return frame
        
    max_w = Config.IMAGE_MAX_WIDTH
    max_h = Config.IMAGE_MAX_HEIGHT
    
    height, width = frame.shape[:2]
    
    # Calculate scale to fit both dimensions
    scale = min(max_w / width, max_h / height, 1.0)
    
    if scale < 1.0:
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
    return frame

def encode_jpeg(frame: np.ndarray) -> Tuple[bool, Optional[str], Optional[np.ndarray]]:
    """
    Compress frame to JPEG, attempting to stay under Config.TARGET_IMAGE_KB.
    Dynamically adjusts quality.
    
    Args:
        frame: Input image frame
        
    Returns:
        Tuple of (Success, Warning Message, Encoded Buffer)
    """
    if frame is None or frame.size == 0:
        return False, "Invalid frame provided", None
        
    target_bytes = Config.TARGET_IMAGE_KB * 1024
    quality = Config.IMAGE_JPEG_QUALITY
    min_quality = Config.IMAGE_MIN_JPEG_QUALITY
    
    best_buffer: Optional[np.ndarray] = None
    
    # Iterative compression
    while quality >= min_quality:
        success, buffer = cv2.imencode(
            ".jpg", 
            frame, 
            [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        
        if not success:
            return False, "OpenCV encoding failed", None
        
        best_buffer = buffer
        
        if buffer.nbytes <= target_bytes:
            return True, None, buffer
            
        quality -= 5
    
    # If we exit loop, we didn't meet target size with min_quality
    if best_buffer is None:
        return False, "Encoding produced no output", None
        
    warning = (
        f"Image size {best_buffer.nbytes / 1024:.1f}KB exceeds target "
        f"{Config.TARGET_IMAGE_KB}KB at minimum quality {min_quality}"
    )
    logger.warning(warning)
    return True, warning, best_buffer

def enhance_image_for_recognition(frame: np.ndarray) -> np.ndarray:
    """
    Apply enhancement pipeline: Upscale -> Gamma -> CLAHE -> Sharpen.
    Used for improving face detection recall.
    
    Args:
        frame: Input image frame
        
    Returns:
        Enhanced image frame
    """
    if frame is None or frame.size == 0:
        logger.warning("Invalid frame provided to enhance_image_for_recognition")
        return frame
        
    try:
        # 1. Upscale
        height, width = frame.shape[:2]
        new_dim = (width * 2, height * 2)
        enhanced = cv2.resize(frame, new_dim, interpolation=cv2.INTER_LANCZOS4)
        # 2. Gamma Correction
        gamma = 1.5
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        enhanced = cv2.LUT(enhanced, table)

        # 3. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl, a_channel, b_channel))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
        
        # 4. Sharpen
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        enhanced = cv2.filter2D(enhanced, -1, kernel)
        
        return enhanced
    except Exception as e:
        logger.error(f"Error enhancing image: {e}")
        return frame

def crop_face(frame: np.ndarray, rect: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Crop the face region from frame.
    
    Args:
        frame: Input image frame
        rect: Rectangle coordinates (x, y, w, h)
        
    Returns:
        Cropped face region
    """
    if frame is None or frame.size == 0:
        logger.warning("Invalid frame provided to crop_face")
        return frame
        
    x, y, w, h = rect
    
    # Validate coordinates
    frame_h, frame_w = frame.shape[:2]
    if x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
        logger.warning(f"Invalid crop coordinates: {rect} for frame size {frame_w}x{frame_h}")
        return frame
        
    return frame[y:y + h, x:x + w]


