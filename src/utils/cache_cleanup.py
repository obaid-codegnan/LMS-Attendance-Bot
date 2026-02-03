"""
Background Cache Cleanup Service
Automatically cleans expired cache entries
"""
import threading
import time
import logging
from src.utils.memory_cache import get_student_cache, get_teacher_cache, get_session_cache

logger = logging.getLogger(__name__)

class CacheCleanupService:
    """Background service to clean up expired cache entries."""
    
    def __init__(self, cleanup_interval: int = 60):
        self.cleanup_interval = cleanup_interval
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the cleanup service."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.thread.start()
        logger.info("Cache cleanup service started")
    
    def stop(self):
        """Stop the cleanup service."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Cache cleanup service stopped")
    
    def _cleanup_loop(self):
        """Main cleanup loop."""
        while self.running:
            try:
                # Clean up all cache instances
                student_cleaned = get_student_cache().clear_expired()
                teacher_cleaned = get_teacher_cache().clear_expired()
                session_cleaned = get_session_cache().clear_expired()
                
                total_cleaned = student_cleaned + teacher_cleaned + session_cleaned
                
                if total_cleaned > 0:
                    logger.info(f"Cleaned {total_cleaned} expired cache entries")
                
                # Sleep for cleanup interval
                time.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                time.sleep(self.cleanup_interval)

# Global cleanup service
_cleanup_service = None

def start_cache_cleanup():
    """Start global cache cleanup service."""
    global _cleanup_service
    if _cleanup_service is None:
        _cleanup_service = CacheCleanupService()
        _cleanup_service.start()

def stop_cache_cleanup():
    """Stop global cache cleanup service."""
    global _cleanup_service
    if _cleanup_service:
        _cleanup_service.stop()
        _cleanup_service = None