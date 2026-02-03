from flask import request
from flask_restful import Resource
import logging
import re
from src.repositories.student_repository import StudentRepository
from src.utils.response_utils import success_response, error_response

logger = logging.getLogger(__name__)

class TeacherResource(Resource):
    """Resource for handling teacher operations."""
    
    def post(self):
        """Create a new teacher."""
        try:
            data = request.get_json()
            logger.info(f"Received teacher data: {data}")
            
            if not data:
                logger.error("No data provided")
                return error_response("No data provided", 400)
                
            name = data.get('name', '').strip()
            phone = data.get('phone_number', '').strip()
            batches = data.get('assigned_batches', [])
            subjects = data.get('assigned_subjects', [])
            time_restrictions = data.get('subject_time_restrictions', {})
            
            logger.info(f"Parsed: name={name}, phone={phone}, batches={batches}, subjects={subjects}")
            
            # Validate required fields
            if not name or not phone:
                logger.error(f"Missing required fields: name={name}, phone={phone}")
                return error_response("Name and Phone Number are required", 400)
            
            # Validate name (letters, spaces, hyphens, apostrophes only)
            if not re.match(r'^[a-zA-Z\s\-\']+$', name):
                logger.error(f"Invalid name format: {name}")
                return error_response("Invalid name format", 400)
            
            # Validate and format phone
            phone = self._validate_and_format_phone(phone)
            if not phone:
                return error_response("Invalid phone number format", 400)
            
            # Validate arrays and time restrictions
            if not isinstance(batches, list) or not isinstance(subjects, list):
                return error_response("Batches and subjects must be arrays", 400)
            
            if time_restrictions and not isinstance(time_restrictions, dict):
                return error_response("Time restrictions must be an object", 400)
            
            # Validate time restriction format
            if time_restrictions:
                for subject, time_data in time_restrictions.items():
                    # Support both old format (list) and new format (dict with batches)
                    if isinstance(time_data, list):
                        # Old format: subject-level time restrictions
                        for time_range in time_data:
                            if not self._validate_time_range(time_range):
                                return error_response(f"Invalid time format: {time_range}", 400)
                    elif isinstance(time_data, dict):
                        # New format: batch-specific time restrictions
                        for batch, time_ranges in time_data.items():
                            if not isinstance(time_ranges, list):
                                return error_response(f"Time ranges for {subject}.{batch} must be an array", 400)
                            for time_range in time_ranges:
                                if not self._validate_time_range(time_range):
                                    return error_response(f"Invalid time format for {subject}.{batch}: {time_range}", 400)
                    else:
                        return error_response(f"Time data for {subject} must be array or object", 400)
            
            repo = StudentRepository()
            
            payload = {
                "name": name,
                "phone_number": phone,
                "assigned_batches": batches,
                "assigned_subjects": subjects
            }
            
            # Add time restrictions if provided
            if time_restrictions:
                payload["subject_time_restrictions"] = time_restrictions
            try:
                # Check for existing teacher
                existing = repo.supabase.table("teachers").select("id").eq("phone_number", phone).execute()
                if existing.data:
                    return error_response(f"Teacher with phone {phone} already exists", 409)
                    
                repo.supabase.table("teachers").insert(payload).execute()
                return success_response("Teacher added successfully", {"phone_number": phone})
                
            except Exception as e:
                logger.error(f"Database error creating teacher: {e}")
                return error_response("Database operation failed", 500)

        except Exception as e:
            logger.error(f"Unexpected error creating teacher: {e}")
            return error_response("Internal server error", 500)
    
    def _validate_time_range(self, time_range: str) -> bool:
        """Validate time range format (HH:MM-HH:MM)."""
        try:
            if '-' not in time_range:
                return False
            
            start_time, end_time = time_range.split('-', 1)
            start_time = start_time.strip()
            end_time = end_time.strip()
            
            # Validate time format (HH:MM)
            time_pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
            
            if not re.match(time_pattern, start_time) or not re.match(time_pattern, end_time):
                return False
            
            # Validate that start time is before end time
            start_hour, start_min = map(int, start_time.split(':'))
            end_hour, end_min = map(int, end_time.split(':'))
            
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min
            
            return start_minutes < end_minutes
            
        except Exception:
            return False
    
    def _validate_and_format_phone(self, phone: str) -> str:
        """Validate and format phone number."""
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
