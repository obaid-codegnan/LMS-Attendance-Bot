"""
Attendance API Resource.
"""
from flask import request
from flask_restful import Resource
from src.services.attendance_service import AttendanceService
from src.utils.response_utils import success_response, error_response
from src.exceptions.base import AppError
import logging

logger = logging.getLogger(__name__)

class AttendanceResource(Resource):
    def __init__(self):
        self.service = AttendanceService()

    def post(self):
        """
        Mark attendance from upload.
        """
        try:
            image_file = request.files.get('image')
            batch = request.form.get('batch_name', '').strip()
            subject = request.form.get('subject', '').strip()
            drive_file_id = request.form.get('drive_file_id', '').strip()

            if not batch or not subject:
                return error_response("Missing batch or subject", 400)
            
            if not image_file and not drive_file_id:
                return error_response("Image or Drive File ID required", 400)

            # Validate file size if image provided
            if image_file:
                image_file.seek(0, 2)
                file_size = image_file.tell()
                image_file.seek(0)
                
                if file_size > 10 * 1024 * 1024:
                    return error_response("File too large (max 10MB)", 400)
                
                image_bytes = image_file.read()
            else:
                image_bytes = None
            
            result = self.service.process_attendance(image_bytes, batch, subject, drive_file_id)

            
            if result.get('success'):
                return success_response("Attendance processed", result)
            else:
                return error_response(result.get('message', 'Processing failed'), 500)

        except AppError as e:
            logger.error(f"AppError in attendance processing: {e}")
            return error_response(str(e), getattr(e, 'status_code', 500))
        except Exception as e:
            logger.error(f"Unexpected error in attendance processing: {e}")
            return error_response("Internal server error", 500)
