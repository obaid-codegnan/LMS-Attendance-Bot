"""
Face Repository.
Handles interactions with AWS Rekognition for face detection and matching.
Treats AWS as an external data source.
"""
import logging
import time
from typing import List, Tuple, Optional, Dict, Any
import boto3
import cv2
import numpy as np
import urllib3
import asyncio
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig
from src.config.settings import Config
from src.exceptions.base import ExternalServiceError
from src.utils.cost_optimizer import get_cost_optimizer

logger = logging.getLogger(__name__)

# Type alias for face rectangle: (x, y, w, h)
FaceRect = Tuple[int, int, int, int]

class FaceRepository:
    """
    Repository for AWS Rekognition operations with rate limiting for high scale.
    """
    
    _last_request_time = 0
    _request_lock = asyncio.Lock() if 'asyncio' in globals() else None

    def __init__(self) -> None:
        """Initialize the AWS Rekognition client with retry logic."""
        try:
            from botocore.config import Config as BotoConfig
            
            # Standard retry mode handles connection errors and throttling
            retry_config = BotoConfig(
                retries={
                    'max_attempts': 5,
                    'mode': 'standard'
                },
                connect_timeout=60,
                read_timeout=60
            )

            # Disable SSL Warnings
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            self.client = boto3.client(
                'rekognition',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION,
                config=retry_config,
                verify=False  # Bypass SSL errors
            )
        except Exception as e:
            logger.error(f"Failed to initialize AWS Rekognition client: {e}")
            raise ExternalServiceError("Failed to initialize AWS Rekognition", "AWS", details={"error": str(e)})

    def _rate_limit(self):
        """Rate limiting for AWS API calls to handle high scale."""
        from src.utils.rate_limiter import aws_rekognition_limiter
        import time
        
        while not aws_rekognition_limiter.acquire():
            wait_time = aws_rekognition_limiter.wait_time()
            if wait_time > 0:
                time.sleep(wait_time)

    def detect_faces_in_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Detect faces in image bytes with cost optimization.
        Returns raw AWS FaceDetails.
        """
        # Optimize image before AWS call
        from src.utils.cost_optimizer import optimize_image_for_aws
        optimized_bytes = optimize_image_for_aws(image_bytes)
        
        max_retries = 2  # Reduced retries due to optimization
        current_bytes = optimized_bytes
        
        for attempt in range(max_retries + 1):
            try:
                # Rate limiting for high scale
                self._rate_limit()
                
                # Re-create client on retry
                if attempt > 0:
                     self.__init__()
                     
                response = self.client.detect_faces(
                    Image={'Bytes': current_bytes},
                    Attributes=['DEFAULT']
                )
                return response.get('FaceDetails', [])
            except Exception as e:
                err_str = str(e)
                is_conn_error = "SSL" in err_str or "EOF" in err_str or "Connection" in err_str
                
                if is_conn_error and attempt < max_retries:
                    import time
                    logger.warning(f"Connection error in detect_faces (Attempt {attempt+1}): {e}.")
                    
                    # Fallback compression
                    try:
                        current_bytes = self._compress_image(current_bytes, attempt)
                    except Exception as compress_err:
                        logger.warning(f"Failed to compress on retry: {compress_err}")

                    time.sleep(2)
                    continue
                
                logger.error(f"Error calling AWS Rekognition detect_faces: {e}")
                
                if attempt == max_retries:
                    raise ExternalServiceError("Face detection failed", "AWS", details={"error": str(e)})
        return []

    def compare_faces(self, source_s3_bucket: str, source_s3_key: str, 
                      target_image_bytes: Optional[bytes] = None, 
                      threshold: float = 80,
                      target_s3_bucket: Optional[str] = None, 
                      target_s3_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Compare a source face (from S3) against faces in a target image with cost optimization.
        Target can be raw bytes OR an S3 Object (S3-to-S3 comparison).
        """
        # Use cost optimizer for caching and image optimization
        if target_image_bytes:
            cost_optimizer = get_cost_optimizer()
            return cost_optimizer.optimize_face_comparison(
                source_key=f"{source_s3_bucket}/{source_s3_key}",
                target_bytes=target_image_bytes,
                comparison_func=self._compare_faces_internal,
                source_s3_bucket=source_s3_bucket,
                source_s3_key=source_s3_key,
                threshold=threshold,
                target_s3_bucket=target_s3_bucket,
                target_s3_key=target_s3_key
            )
        else:
            # S3-to-S3 comparison (no optimization needed)
            return self._compare_faces_internal(
                source_s3_bucket=source_s3_bucket,
                source_s3_key=source_s3_key,
                target_image_bytes=None,
                threshold=threshold,
                target_s3_bucket=target_s3_bucket,
                target_s3_key=target_s3_key
            )
    
    def _compare_faces_internal(self, source_s3_bucket: str, source_s3_key: str, 
                               target_image_bytes: Optional[bytes] = None, 
                               threshold: float = 80,
                               target_s3_bucket: Optional[str] = None, 
                               target_s3_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Internal face comparison method with retry logic.
        """
        max_retries = 2  # Reduced retries since we have cost optimization
        current_bytes = target_image_bytes
        
        for attempt in range(max_retries + 1):
            try:
                # Rate limiting for high scale
                self._rate_limit()
                
                # Refresh client on deep retries
                if attempt > 1:
                    self.__init__()

                # Prepare Target Image param
                target_image_param = {}
                if target_s3_bucket and target_s3_key:
                    target_image_param = {
                        'S3Object': {
                            'Bucket': target_s3_bucket,
                            'Name': target_s3_key
                        }
                    }
                elif current_bytes:
                    target_image_param = {'Bytes': current_bytes}
                else:
                    logger.error("No target image provided (bytes or S3)")
                    return []

                response = self.client.compare_faces(
                    SourceImage={
                        'S3Object': {
                            'Bucket': source_s3_bucket,
                            'Name': source_s3_key
                        }
                    },
                    TargetImage=target_image_param,
                    SimilarityThreshold=threshold
                )
                return response.get('FaceMatches', [])

            except Exception as e:
                import time
                err_str = str(e)
                is_conn_error = "SSL" in err_str or "EOF" in err_str or "Connection" in err_str
                
                if is_conn_error and attempt < max_retries:
                    logger.warning(f"Connection error in compare_faces (Attempt {attempt+1}/{max_retries+1}): {e}.")
                    
                    # Fallback compression if cost optimizer fails
                    try:
                        current_bytes = self._compress_image(current_bytes, attempt)
                    except Exception:
                        pass

                    time.sleep(1.5) 
                    continue
                
                logger.warning(f"Comparison failed for {source_s3_key}: {e}")
                if "InvalidParameterException" in err_str:
                    t_size = len(current_bytes) if current_bytes else 0
                    logger.error(f"Invalid Parameters - Source: {source_s3_bucket}/{source_s3_key}, TargetBytes: {t_size}, Threshold: {threshold}")

                return []
        return []

    def index_face(self, image_bucket: str, image_key: str, external_image_id: str, collection_id: str = None) -> bool:
        """Index a face from S3 into Rekognition Collection.
        
        NOTE: This method is not currently used by the system. The application uses
        direct face comparison via compare_faces() API instead of collection-based
        indexing/searching for better performance and simpler architecture.
        
        Kept for potential future use if collection-based face search is needed.
        
        Args:
            image_bucket: S3 bucket containing the face image
            image_key: S3 key of the face image
            external_image_id: External ID to associate with the indexed face
            collection_id: Rekognition collection ID (required if using this method)
        
        Returns:
            True if face was successfully indexed, False otherwise
        """
        if not collection_id:
            logger.error("collection_id parameter is required for index_face operation")
            return False
            
        try:
            response = self.client.index_faces(
                CollectionId=collection_id,
                Image={
                    'S3Object': {
                        'Bucket': image_bucket,
                        'Name': image_key
                    }
                },
                ExternalImageId=external_image_id,
                DetectionAttributes=['DEFAULT'],
                MaxFaces=1,
                QualityFilter="AUTO"
            )
            face_records = response.get('FaceRecords', [])
            return bool(face_records)
        except ClientError as e:
            logger.warning(f"AWS ClientError indexing face: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to index face: {e}")
            raise ExternalServiceError("Face indexing failed", "AWS", details={"error": str(e)})

    def _compress_image(self, image_bytes: bytes, attempt: int) -> bytes:
        """Compress image for retry attempts."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return image_bytes
            
        # Start with quality reduction
        quality = 80 - (attempt * 10)
        success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), max(30, quality)])
        
        if not success:
            return image_bytes
            
        # If still > 4.8MB, resize dimensions
        encoded_size = len(buffer.tobytes())
        iteration = 0
        h, w = frame.shape[:2]
        
        while encoded_size > 4.8 * 1024 * 1024 and iteration < 3:
            logger.info(f"Compressed size {encoded_size/1024/1024:.2f}MB still > 5MB. Resizing dimensions...")
            # Reduce dimensions by 30% each step
            new_w = int(w * 0.7)
            new_h = int(h * 0.7)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            h, w = new_h, new_w  # Update for next loop
            
            success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), max(30, quality)])
            if not success:
                logger.error("Failed to encode resized frame")
                break
            encoded_size = len(buffer.tobytes())
            iteration += 1

        if success and encoded_size < 5 * 1024 * 1024:
            compressed_bytes = buffer.tobytes()
            logger.info(f"Retrying with optimized payload: {encoded_size/1024:.2f} KB")
            return compressed_bytes
        else:
            logger.warning("Could not compress image below 5MB even after resizing.")
            logger.error("Compression failed: returning original bytes")
            return image_bytes