"""
Resource for fetching real-time attendance updates for the Telegram session.
"""
from flask import request
from flask_restful import Resource
from src.repositories.student_repository import StudentRepository
from src.utils.string_utils import sanitize_batch_name
from src.utils.response_utils import success_response, error_response
from src.utils.security_utils import validate_subject_name
import logging

logger = logging.getLogger(__name__)

class TelegramStatusResource(Resource):
    """Resource for fetching attendance status."""
    
    def get(self):
        """Get current attendance status for any batch/subject dynamically."""
        try:
            batch_name = request.args.get('batch_name', '').strip()
            subject = request.args.get('subject', '').strip()

            if not batch_name or not subject:
                return error_response("Missing batch_name or subject parameters", 400)
            
            if not validate_subject_name(subject) or len(batch_name) > 100:
                return error_response("Invalid batch name or subject", 400)

            # Dynamic table name generation
            safe_batch = sanitize_batch_name(batch_name)
            table_name = safe_batch if safe_batch.startswith("students_") else f"students_{safe_batch}"
            subject_col = subject.lower()
            
            repo = StudentRepository()
            
            # Check if table exists and get students
            try:
                student_map = repo.get_student_map(table_name)
                if not student_map:
                    return error_response(f"Batch '{batch_name}' not found or empty", 404)
            except Exception as e:
                logger.error(f"Table {table_name} not accessible: {e}")
                return error_response(f"Batch '{batch_name}' not found", 404)
                
            # Ensure subject column exists
            repo.ensure_subject_column(table_name, subject_col)
            
            # Query attendance data
            try:
                res = repo.client.table(table_name).select(f"student_id, name, {subject_col}").execute()
                data = res.data
                
                present_list = []
                absent_list = []
                
                for row in data:
                    status = row.get(subject_col, 'Absent')
                    student_str = f"{row['student_id']} - {row.get('name', 'Unknown')}"
                    
                    if status == 'Present':
                        present_list.append(student_str)
                    else:
                        absent_list.append(student_str)
                
                return success_response(f"Attendance for {batch_name}/{subject}", {
                    "batch_name": batch_name,
                    "subject": subject,
                    "table_name": table_name,
                    "total_students": len(data),
                    "present_count": len(present_list),
                    "absent_count": len(absent_list),
                    "present_students": present_list,
                    "absent_students": absent_list
                })
                
            except Exception as e:
                # Handle missing column gracefully
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["column", "does not exist", "pgrst204", "42703"]):
                    all_students = [f"{sid} - {info.get('name', 'Unknown')}" for sid, info in student_map.items()]
                    return success_response(f"Attendance for {batch_name}/{subject} (new subject)", {
                        "batch_name": batch_name,
                        "subject": subject,
                        "table_name": table_name,
                        "total_students": len(all_students),
                        "present_count": 0,
                        "absent_count": len(all_students),
                        "present_students": [],
                        "absent_students": all_students
                    })
                else:
                    logger.error(f"Database error querying {table_name}.{subject_col}: {e}")
                    raise e

        except Exception as e:
            logger.error(f"Error fetching attendance for {batch_name}/{subject}: {e}")
            return error_response(f"Failed to fetch attendance: {str(e)}", 500)