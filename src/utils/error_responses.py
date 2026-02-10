"""
Structured Error Response System
Provides consistent error formatting across the application
"""
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime


class ErrorCode(Enum):
    """Standard error codes for the application."""
    # Authentication Errors (1xxx)
    AUTH_INVALID_CREDENTIALS = 1001
    AUTH_TOKEN_EXPIRED = 1002
    AUTH_UNAUTHORIZED = 1003
    
    # Validation Errors (2xxx)
    VALIDATION_INVALID_STUDENT_ID = 2001
    VALIDATION_INVALID_OTP = 2002
    VALIDATION_SESSION_EXPIRED = 2003
    VALIDATION_LOCATION_OUT_OF_RANGE = 2004
    
    # Face Recognition Errors (3xxx)
    FACE_NOT_DETECTED = 3001
    FACE_NOT_MATCHED = 3002
    FACE_IMAGE_NOT_FOUND = 3003
    FACE_PROCESSING_FAILED = 3004
    
    # API Errors (4xxx)
    API_REQUEST_FAILED = 4001
    API_TIMEOUT = 4002
    API_ATTENDANCE_FAILED = 4003
    
    # System Errors (5xxx)
    SYSTEM_DATABASE_ERROR = 5001
    SYSTEM_QUEUE_FULL = 5002
    SYSTEM_SERVICE_UNAVAILABLE = 5003


class ErrorResponse:
    """Structured error response builder."""
    
    @staticmethod
    def create(
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a structured error response.
        
        Args:
            error_code: Standard error code
            message: Human-readable error message
            details: Additional error details
            request_id: Request tracking ID
            
        Returns:
            Structured error dictionary
        """
        return {
            "success": False,
            "error": {
                "code": error_code.value,
                "type": error_code.name,
                "message": message,
                "details": details or {},
                "timestamp": datetime.now().isoformat(),
                "request_id": request_id
            }
        }
    
    @staticmethod
    def success(data: Any, request_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a structured success response.
        
        Args:
            data: Response data
            request_id: Request tracking ID
            
        Returns:
            Structured success dictionary
        """
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id
        }


# Convenience functions for common errors
def auth_error(message: str, request_id: str = None) -> Dict[str, Any]:
    """Create authentication error response."""
    return ErrorResponse.create(
        ErrorCode.AUTH_INVALID_CREDENTIALS,
        message,
        request_id=request_id
    )


def validation_error(message: str, field: str = None, request_id: str = None) -> Dict[str, Any]:
    """Create validation error response."""
    details = {"field": field} if field else {}
    return ErrorResponse.create(
        ErrorCode.VALIDATION_INVALID_STUDENT_ID,
        message,
        details=details,
        request_id=request_id
    )


def face_error(error_code: ErrorCode, message: str, confidence: float = None, request_id: str = None) -> Dict[str, Any]:
    """Create face recognition error response."""
    details = {"confidence": confidence} if confidence is not None else {}
    return ErrorResponse.create(
        error_code,
        message,
        details=details,
        request_id=request_id
    )


def api_error(message: str, status_code: int = None, request_id: str = None) -> Dict[str, Any]:
    """Create API error response."""
    details = {"status_code": status_code} if status_code else {}
    return ErrorResponse.create(
        ErrorCode.API_REQUEST_FAILED,
        message,
        details=details,
        request_id=request_id
    )


def system_error(message: str, exception: Exception = None, request_id: str = None) -> Dict[str, Any]:
    """Create system error response."""
    details = {"exception": str(exception)} if exception else {}
    return ErrorResponse.create(
        ErrorCode.SYSTEM_SERVICE_UNAVAILABLE,
        message,
        details=details,
        request_id=request_id
    )
