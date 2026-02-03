"""
Face Recognition Service using AWS Rekognition
"""
import logging
import boto3
import cv2
import tempfile
import os
from typing import Dict, Any
from src.config.settings import Config
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial

logger = logging.getLogger(__name__)

class FaceRecognitionService:
    """Service for face recognition using AWS Rekognition."""
    
    def __init__(self):
        # Don't create shared clients - create per-request
        self.s3_bucket = Config.AWS_S3_BUCKET
        
        # Simple in-memory cache for S3 images
        self._image_cache = {}
        self._cache_max_size = 100  # Cache up to 100 student images
        
        # Dynamic worker allocation based on system resources
        worker_config = Config.get_optimal_workers()
        max_workers = worker_config['face_workers']
        
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="FaceRecog")
        logger.info(f"Face recognition service initialized with {max_workers} workers (CPU cores: {worker_config['cpu_count']}, allocated: {worker_config['project_cores']})")
    
    def _get_rekognition_client(self):
        """Create new Rekognition client for each request."""
        return boto3.client(
            'rekognition',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
    
    def _get_s3_client(self):
        """Create new S3 client for each request."""
        return boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
    
    async def verify_face_from_video_bytes(self, video_bytes: bytes, student_id: str, batch_name: str = None, request_id: str = None) -> Dict[str, Any]:
        """Verify face from video bytes against stored S3 image."""
        if not request_id:
            request_id = "unknown"
            
        logger.info(f"[{request_id}] Starting face verification from bytes for {student_id} in batch {batch_name}")
        
        try:
            # Run the blocking face verification in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                partial(self._verify_face_from_bytes_sync, video_bytes, student_id, batch_name, request_id)
            )
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Async face verification error for {student_id}: {e}")
            return {"success": False, "error": f"Verification failed: {str(e)}"}
    
    def _verify_face_from_bytes_sync(self, video_bytes: bytes, student_id: str, batch_name: str = None, request_id: str = None) -> Dict[str, Any]:
        """Synchronous face verification from bytes - runs in thread pool."""
        import time
        
        try:
            total_start = time.time()
            
            logger.info(f"[{request_id}] Processing video bytes for student {student_id} in batch {batch_name}")
            
            # Extract frame from video bytes (no download!)
            frame_start = time.time()
            frame_bytes = self._extract_frame_from_video_bytes(video_bytes)
            frame_time = time.time() - frame_start
            
            if not frame_bytes:
                return {"success": False, "error": "Could not extract frame from video"}
            
            logger.info(f"[{request_id}] Frame extraction: {frame_time:.2f}s")
            
            # Compare with stored face image in S3
            compare_start = time.time()
            result = self._compare_faces_with_s3_bytes(frame_bytes, student_id, batch_name, request_id)
            compare_time = time.time() - compare_start
            
            total_time = time.time() - total_start
            logger.info(f"[{request_id}] TIMING BREAKDOWN - Frame: {frame_time:.2f}s, Compare: {compare_time:.2f}s, Total: {total_time:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Face verification error: {e}")
            return {"success": False, "error": f"Verification failed: {str(e)}"}
    
    async def verify_face_from_video(self, video_file, student_id: str, batch_name: str = None, request_id: str = None) -> Dict[str, Any]:
        """Verify face from Telegram video note against stored S3 image."""
        if not request_id:
            request_id = "unknown"
            
        logger.info(f"[{request_id}] Starting threaded face verification for {student_id} in batch {batch_name}")
        
        try:
            # Run the blocking face verification in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                partial(self._verify_face_sync, video_file, student_id, batch_name, request_id)
            )
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Async face verification error for {student_id}: {e}")
            return {"success": False, "error": f"Verification failed: {str(e)}"}
    
    def _verify_face_sync(self, video_file, student_id: str, batch_name: str = None, request_id: str = None) -> Dict[str, Any]:
        """Synchronous face verification - runs in thread pool."""
        import time
        temp_frame_path = None
        
        try:
            total_start = time.time()
            
            # Get video file URL and extract frame directly
            video_url = video_file.file_path
            logger.info(f"[{request_id}] Processing video for student {student_id} in batch {batch_name}: {video_url}")
            
            # Extract frame directly from video URL
            frame_start = time.time()
            frame_bytes = self._extract_frame_from_video_url(video_url)
            frame_time = time.time() - frame_start
            
            if not frame_bytes:
                return {"success": False, "error": "Could not extract frame from video"}
            
            logger.info(f"[{request_id}] Frame extraction: {frame_time:.2f}s")
            
            # Compare with stored face image in S3
            compare_start = time.time()
            result = self._compare_faces_with_s3_bytes(frame_bytes, student_id, batch_name, request_id)
            compare_time = time.time() - compare_start
            
            total_time = time.time() - total_start
            logger.info(f"[{request_id}] TIMING BREAKDOWN - Frame: {frame_time:.2f}s, Compare: {compare_time:.2f}s, Total: {total_time:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Face verification error: {e}")
            return {"success": False, "error": f"Verification failed: {str(e)}"}
        finally:
            # Clean up temporary file
            if temp_frame_path and os.path.exists(temp_frame_path):
                try:
                    os.unlink(temp_frame_path)
                    logger.debug(f"[{request_id}] Cleaned up temp frame: {temp_frame_path}")
                except:
                    pass
    
    def _extract_frame_from_video_bytes(self, video_bytes: bytes) -> bytes:
        """Extract frame from video bytes - no download needed."""
        import time
        import tempfile
        
        try:
            extract_start = time.time()
            
            # Write bytes to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_file.write(video_bytes)
                temp_path = temp_file.name
            
            # Fast frame extraction
            cap = cv2.VideoCapture(temp_path)
            
            if not cap.isOpened():
                os.unlink(temp_path)
                return None
            
            # Skip to middle frame (frame 7) for good quality
            for i in range(7):
                ret, frame = cap.read()
                if not ret:
                    break
            
            cap.release()
            os.unlink(temp_path)
            
            if not ret:
                return None
            
            # Process frame
            frame = cv2.resize(frame, (200, 200), interpolation=cv2.INTER_LINEAR)
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
            
            total_time = time.time() - extract_start
            
            return buffer.tobytes()
                
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            return None
    
    def _extract_frame_from_video_url(self, video_url: str) -> bytes:
        """Fast single frame capture."""
        import time
        
        try:
            extract_start = time.time()
            
            # Direct frame capture from video stream
            cap = cv2.VideoCapture(video_url)
            
            if not cap.isOpened():
                return None
            
            # Skip to middle frame (frame 7) for good quality
            for i in range(7):
                ret, frame = cap.read()
                if not ret:
                    break
            
            cap.release()
            
            if not ret:
                return None
            
            # Process frame
            frame = cv2.resize(frame, (200, 200), interpolation=cv2.INTER_LINEAR)
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
            
            return buffer.tobytes()
                
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            return None
    
    def _compare_faces_with_s3_bytes(self, frame_bytes: bytes, student_id: str, batch_name: str = None, request_id: str = None) -> Dict[str, Any]:
        """Compare extracted frame with stored S3 image using AWS Rekognition."""
        import time
        
        try:

            
            # Create isolated clients for this request
            rekognition = self._get_rekognition_client()
            
            # Step 1: Find student image in S3
            s3_start = time.time()
            stored_image_bytes, found_s3_key = self._find_student_image_in_s3(student_id, batch_name, request_id)
            s3_time = time.time() - s3_start
            
            if not stored_image_bytes:
                return {"success": False, "error": f"No stored image found for student {student_id}"}
            
            # Step 2: Resize images if needed
            resize_start = time.time()
            stored_image_bytes = self._resize_image_if_needed(stored_image_bytes)
            frame_bytes = self._resize_image_if_needed(frame_bytes)
            resize_time = time.time() - resize_start
            
            # Step 3: AWS Rekognition comparison
            aws_start = time.time()
            response = rekognition.compare_faces(
                SourceImage={'Bytes': stored_image_bytes},
                TargetImage={'Bytes': frame_bytes},
                SimilarityThreshold=Config.FACE_MATCH_THRESHOLD
            )
            aws_time = time.time() - aws_start
            
            if response['FaceMatches']:
                confidence = response['FaceMatches'][0]['Similarity']
                total_time = s3_time + resize_time + aws_time
                return {
                    "success": True,
                    "confidence": confidence,
                    "student_id": student_id,
                    "timing": {
                        "s3_search": s3_time,
                        "image_resize": resize_time,
                        "aws_rekognition": aws_time,
                        "total": total_time
                    }
                }
            else:
                total_time = s3_time + resize_time + aws_time
                return {
                    "success": False,
                    "error": "Face does not match stored image",
                    "timing": {
                        "s3_search": s3_time,
                        "image_resize": resize_time,
                        "aws_rekognition": aws_time,
                        "total": total_time
                    }
                }
                
        except Exception as e:
            logger.error(f"Face comparison error for {student_id}: {e}")
            return {"success": False, "error": f"Comparison failed: {str(e)}"}
    
    def _find_student_image_in_s3(self, student_id: str, batch_name: str = None, request_id: str = None) -> tuple:
        """Ultra-fast S3 image lookup with direct path access."""
        try:
            # Check cache first
            cache_key = f"{batch_name}_{student_id}" if batch_name else student_id
            if cache_key in self._image_cache:
                logger.info(f"[{request_id}] Cache HIT for {student_id}")
                return self._image_cache[cache_key]
            
            # Create isolated S3 client for this request
            s3_client = self._get_s3_client()
            
            # Direct path using batch name and student ID
            if batch_name:
                s3_key = f"students/{batch_name}/{student_id}.jpg"
                try:
                    response = s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
                    stored_image_bytes = response['Body'].read()
                    
                    # Cache the result
                    if len(self._image_cache) >= self._cache_max_size:
                        # Remove oldest entry
                        oldest_key = next(iter(self._image_cache))
                        del self._image_cache[oldest_key]
                    
                    self._image_cache[cache_key] = (stored_image_bytes, s3_key)
                    logger.info(f"[{request_id}] Found: {s3_key}")
                    return stored_image_bytes, s3_key
                except Exception as e:
                    logger.error(f"[{request_id}] Student {student_id} not found at {s3_key}: {e}")
            
            logger.error(f"[{request_id}] No batch name or student {student_id} not found")
            return None, None
            
        except Exception as e:
            logger.error(f"Error finding student image in S3: {e}")
            return None, None
    
    def _resize_image_if_needed(self, image_bytes: bytes, max_size: int = 100000) -> bytes:
        """Balanced image processing for accuracy and speed."""
        try:
            # Skip resize if small enough
            if len(image_bytes) <= max_size:
                return image_bytes
            
            import numpy as np
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Balanced compression - 150x150 pixels
            resized_img = cv2.resize(img, (150, 150), interpolation=cv2.INTER_LINEAR)
            _, buffer = cv2.imencode('.jpg', resized_img, [cv2.IMWRITE_JPEG_QUALITY, 50])
            
            return buffer.tobytes()
            
        except Exception as e:
            return image_bytes
    
    def cleanup(self):
        """Cleanup thread pool resources."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
            logger.info("Face recognition thread pool shut down")