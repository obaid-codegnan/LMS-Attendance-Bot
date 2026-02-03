"""
AWS Cost Optimization System.
Reduces operational costs through image compression, caching, and batch processing.
"""
import logging
import hashlib
import time
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import cv2
import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)

class ImageOptimizer:
    """Optimizes images for AWS Rekognition to reduce costs."""
    
    @staticmethod
    def optimize_for_rekognition(image_bytes: bytes, max_size_kb: int = 512) -> bytes:
        """Optimize image for AWS Rekognition while maintaining quality."""
        try:
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Calculate optimal dimensions (AWS Rekognition works best with 800x600 max)
            width, height = image.size
            max_dimension = 800
            
            if width > max_dimension or height > max_dimension:
                ratio = min(max_dimension / width, max_dimension / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Progressive compression to target size
            quality = 85
            while quality > 30:
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=quality, optimize=True)
                compressed_bytes = output.getvalue()
                
                if len(compressed_bytes) <= max_size_kb * 1024:
                    logger.debug(f"Optimized image: {len(image_bytes)} -> {len(compressed_bytes)} bytes (quality: {quality})")
                    return compressed_bytes
                
                quality -= 10
            
            # Final fallback
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=30, optimize=True)
            return output.getvalue()
            
        except Exception as e:
            logger.warning(f"Image optimization failed: {e}, using original")
            return image_bytes

class FaceRecognitionCache:
    """Caches face recognition results to avoid duplicate AWS calls."""
    
    def __init__(self, max_size: int = 1000, ttl_hours: int = 24):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, float] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_hours * 3600
        self.lock = threading.RLock()
    
    def _generate_key(self, source_key: str, target_hash: str) -> str:
        """Generate cache key from source and target."""
        return f"{source_key}:{target_hash}"
    
    def _hash_image(self, image_bytes: bytes) -> str:
        """Generate hash for image bytes."""
        return hashlib.md5(image_bytes).hexdigest()[:16]
    
    def get(self, source_key: str, target_bytes: bytes) -> Optional[List[Dict[str, Any]]]:
        """Get cached result if available."""
        target_hash = self._hash_image(target_bytes)
        cache_key = self._generate_key(source_key, target_hash)
        
        with self.lock:
            if cache_key in self.cache:
                # Check TTL
                if time.time() - self.access_times[cache_key] < self.ttl_seconds:
                    self.access_times[cache_key] = time.time()  # Update access time
                    logger.debug(f"Cache HIT for {cache_key}")
                    return self.cache[cache_key]['result']
                else:
                    # Expired
                    del self.cache[cache_key]
                    del self.access_times[cache_key]
        
        logger.debug(f"Cache MISS for {cache_key}")
        return None
    
    def put(self, source_key: str, target_bytes: bytes, result: List[Dict[str, Any]]):
        """Cache the result."""
        target_hash = self._hash_image(target_bytes)
        cache_key = self._generate_key(source_key, target_hash)
        
        with self.lock:
            # Evict old entries if cache is full
            if len(self.cache) >= self.max_size:
                self._evict_oldest()
            
            self.cache[cache_key] = {
                'result': result,
                'timestamp': time.time()
            }
            self.access_times[cache_key] = time.time()
            logger.debug(f"Cached result for {cache_key}")
    
    def _evict_oldest(self):
        """Evict oldest cache entry."""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
        logger.debug(f"Evicted cache entry: {oldest_key}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': getattr(self, '_hit_count', 0) / max(getattr(self, '_total_requests', 1), 1)
            }

