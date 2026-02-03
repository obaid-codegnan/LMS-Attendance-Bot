"""
Custom Exceptions for the Application.
Adheres to the Enterprise Architecture standards.
"""

class AppError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class ValidationError(AppError):
    """Raised when input validation fails (Pydantic or Business Rule)."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400, details=details)

class NotFoundError(AppError):
    """Raised when a resource is not found."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)

class UnauthorizedError(AppError):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, code="UNAUTHORIZED", status_code=401)

class DatabaseError(AppError):
    """Raised when a database operation fails."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="DATABASE_ERROR", status_code=500, details=details)

class ExternalServiceError(AppError):
    """Raised when an external service (AWS, Google Drive) fails."""
    def __init__(self, message: str, service_name: str, details: dict = None):
        super().__init__(f"{service_name} Error: {message}", code=f"{service_name.upper()}_ERROR", status_code=502, details=details)
