"""
Performance monitoring and metrics
"""
import time
import logging
from collections import defaultdict, deque
from typing import Dict, List
import threading

logger = logging.getLogger(__name__)

class MetricsCollector:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.metrics = defaultdict(list)
            self.counters = defaultdict(int)
            self.timers = {}
            self.recent_times = defaultdict(lambda: deque(maxlen=100))
            self.initialized = True
    
    def start_timer(self, operation: str, request_id: str = None):
        key = f"{operation}:{request_id}" if request_id else operation
        self.timers[key] = time.time()
    
    def end_timer(self, operation: str, request_id: str = None):
        key = f"{operation}:{request_id}" if request_id else operation
        if key in self.timers:
            duration = time.time() - self.timers[key]
            self.recent_times[operation].append(duration)
            del self.timers[key]
            return duration
        return 0
    
    def increment_counter(self, metric: str):
        self.counters[metric] += 1
    
    def get_stats(self) -> Dict:
        stats = {}
        for operation, times in self.recent_times.items():
            if times:
                stats[operation] = {
                    'avg_time': sum(times) / len(times),
                    'min_time': min(times),
                    'max_time': max(times),
                    'count': len(times)
                }
        
        stats['counters'] = dict(self.counters)
        stats['active_workers'] = len(self.timers)
        return stats
    
    def log_performance_summary(self):
        stats = self.get_stats()
        logger.info(f"Performance Summary: {stats}")

# Global metrics instance
metrics = MetricsCollector()