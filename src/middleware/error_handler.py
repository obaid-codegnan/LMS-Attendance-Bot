"""
Enhanced error handling middleware for Flask application.
"""
import logging
from functools import wraps
from flask import jsonify, request, g
from src.exceptions.base import AppError, ValidationError, DatabaseError
from src.utils.response_utils import error_response
from src.utils.error_handling import correlation_context, ErrorHandler

logger = logging.getLogger(__name__)

def handle_errors(app):
    """Register enhanced error handlers with Flask app."""
    
    @app.before_request
    def setup_correlation_id():
        """Set up correlation ID for request tracking."""
        correlation_id = request.headers.get('X-Correlation-ID')
        if not correlation_id:
            import uuid
            correlation_id = str(uuid.uuid4())[:8]
        
        correlation_context.set_correlation_id(correlation_id)
        g.correlation_id = correlation_id
    
    @app.after_request
    def add_correlation_header(response):
        """Add correlation ID to response headers."""
        if hasattr(g, 'correlation_id'):
            response.headers['X-Correlation-ID'] = g.correlation_id
        return response
    
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.warning(f"[{correlation_id}] Validation error: {error.message}")
        return error_response(error.message, 400)
    
    @app.errorhandler(DatabaseError)
    def handle_database_error(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.error(f"[{correlation_id}] Database error: {error.message}")
        
        # Use enhanced error handler
        handled_error = ErrorHandler.handle_database_error(
            error, "database_operation", {"url": request.url}
        )
        return error_response(str(handled_error), 500)
    
    @app.errorhandler(AppError)
    def handle_app_error(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.error(f"[{correlation_id}] Application error: {error.message}")
        return error_response(error.message, 500)
    
    @app.errorhandler(404)
    def handle_not_found(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.warning(f"[{correlation_id}] 404 error for {request.url}")
        return error_response("Resource not found", 404)
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.warning(f"[{correlation_id}] 405 error for {request.method} {request.url}")
        return error_response("Method not allowed", 405)
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.error(f"[{correlation_id}] Internal server error: {str(error)}")
        return error_response("Internal server error", 500)
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.error(f"[{correlation_id}] Unexpected error: {str(error)}", exc_info=True)
        return error_response("An unexpected error occurred", 500)


def log_requests(app):
    """Add enhanced request logging middleware."""
    
    @app.before_request
    def log_request_info():
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.info(f"[{correlation_id}] {request.method} {request.url} - {request.remote_addr}")
    
    @app.after_request
    def log_response_info(response):
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        logger.info(f"[{correlation_id}] Response: {response.status_code}")
        return response


def validate_content_type(required_type='application/json'):
    """Decorator to validate request content type."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.content_type != required_type:
                return error_response(f"Content-Type must be {required_type}", 400)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_json_fields(*required_fields):
    """Decorator to validate required JSON fields."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return error_response("Request must be JSON", 400)
            
            json_data = request.get_json()
            if not json_data:
                return error_response("Invalid JSON data", 400)
            
            missing_fields = [field for field in required_fields if field not in json_data]
            if missing_fields:
                return error_response(f"Missing required fields: {', '.join(missing_fields)}", 400)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def rate_limit_by_ip(max_requests=100, window_seconds=3600):
    """Simple rate limiting decorator (in-memory, for basic protection)."""
    from collections import defaultdict
    import time
    
    request_counts = defaultdict(list)
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            now = time.time()
            
            # Clean old requests
            request_counts[client_ip] = [
                req_time for req_time in request_counts[client_ip]
                if now - req_time < window_seconds
            ]
            
            # Check rate limit
            if len(request_counts[client_ip]) >= max_requests:
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return error_response("Rate limit exceeded", 429)
            
            # Add current request
            request_counts[client_ip].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator