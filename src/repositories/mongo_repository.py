"""
MongoDB Repository for LMS Database Integration.
"""
import logging
from typing import Dict, List, Optional, Any
from src.config.settings import Config

logger = logging.getLogger(__name__)

class MongoRepository:
    """Repository for MongoDB LMS database operations."""
    
    def __init__(self):
        self.client = None
        self.db = None
        self._connect()
    
    def _connect(self):
        """Connect to MongoDB with fallback mode."""
        try:
            if not Config.MONGODB_URI:
                logger.warning("MONGODB_URI not configured, running in fallback mode")
                return
            
            # Try to import pymongo
            try:
                from pymongo import MongoClient
                from pymongo.errors import PyMongoError
            except ImportError:
                logger.error("pymongo not installed. Install with: pip install pymongo")
                return
                
            self.client = MongoClient(
                Config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=30000,
                retryWrites=True,
                retryReads=True
            )
            self.db = self.client[Config.MONGODB_DATABASE]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("MongoDB connected successfully")
            
        except Exception as e:
            logger.warning(f"MongoDB unavailable: {e}")
            logger.info("Running in fallback mode without MongoDB")
            self.client = None
            self.db = None
    
    def get_teacher_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get teacher by phone number."""
        try:
            if self.db is None:
                return None
                
            # Try exact match first
            teacher = self.db.teachers.find_one({"PhNumber": phone})
            
            if not teacher:
                # Try without country code
                clean_phone = phone.replace('+91', '').replace('+', '')
                teacher = self.db.teachers.find_one({
                    "$or": [
                        {"PhNumber": clean_phone},
                        {"PhNumber": f"+91{clean_phone}"},
                        {"PhNumber": {"$regex": clean_phone}}
                    ]
                })
            
            if teacher:
                # Convert ObjectId to string if present
                if '_id' in teacher:
                    teacher['_id'] = str(teacher['_id'])
                # Map fields for compatibility
                teacher['mentor_id'] = teacher.get('id')
                teacher['api_username'] = teacher.get('email')
                teacher['api_password'] = teacher.get('password')  # This is hashed, need plain text
                
            return teacher
            
        except Exception as e:
            logger.error(f"Error getting teacher by phone: {e}")
            return None
    
    def validate_student_for_session(self, student_id: str, otp: str) -> Optional[Dict[str, Any]]:
        """Validate if student can attend this session."""
        try:
            if self.db is None:
                logger.warning("MongoDB not connected")
                return None
            
            # Get session from MongoDB
            session = self.db.sessions.find_one({"otp": otp})
            
            if not session:
                logger.warning(f"Session not found for OTP: {otp}")
                return None
            
            # Check if session is expired
            from datetime import datetime, timedelta
            created_at = session.get('created_at')
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            
            if datetime.now() - created_at > timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
                logger.warning(f"Session {otp} has expired")
                return None
            
            # Check if student is in the session's student list
            students = session.get('students', {})
            
            # Debug: Log all student IDs in the session
            student_ids = list(students.keys())
            logger.info(f"Session {otp} contains {len(student_ids)} students: {student_ids}")
            
            if student_id in students:
                student_info = students[student_id]
                logger.info(f"Student {student_id} validated for session {otp}")
                return {
                    'student_id': student_id,
                    'name': student_info.get('name', ''),
                    'batch': student_info.get('BatchNo', ''),
                    'session_info': {
                        'otp': otp,
                        'batch_name': session.get('batch_name', ''),
                        'subject': session.get('subject', ''),
                        'lat': session.get('lat'),
                        'long': session.get('long'),
                        'teacher_credentials': session.get('teacher_credentials'),
                        'students': students  # Include all students for batch lookup
                    }
                }
            else:
                logger.warning(f"Student {student_id} not found in session {otp} student list")
                return None
                
        except Exception as e:
            logger.error(f"Error validating student {student_id} for session {otp}: {e}")
            return None
    
    def get_teacher_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get teacher by telegram ID."""
        try:
            if self.db is None:
                return None
            
            from src.utils.credential_manager import credential_manager
                
            teacher = self.db.teachers.find_one({"telegram_id": telegram_id})
            
            if teacher:
                if '_id' in teacher:
                    teacher['_id'] = str(teacher['_id'])
                # Decrypt password if exists
                if teacher.get('plain_password'):
                    decrypted = credential_manager.decrypt(teacher['plain_password'])
                    if decrypted:  # Only use if decryption succeeded
                        teacher['plain_password'] = decrypted
                    else:
                        # Decryption failed, remove invalid data
                        teacher.pop('plain_password', None)
                # Map fields for compatibility
                teacher['mentor_id'] = teacher.get('id')
                teacher['api_username'] = teacher.get('email')
                teacher['api_password'] = teacher.get('password')
                
            return teacher
            
        except Exception as e:
            logger.error(f"Error getting teacher by telegram ID: {e}")
            return None
    
    
    def create_session_with_credentials(self, otp: str, lat: float, lng: float, batch_name: str, subject: str, students: dict, teacher_id: str = None, teacher_name: str = None, teacher_telegram_id: int = None, teacher_credentials: dict = None) -> bool:
        """Create a new session in MongoDB with teacher credentials."""
        try:
            if self.db is None:
                logger.error("MongoDB not connected")
                return False
            
            from datetime import datetime
            
            session_data = {
                'otp': otp,
                'lat': lat,
                'lng': lng,
                'long': lng,  # Store both lng and long for compatibility
                'batch_name': batch_name,
                'subject': subject,
                'students': students,
                'created_at': datetime.now(),
                'expires_at': datetime.now().timestamp() + Config.OTP_EXPIRY_SECONDS,
                'date': datetime.now().strftime("%Y-%m-%d"),
                'location': 'vijayawada',
                'teacher_credentials': teacher_credentials  # Store credentials for API calls
            }
            
            # Add teacher info if provided
            if teacher_id:
                session_data['teacher_id'] = teacher_id
            if teacher_name:
                session_data['teacher_name'] = teacher_name
            if teacher_telegram_id:
                session_data['teacher_telegram_id'] = teacher_telegram_id
            
            result = self.db.sessions.insert_one(session_data)
            logger.info(f"Session created with OTP {otp}, ID: {result.inserted_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False
    
    def save_teacher_credentials(self, telegram_id: int, phone: str, email: str, password: str, name: str = None) -> bool:
        """Save teacher credentials for future logins."""
        try:
            if self.db is None:
                return False
            
            from datetime import datetime
            from src.utils.credential_manager import credential_manager
            
            # Normalize email to lowercase
            email = email.lower().strip()
            
            teacher_data = {
                'telegram_id': telegram_id,
                'phone': phone,
                'email': email,
                'plain_password': credential_manager.encrypt(password),
                'name': name or 'Teacher',
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            # Upsert based on telegram_id
            result = self.db.teachers.update_one(
                {'telegram_id': telegram_id},
                {'$set': teacher_data},
                upsert=True
            )
            
            logger.info(f"Saved encrypted credentials for teacher {email} (telegram_id: {telegram_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving teacher credentials: {e}")
            return False
    
    def save_jwt_tokens(self, username: str, access_token: str, refresh_token: str, access_expiry: float, refresh_expiry: float) -> bool:
        """Save JWT tokens to MongoDB for persistence across restarts.
        
        Args:
            username: User's email/username
            access_token: JWT access token
            refresh_token: JWT refresh token
            access_expiry: Access token expiry timestamp
            refresh_expiry: Refresh token expiry timestamp
            
        Returns:
            True if saved successfully
        """
        try:
            if self.db is None:
                return False
            
            from datetime import datetime
            
            token_data = {
                'username': username.lower().strip(),
                'access_token': access_token,
                'refresh_token': refresh_token,
                'access_expiry': access_expiry,
                'refresh_expiry': refresh_expiry,
                'updated_at': datetime.now()
            }
            
            # Upsert based on username
            result = self.db.jwt_tokens.update_one(
                {'username': username.lower().strip()},
                {'$set': token_data},
                upsert=True
            )
            
            logger.info(f"Saved JWT tokens for {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving JWT tokens: {e}")
            return False
    
    def get_jwt_tokens(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve JWT tokens from MongoDB.
        
        Args:
            username: User's email/username
            
        Returns:
            Token data dict or None
        """
        try:
            if self.db is None:
                return None
            
            import time
            
            token_data = self.db.jwt_tokens.find_one({'username': username.lower().strip()})
            
            if not token_data:
                return None
            
            # Check if tokens are expired
            current_time = time.time()
            if token_data.get('refresh_expiry', 0) < current_time:
                # Refresh token expired, delete and return None
                self.db.jwt_tokens.delete_one({'username': username.lower().strip()})
                logger.info(f"Deleted expired tokens for {username}")
                return None
            
            return token_data
            
        except Exception as e:
            logger.error(f"Error retrieving JWT tokens: {e}")
            return None
    
    def delete_jwt_tokens(self, username: str) -> bool:
        """Delete JWT tokens from MongoDB.
        
        Args:
            username: User's email/username
            
        Returns:
            True if deleted successfully
        """
        try:
            if self.db is None:
                return False
            
            result = self.db.jwt_tokens.delete_one({'username': username.lower().strip()})
            
            if result.deleted_count > 0:
                logger.info(f"Deleted JWT tokens for {username}")
            
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting JWT tokens: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from MongoDB.
        
        Returns:
            Number of sessions deleted
        """
        try:
            if self.db is None:
                return 0
            
            from datetime import datetime
            current_time = datetime.now().timestamp()
            
            # Delete sessions where expires_at < current_time
            result = self.db.sessions.delete_many({
                'expires_at': {'$lt': current_time}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} expired sessions")
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0