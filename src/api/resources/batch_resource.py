"""
Batch API Resource.
"""
from flask_restful import Resource
from src.services.student_service import StudentService
from src.utils.response_utils import success_response, error_response
from src.config.settings import Config
import logging

logger = logging.getLogger(__name__)

class BatchResource(Resource):
    """Resource for handling batch operations."""
    
    def __init__(self):
        self.service = StudentService()

    def get(self):
        """List all available batches."""
        logger.info("BatchResource GET called")
        logger.debug(f"Config.GOOGLE_DRIVE_FOLDER_ID = {Config.GOOGLE_DRIVE_FOLDER_ID}")
        
        try:
            batches = self.service.get_batches()
            logger.info(f"Service returned {len(batches)} batches")
            return success_response("Batches fetched successfully", data={"batches": batches})
        except Exception as e:
            logger.error(f"Failed to fetch batches: {e}")
            return error_response(f"Failed to fetch batches: {str(e)}", 500)

class BatchFilesResource(Resource):
    """Resource for handling batch file operations."""
    
    def __init__(self):
        self.service = StudentService()

    def get(self, batch_id: str):
        """List files in a specific batch folder.
        
        Args:
            batch_id: The ID of the batch folder
        """
        if not batch_id or not batch_id.strip():
            return error_response("Batch ID is required", 400)
            
        try:
            files = self.service.get_drive_files(batch_id.strip())
            return success_response("Files fetched successfully", data={"files": files})
        except Exception as e:
            logger.error(f"Failed to fetch files for batch {batch_id}: {e}")
            return error_response(f"Failed to fetch files: {str(e)}", 500)