class BatchProcessor:
    """Batches AWS requests to optimize API usage."""
    
    def __init__(self, batch_size: int = 5, batch_timeout: float = 2.0):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_requests: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.last_batch_time = time.time()
    
    def add_request(self, request_data: Dict[str, Any]) -> str:
        """Add request to batch queue."""
        request_id = f"req_{int(time.time() * 1000)}_{len(self.pending_requests)}"
        
        with self.lock:
            self.pending_requests.append({
                'id': request_id,
                'data': request_data,
                'timestamp': time.time()
            })
            
            # Process batch if conditions met
            if (len(self.pending_requests) >= self.batch_size or 
                time.time() - self.last_batch_time > self.batch_timeout):
                self._process_batch()
        
        return request_id
    
    def _process_batch(self):
        """Process current batch of requests."""
        if not self.pending_requests:
            return
        
        batch = self.pending_requests.copy()
        self.pending_requests.clear()
        self.last_batch_time = time.time()
        
        logger.info(f"Processing batch of {len(batch)} requests")
        
        # Process batch in background thread
        threading.Thread(target=self._execute_batch, args=(batch,), daemon=True).start()
    
    def _execute_batch(self, batch: List[Dict[str, Any]]):
        """Execute batch of requests."""
        # This would be implemented based on specific AWS service
        # For now, just log the batch processing
        logger.info(f"Executed batch processing for {len(batch)} requests")

class CostOptimizer:
    """Main cost optimization coordinator."""
    
    def __init__(self):
        self.image_optimizer = ImageOptimizer()
        self.face_cache = FaceRecognitionCache()
        self.batch_processor = BatchProcessor()
        self.cost_metrics = {
            'api_calls_saved': 0,
            'bytes_saved': 0,
            'cache_hits': 0,
            'optimizations_applied': 0
        }
        self.metrics_lock = threading.Lock()
    
    def optimize_face_comparison(self, source_key: str, target_bytes: bytes, 
                               comparison_func, **kwargs) -> List[Dict[str, Any]]:
        """Optimize face comparison with caching and image optimization."""
        
        # 1. Check cache first
        cached_result = self.face_cache.get(source_key, target_bytes)
        if cached_result is not None:
            with self.metrics_lock:
                self.cost_metrics['cache_hits'] += 1
                self.cost_metrics['api_calls_saved'] += 1
            return cached_result
        
        # 2. Optimize image
        original_size = len(target_bytes)
        optimized_bytes = self.image_optimizer.optimize_for_rekognition(target_bytes)
        optimized_size = len(optimized_bytes)
        
        with self.metrics_lock:
            self.cost_metrics['bytes_saved'] += (original_size - optimized_size)
            self.cost_metrics['optimizations_applied'] += 1
        
        # 3. Execute comparison with optimized image
        try:
            result = comparison_func(target_image_bytes=optimized_bytes, **kwargs)
            
            # 4. Cache result
            self.face_cache.put(source_key, target_bytes, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Optimized face comparison failed: {e}")
            # Fallback to original if optimization fails
            result = comparison_func(target_image_bytes=target_bytes, **kwargs)
            self.face_cache.put(source_key, target_bytes, result)
            return result
    
    def get_cost_savings(self) -> Dict[str, Any]:
        """Get cost savings metrics."""
        with self.metrics_lock:
            # Estimate cost savings (AWS Rekognition: ~$0.001 per image)
            api_cost_saved = self.cost_metrics['api_calls_saved'] * 0.001
            bandwidth_saved_mb = self.cost_metrics['bytes_saved'] / (1024 * 1024)
            
            return {
                'api_calls_saved': self.cost_metrics['api_calls_saved'],
                'estimated_cost_saved_usd': round(api_cost_saved, 4),
                'bandwidth_saved_mb': round(bandwidth_saved_mb, 2),
                'cache_hit_rate': self.face_cache.get_stats()['hit_rate'],
                'optimizations_applied': self.cost_metrics['optimizations_applied']
            }

# Global cost optimizer instance
_cost_optimizer: Optional[CostOptimizer] = None
_optimizer_lock = threading.Lock()

def get_cost_optimizer() -> CostOptimizer:
    """Get global cost optimizer instance."""
    global _cost_optimizer
    if _cost_optimizer is None:
        with _optimizer_lock:
            if _cost_optimizer is None:
                _cost_optimizer = CostOptimizer()
    return _cost_optimizer

def optimize_image_for_aws(image_bytes: bytes) -> bytes:
    """Quick function to optimize image for AWS services."""
    optimizer = get_cost_optimizer()
    return optimizer.image_optimizer.optimize_for_rekognition(image_bytes)

def get_cost_savings_report() -> Dict[str, Any]:
    """Get current cost savings report."""
    optimizer = get_cost_optimizer()
    return optimizer.get_cost_savings()