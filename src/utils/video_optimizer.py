"""
Video Frame Quality Enhancement and AWS Cost Optimization
Extracts best quality frames and optimizes images for AWS processing
"""
import cv2
import numpy as np
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

def extract_best_frame(video_path: str) -> Optional[np.ndarray]:
    """Extract the highest quality frame from video."""
    cap = cv2.VideoCapture(video_path)
    frames = []
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Extract frames from different positions
    positions = [0.2, 0.4, 0.6, 0.8] if frame_count > 4 else [0.5]
    
    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * pos))
        ret, frame = cap.read()
        if ret and frame is not None:
            quality_score = calculate_frame_quality(frame)
            frames.append((frame, quality_score))
    
    cap.release()
    
    if not frames:
        return None
    
    # Return best quality frame
    return max(frames, key=lambda x: x[1])[0]

def calculate_frame_quality(frame: np.ndarray) -> float:
    """Calculate frame quality based on sharpness and brightness."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Sharpness using Laplacian variance
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Brightness score (optimal around 128)
    brightness = np.mean(gray)
    brightness_score = 1 - abs(brightness - 128) / 128
    
    # Combined quality score
    return sharpness * brightness_score

def optimize_for_aws(frame: np.ndarray, max_size: Tuple[int, int] = None) -> bytes:
    """Optimize frame for AWS processing to reduce costs."""
    from src.config.settings import Config
    
    if max_size is None:
        max_size = (Config.AWS_IMAGE_MAX_WIDTH, Config.AWS_IMAGE_MAX_HEIGHT)
    
    # Resize if too large
    height, width = frame.shape[:2]
    max_width, max_height = max_size
    
    if width > max_width or height > max_height:
        scale = min(max_width/width, max_height/height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    # Optimized JPEG compression using config
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, Config.AWS_JPEG_QUALITY]
    
    if Config.AWS_JPEG_OPTIMIZE:
        encode_params.extend([cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    
    success, buffer = cv2.imencode(".jpg", frame, encode_params)
    
    if not success:
        raise ValueError("Failed to encode optimized frame")
    
    return buffer.tobytes()

def process_video_bytes(video_bytes: bytes) -> Optional[bytes]:
    """Process video bytes and return optimized image bytes."""
    import tempfile
    import os
    
    try:
        # Save video bytes to temp file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tf:
            tf.write(video_bytes)
            temp_path = tf.name
        
        # Extract best frame
        best_frame = extract_best_frame(temp_path)
        
        # Cleanup temp file
        os.remove(temp_path)
        
        if best_frame is None:
            return None
        
        # Optimize for AWS
        return optimize_for_aws(best_frame)
        
    except Exception as e:
        logger.error(f"Video processing error: {e}")
        return None