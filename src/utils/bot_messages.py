"""
Bot Messages Loader.
Centralized message management for all bot responses.
"""
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BotMessages:
    """Singleton class to load and format bot messages from JSON."""
    
    _instance = None
    _messages = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BotMessages, cls).__new__(cls)
            cls._instance._load_messages()
        return cls._instance
    
    def _load_messages(self):
        """Load messages from JSON file."""
        try:
            # Get project root directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(os.path.dirname(current_dir), 'config')
            messages_file = os.path.join(config_dir, 'bot_messages.json')
            
            with open(messages_file, 'r', encoding='utf-8') as f:
                self._messages = json.load(f)
            
            logger.info(f"Bot messages loaded successfully from {messages_file}")
        except Exception as e:
            logger.error(f"Failed to load bot messages: {e}")
            self._messages = {}
    
    def get(self, category: str, key: str, **kwargs) -> str:
        """
        Get a formatted message.
        
        Args:
            category: Message category (teacher_bot, student_bot, face_verification)
            key: Message key
            **kwargs: Format parameters
            
        Returns:
            Formatted message string
        """
        try:
            message = self._messages.get(category, {}).get(key, "")
            if kwargs:
                return message.format(**kwargs)
            return message
        except KeyError as e:
            logger.error(f"Missing format parameter for {category}.{key}: {e}")
            return message
        except Exception as e:
            logger.error(f"Error formatting message {category}.{key}: {e}")
            return f"Error loading message: {category}.{key}"
    
    def teacher(self, key: str, **kwargs) -> str:
        """Get teacher bot message."""
        return self.get('teacher_bot', key, **kwargs)
    
    def student(self, key: str, **kwargs) -> str:
        """Get student bot message."""
        return self.get('student_bot', key, **kwargs)
    
    def verification(self, key: str, **kwargs) -> str:
        """Get face verification message."""
        return self.get('face_verification', key, **kwargs)

# Global instance
messages = BotMessages()
