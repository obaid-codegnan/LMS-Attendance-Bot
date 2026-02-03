"""
String utility functions.
"""
import re
from typing import Optional


def sanitize_batch_name(batch_name: str) -> str:
    """
    Sanitize batch name for database table usage.
    Converts to lowercase and keeps only alphanumeric characters.
    
    Args:
        batch_name: The batch name to sanitize
        
    Returns:
        Sanitized batch name safe for database use
    """
    if not batch_name or not isinstance(batch_name, str):
        return "default_batch"
    
    # Convert to lowercase and replace non-alphanumeric with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', batch_name.lower().strip())
    
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


def clean_phone_number(phone: str) -> Optional[str]:
    """
    Clean and format phone number.
    
    Args:
        phone: Raw phone number string
        
    Returns:
        Formatted phone number or None if invalid
    """
    if not phone or not isinstance(phone, str):
        return None
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Handle different formats
    if len(digits_only) == 10:
        return '+91' + digits_only
    elif len(digits_only) == 12 and digits_only.startswith('91'):
        return '+' + digits_only
    elif len(digits_only) == 13 and digits_only.startswith('91'):
        return '+' + digits_only[1:]
    
    return None


def truncate_string(text: str, max_length: int = 100) -> str:
    """
    Truncate string to maximum length.
    
    Args:
        text: String to truncate
        max_length: Maximum allowed length
        
    Returns:
        Truncated string
    """
    if not text or not isinstance(text, str):
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."
