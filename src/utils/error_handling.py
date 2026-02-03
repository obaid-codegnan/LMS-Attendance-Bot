"""
Enhanced Error Handling System.
Provides correlation IDs, circuit breakers, and retry mechanisms for better reliability.
"""
import logging
import time
import uuid
import functools
from typing import Callable, Any, Optional, Dict
from threading import Lock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CorrelationContext:
    """Thread-local correlation ID context."""
    
    def __init__(self):
        import threading
        self._local = threading.local()
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current thread."""
        self._local.correlation_id = correlation_id
    
    def get_correlation_id(self) -> str:
        """Get correlation ID for current thread."""
        if not hasattr(self._local, 'correlation_id'):
            self._local.correlation_id = str(uuid.uuid4())[:8]
        return self._local.correlation_id
    
    def clear(self):
        """Clear correlation ID."""
        if hasattr(self._local, 'correlation_id'):
            delattr(self._local, 'correlation_id')

# Global correlation context
correlation_context = CorrelationContext()

class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self.lock = Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == 'OPEN':
                if self._should_attempt_reset():
                    self.state = 'HALF_OPEN'
                else:
                    raise Exception(f"Circuit breaker OPEN - service unavailable")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""
        return (self.last_failure_time and 
                datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout))
    
    def _on_success(self):
        """Handle successful call."""
        with self.lock:
            self.failure_count = 0
            self.state = 'CLOSED'
    
    def _on_failure(self):
        """Handle failed call."""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'

# Global circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_breaker_lock = Lock()

def get_circuit_breaker(service_name: str) -> CircuitBreaker:
    """Get or create circuit breaker for service."""
    with _breaker_lock:
        if service_name not in _circuit_breakers:
            _circuit_breakers[service_name] = CircuitBreaker()
        return _circuit_breakers[service_name]

def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 1.0, 
                      exceptions: tuple = (Exception,)):
    """Decorator for retry with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            correlation_id = correlation_context.get_correlation_id()
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"[{correlation_id}] Final retry failed for {func.__name__}: {e}")
                        raise
                    
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"[{correlation_id}] Retry {attempt + 1}/{max_retries} for {func.__name__} in {wait_time}s: {e}")
                    time.sleep(wait_time)
            
        return wrapper
    return decorator

def with_circuit_breaker(service_name: str):
    """Decorator to add circuit breaker protection."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            breaker = get_circuit_breaker(service_name)
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

def log_errors(func: Callable) -> Callable:
    """Decorator to add enhanced error logging."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        correlation_id = correlation_context.get_correlation_id()
        start_time = time.time()
        
        try:
            logger.info(f"[{correlation_id}] Starting {func.__name__}")
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"[{correlation_id}] Completed {func.__name__} in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{correlation_id}] Failed {func.__name__} after {duration:.2f}s: {e}")
            raise
    return wrapper

class ErrorHandler:
    """Centralized error handler with context."""
    
    @staticmethod
    def handle_database_error(e: Exception, operation: str, context: Dict = None) -> Exception:
        """Handle database errors with context."""
        correlation_id = correlation_context.get_correlation_id()
        context = context or {}
        
        error_msg = f"Database operation '{operation}' failed"
        logger.error(f"[{correlation_id}] {error_msg}: {e}, Context: {context}")
        
        # Return appropriate exception based on error type
        if "connection" in str(e).lower():
            return Exception(f"Database connection error - please try again")
        elif "timeout" in str(e).lower():
            return Exception(f"Database timeout - operation took too long")
        else:
            return Exception(f"Database error - {str(e)}")
    
    @staticmethod
    def handle_aws_error(e: Exception, operation: str, context: Dict = None) -> Exception:
        """Handle AWS service errors with context."""
        correlation_id = correlation_context.get_correlation_id()
        context = context or {}
        
        error_msg = f"AWS operation '{operation}' failed"
        logger.error(f"[{correlation_id}] {error_msg}: {e}, Context: {context}")
        
        # Return user-friendly error messages
        if "InvalidParameterException" in str(e):
            return Exception("Invalid image format - please try a different image")
        elif "ThrottlingException" in str(e):
            return Exception("Service busy - please try again in a moment")
        elif "AccessDenied" in str(e):
            return Exception("Service access error - please contact support")
        else:
            return Exception(f"Service error - please try again")
    
    @staticmethod
    def handle_telegram_error(e: Exception, operation: str, context: Dict = None) -> Exception:
        """Handle Telegram API errors with context."""
        correlation_id = correlation_context.get_correlation_id()
        context = context or {}
        
        error_msg = f"Telegram operation '{operation}' failed"
        logger.error(f"[{correlation_id}] {error_msg}: {e}, Context: {context}")
        
        if "network" in str(e).lower() or "timeout" in str(e).lower():
            return Exception("Network error - please check your connection")
        elif "bot was blocked" in str(e).lower():
            return Exception("Bot access blocked - please unblock and try again")
        else:
            return Exception("Communication error - please try again")

def safe_execute(func: Callable, error_handler: Callable = None, 
                default_return: Any = None, context: Dict = None) -> Any:
    """Safely execute function with error handling."""
    correlation_id = correlation_context.get_correlation_id()
    
    try:
        return func()
    except Exception as e:
        if error_handler:
            handled_error = error_handler(e, func.__name__, context)
            logger.error(f"[{correlation_id}] Handled error in {func.__name__}: {handled_error}")
        else:
            logger.error(f"[{correlation_id}] Unhandled error in {func.__name__}: {e}")
        
        return default_return