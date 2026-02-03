"""
Student Upload API Resource.
"""
from flask import request
from flask_restful import Resource
from src.services.student_service import StudentService
from src.utils.response_utils import success_response, error_response
from src.exceptions.base import AppError
import logging

logger = logging.getLogger(__name__)

class StudentUploadResource(Resource):
    """Resource for handling student upload operations."""
    
    def __init__(self):
        self.service = StudentService()

    def post(self, action: str):
        """Handle upload actions: 'single' or 'bulk'."""
        if action not in ['single', 'bulk']:
            return error_response("Invalid action. Use 'single' or 'bulk'", 400)
            
        try:
            if action == 'single':
                return self._handle_single_upload()
            else:
                return self._handle_bulk_upload()

        except AppError as e:
            logger.error(f"AppError in student upload: {e}")
            return error_response(str(e), getattr(e, 'status_code', 500))
        except Exception as e:
            logger.error(f"Unexpected error in student upload: {e}")
            return error_response("Internal server error", 500)
    
    def _handle_single_upload(self):
        """Handle single student upload."""
        metadata = request.form.to_dict()
        file = request.files.get("image")
        
        if not file:
            return error_response("Image file required", 400)
        
        # Validate required fields
        required_fields = ['student_id', 'student_name', 'batch']
        for field in required_fields:
            if not metadata.get(field, '').strip():
                return error_response(f"{field} is required", 400)
        
        # Validate file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return error_response("File too large (max 10MB)", 400)
        
        result = self.service.process_single_upload(file, metadata)
        return success_response(result['message'], result)
    
    def _handle_bulk_upload(self):
        """Handle bulk student upload."""
        excel = request.files.get("excel")
        images = request.files.getlist("images")
        
        if not excel or not images:
            return error_response("Excel file and images required", 400)
        
        # Validate file counts
        if len(images) > 1000:  # Reasonable limit
            return error_response("Too many images (max 1000)", 400)
        
        result = self.service.process_bulk_upload(excel, images)
        return success_response("Bulk upload completed", result)
