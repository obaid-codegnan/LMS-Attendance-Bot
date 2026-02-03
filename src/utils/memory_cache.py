"""
Simple memory cache implementation
"""
import time
from typing import Dict, Any

class MemoryCache:
    def __init__(self):
        self.cache = {}
    
    def clear_expired(self) -> int:
        """Clear expired entries and return count."""
        current_time = time.time()
        expired_keys = []
        
        for key, (value, expiry) in self.cache.items():
            if expiry and current_time > expiry:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        return len(expired_keys)

# Global cache instances
_student_cache = MemoryCache()
_teacher_cache = MemoryCache()
_session_cache = MemoryCache()

def get_student_cache():
    return _student_cache

def get_teacher_cache():
    return _teacher_cache

def get_session_cache():
    return _session_cache