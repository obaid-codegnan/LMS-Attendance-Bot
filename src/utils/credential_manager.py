"""
Secure Credential Manager for encrypting/decrypting passwords
"""
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class SecureCredentialManager:
    """Manages encryption and decryption of credentials."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            # Get or generate encryption key
            key = os.getenv('ENCRYPTION_KEY')
            if not key:
                # Generate and log warning
                key = Fernet.generate_key().decode()
                logger.warning(f"ENCRYPTION_KEY not set. Generated key: {key}")
                logger.warning("Add this to .env: ENCRYPTION_KEY=" + key)
            
            if isinstance(key, str):
                key = key.encode()
            
            self.cipher = Fernet(key)
            self.initialized = True
    
    def encrypt(self, password: str) -> str:
        """Encrypt a password."""
        if not password:
            return ""
        return self.cipher.encrypt(password.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt a password."""
        if not encrypted:
            return ""
        try:
            return self.cipher.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ""

# Global instance
credential_manager = SecureCredentialManager()
