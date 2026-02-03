"""
Response utility functions for standardized API responses.
"""
from typing import Tuple, Dict, Any, Optional

def success_response(message: str = "Success", data: Dict[str, Any] = None, status_code: int = 200) -> Tuple[Dict[str, Any], int]:
    """
    Standard Success Response.
    """
    response = {
        "success": True,
        "message": message,
        "data": data or {}
    }
    return response, status_code

def error_response(message: str, status_code: int = 500, error_details: Any = None) -> Tuple[Dict[str, Any], int]:
    """
    Standard Error Response.
    """
    response = {
        "success": False,
        "error": {
            "code": "ERROR", # Generic code, can be refined
            "message": message
        }
    }
    if error_details:
        response["error"]["details"] = str(error_details)
        
    return response, status_code
