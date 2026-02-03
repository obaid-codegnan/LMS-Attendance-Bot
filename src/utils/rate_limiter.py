"""
Rate Limiter for AWS API Calls
Prevents throttling and reduces costs
"""
import time
import threading
import asyncio
from typing import Dict, Any
from collections import deque

class RateLimiter:
    """Token bucket rate limiter for AWS API calls."""
    
    def __init__(self, max_calls: int = 10, time_window: int = 1):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
        self.lock = threading.Lock()
    
    def acquire(self) -> bool:
        """Acquire permission for API call."""
        with self.lock:
            now = time.time()
            
            # Remove old calls outside time window
            while self.calls and self.calls[0] <= now - self.time_window:
                self.calls.popleft()
            
            # Check if we can make the call
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True
            
            return False
    
    def wait_time(self) -> float:
        """Get wait time until next call is allowed."""
        with self.lock:
            if len(self.calls) < self.max_calls:
                return 0.0
            
            oldest_call = self.calls[0]
            return max(0.0, self.time_window - (time.time() - oldest_call))

# Global rate limiters
aws_rekognition_limiter = RateLimiter(max_calls=8, time_window=1)  # 8 calls per second
aws_s3_limiter = RateLimiter(max_calls=20, time_window=1)  # 20 calls per second

async def rate_limited_aws_call(limiter: RateLimiter, func, *args, **kwargs):
    """Execute AWS call with rate limiting."""
    while not limiter.acquire():
        wait_time = limiter.wait_time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)
    
    return func(*args, **kwargs)