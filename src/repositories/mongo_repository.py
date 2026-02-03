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
                
            self.client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)
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
            teacher = self.db.teachers.find_one({"phone": phone})
            
            if not teacher:
                # Try without country code
                clean_phone = phone.replace('+91', '').replace('+', '')
                teacher = self.db.teachers.find_one({
                    "$or": [
                        {"phone": clean_phone},
                        {"phone": f"+91{clean_phone}"},
                        {"phone": {"$regex": clean_phone}}
                    ]
                })
            
            if teacher:
                # Convert ObjectId to string
                teacher['_id'] = str(teacher['_id'])
                
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
                        'long': session.get('long')
                    }
                }
            else:
                logger.warning(f"Student {student_id} not found in session {otp} student list")
                return None
                
        except Exception as e:
            logger.error(f"Error validating student {student_id} for session {otp}: {e}")
            return None
    def create_session(self, otp: str, lat: float, lng: float, batch_name: str, subject: str, students: dict, teacher_id: str = None, teacher_name: str = None, teacher_telegram_id: int = None) -> bool:
        """Create a new session in MongoDB."""
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
                'location': 'vijayawada'
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
    
    def get_students_by_batch(self, batch_no: str) -> List[Dict[str, Any]]:
        try:
            # Check cache first
            from src.utils.memory_cache import get_student_cache
            cache = get_student_cache()
            cache_key = f"batch_{batch_no}"
            
            cached_students = cache.get(cache_key)
            if cached_students:
                return cached_students
            
            if self.db is None:
                return []
            
            # Try multiple field names for batch
            students = list(self.db.students.find({
                "$or": [
                    {"BatchNo": batch_no},
                    {"batch": batch_no},
                    {"batchNo": batch_no}
                ]
            }))
            
            # Convert ObjectIds to strings
            for student in students:
                student['_id'] = str(student['_id'])
            
            # Cache for 5 minutes
            cache.set(cache_key, students, ttl_seconds=300)
                
            return students
            
        except Exception as e:
            logger.error(f"Error getting students by batch: {e}")
            return []
    
    def get_student_by_id(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Get student by student ID."""
        try:
            if self.db is None:
                return None
                
            student = self.db.students.find_one({"studentId": student_id})
            
            if student:
                student['_id'] = str(student['_id'])
                
            return student
            
        except Exception as e:
            logger.error(f"Error getting student by ID: {e}")
            return None
    
    def update_teacher_telegram_id(self, teacher_id: str, telegram_id: int) -> bool:
        """Update teacher's telegram ID."""
        try:
            if self.db is None:
                return False
            
            try:
                from bson import ObjectId
            except ImportError:
                logger.error("bson not available, using string ID")
                # Fallback for string IDs
                result = self.db.teachers.update_one(
                    {"_id": teacher_id},
                    {"$set": {"telegram_id": telegram_id}}
                )
                return result.modified_count > 0
                
            result = self.db.teachers.update_one(
                {"_id": ObjectId(teacher_id)},
                {"$set": {"telegram_id": telegram_id}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating teacher telegram ID: {e}")
            return False
    
    def remove_time_restrictions_from_teachers(self) -> bool:
        """Remove time restriction fields from all teachers."""
        try:
            if self.db is None:
                return False
            
            # Remove time restriction related fields
            result = self.db.teachers.update_many(
                {},
                {"$unset": {
                    "time_restrictions": "",
                    "working_hours": "",
                    "schedule": "",
                    "availability": ""
                }}
            )
            
            logger.info(f"Removed time restrictions from {result.modified_count} teachers")
            return True
            
        except Exception as e:
            logger.error(f"Error removing time restrictions: {e}")
            return False
    
    def get_teacher_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get teacher by telegram ID."""
        try:
            if self.db is None:
                return None
                
            teacher = self.db.teachers.find_one({"telegram_id": telegram_id})
            
            if teacher:
                teacher['_id'] = str(teacher['_id'])
                
            return teacher
            
        except Exception as e:
            logger.error(f"Error getting teacher by telegram ID: {e}")
            return None
    
    # WEB INTERFACE METHODS
    def get_all_teachers(self) -> List[Dict[str, Any]]:
        """Get all teachers for web interface."""
        try:
            if self.db is None:
                return []
                
            teachers = list(self.db.teachers.find({}))
            
            for teacher in teachers:
                teacher['_id'] = str(teacher['_id'])
                
            return teachers
            
        except Exception as e:
            logger.error(f"Error getting all teachers: {e}")
            return []
    
    def get_all_students(self) -> List[Dict[str, Any]]:
        """Get all students for web interface."""
        try:
            if self.db is None:
                return []
                
            students = list(self.db.students.find({}))
            
            for student in students:
                student['_id'] = str(student['_id'])
                
            return students
            
        except Exception as e:
            logger.error(f"Error getting all students: {e}")
            return []
    
    def create_teacher(self, teacher_data: Dict[str, Any]) -> str:
        """Create new teacher."""
        try:
            if self.db is None:
                raise Exception("Database not connected")
            
            from datetime import datetime
            teacher_data['created_at'] = datetime.utcnow()
            teacher_data['telegram_id'] = None
            
            result = self.db.teachers.insert_one(teacher_data)
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error creating teacher: {e}")
            raise
    
    def create_student(self, student_data: Dict[str, Any]) -> str:
        """Create new student."""
        try:
            if self.db is None:
                raise Exception("Database not connected")
            
            from datetime import datetime
            student_data['created_at'] = datetime.utcnow()
            
            result = self.db.students.insert_one(student_data)
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error creating student: {e}")
            raise
    
    def get_teacher_by_id(self, teacher_id: str) -> Optional[Dict[str, Any]]:
        """Get teacher by ID."""
        try:
            if self.db is None:
                return None
            
            try:
                from bson import ObjectId
                teacher = self.db.teachers.find_one({"_id": ObjectId(teacher_id)})
            except:
                teacher = self.db.teachers.find_one({"_id": teacher_id})
            
            if teacher:
                teacher['_id'] = str(teacher['_id'])
                
            return teacher
            
        except Exception as e:
            logger.error(f"Error getting teacher by ID: {e}")
            return None
    
    def update_teacher(self, teacher_id: str, update_data: Dict[str, Any]) -> bool:
        """Update teacher."""
        try:
            if self.db is None:
                return False
            
            from datetime import datetime
            update_data['updated_at'] = datetime.utcnow()
            
            try:
                from bson import ObjectId
                result = self.db.teachers.update_one(
                    {"_id": ObjectId(teacher_id)},
                    {"$set": update_data}
                )
            except:
                result = self.db.teachers.update_one(
                    {"_id": teacher_id},
                    {"$set": update_data}
                )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating teacher: {e}")
            return False
    
    def get_teacher_count(self) -> int:
        """Get total teacher count."""
        try:
            if self.db is None:
                return 0
            return self.db.teachers.count_documents({})
        except Exception as e:
            logger.error(f"Error getting teacher count: {e}")
            return 0
    
    def get_student_count(self) -> int:
        """Get total student count."""
        try:
            if self.db is None:
                return 0
            return self.db.students.count_documents({})
        except Exception as e:
            logger.error(f"Error getting student count: {e}")
            return 0
    
    def get_batch_count(self) -> int:
        """Get unique batch count."""
        try:
            if self.db is None:
                return 0
            batches = self.db.students.distinct("batch")
            return len(batches)
        except Exception as e:
            logger.error(f"Error getting batch count: {e}")
            return 0
    
    def get_all_batches(self) -> List[str]:
        """Get all unique batches."""
        try:
            if self.db is None:
                return []
            return self.db.students.distinct("batch")
        except Exception as e:
            logger.error(f"Error getting batches: {e}")
            return []
    
    def get_all_subjects(self) -> List[str]:
        """Get all unique subjects."""
        try:
            if self.db is None:
                return []
            # Get subjects from teachers
            teachers = self.db.teachers.find({}, {"subjects": 1})
            subjects = set()
            for teacher in teachers:
                if "subjects" in teacher:
                    subjects.update(teacher["subjects"])
            return list(subjects)
        except Exception as e:
            logger.error(f"Error getting subjects: {e}")
            return []