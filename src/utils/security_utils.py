"""
Security utility functions for input validation and sanitization.
"""
import re
from typing import Optional


def validate_student_id(student_id: str) -> bool:
    """
    Validate student ID format.
    
    Args:
        student_id: The student ID to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not student_id or not isinstance(student_id, str):
        return False
    
    student_id = student_id.strip()
    
    # Check length (1-50 characters)
    if len(student_id) < 1 or len(student_id) > 50:
        return False
    
    # Allow only alphanumeric characters, hyphens, and underscores
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, student_id))


def validate_otp(otp: str) -> bool:
    """
    Validate OTP format (6 digits).
    
    Args:
        otp: The OTP to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not otp or not isinstance(otp, str):
        return False
    
    otp = otp.strip()
    return otp.isdigit() and len(otp) == 6


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Validate GPS coordinates.
    
    Args:
        latitude: Latitude value
        longitude: Longitude value
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        lat = float(latitude)
        lng = float(longitude)
        return -90 <= lat <= 90 and -180 <= lng <= 180
    except (ValueError, TypeError):
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing potentially dangerous characters.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        str: Sanitized filename
    """
    if not filename:
        return "upload"
    
    # Remove path separators and other dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.strip('. ')
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    
    return filename or "upload"


def validate_table_name(table_name: str) -> bool:
    """
    Validate database table name format.
    
    Args:
        table_name: The table name to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not table_name or not isinstance(table_name, str):
        return False
    
    table_name = table_name.strip()
    
    # Check length (1-63 characters for PostgreSQL)
    if len(table_name) < 1 or len(table_name) > 63:
        return False
    
    # Must start with letter or underscore, contain only alphanumeric and underscores
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, table_name))


def validate_subject_name(subject: str) -> bool:
    """
    Validate subject name format.
    
    Args:
        subject: The subject name to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not subject or not isinstance(subject, str):
        return False
    
    subject = subject.strip()
    
    # Check length (1-50 characters)
    if len(subject) < 1 or len(subject) > 50:
        return False
    
    # Allow letters, numbers, spaces, hyphens, underscores
    pattern = r'^[a-zA-Z0-9 _-]+$'
    return bool(re.match(pattern, subject))


def sanitize_batch_name(batch_name: str) -> str:
    """
    Sanitize batch name for use as table name.
    
    Args:
        batch_name: The batch name to sanitize
        
    Returns:
        str: Sanitized batch name
    """
    if not batch_name:
        return "default_batch"
    
    # Convert to lowercase and replace spaces/special chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', batch_name.lower().strip())
    
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = 'batch_' + sanitized
    
    # Limit length
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
    
    return sanitized or "default_batch"