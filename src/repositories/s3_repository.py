"""
S3 Repository.
Handles file storage interactions (AWS S3).
"""
import logging
from typing import Optional
import boto3
import urllib3
from botocore.config import Config as BotoConfig
from src.config.settings import Config
from src.exceptions.base import ExternalServiceError

logger = logging.getLogger(__name__)

class S3Repository:
    """
    Repository for AWS S3 operations.
    """

    def __init__(self) -> None:
        """Initialize the S3 client."""
        try:
            retry_config = BotoConfig(
                retries={
                    'max_attempts': 3,
                    'mode': 'standard'
                },
                connect_timeout=60,
                read_timeout=60
            )

            # Disable SSL Warnings
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            self.client = boto3.client(
                's3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION,
                config=retry_config,
                verify=False  # Bypass SSL errors
            )
            self.bucket_name = Config.AWS_S3_BUCKET
            if not self.bucket_name:
                logger.warning("AWS_S3_BUCKET is not set in configuration")
                
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise ExternalServiceError("Failed to initialize S3 client", "S3", details={"error": str(e)})

    def upload_file(self, file_path: str, object_name: str) -> bool:
        """
        Upload a file to an S3 bucket.
        
        Args:
            file_path: Local file path to upload
            object_name: S3 object name/key
            
        Returns:
            True if successful, raises exception otherwise
        """
        if not self.bucket_name:
            raise ExternalServiceError("AWS_S3_BUCKET not configured", "S3")
        
        if not file_path or not object_name:
            raise ValueError("file_path and object_name are required")
             
        try:
            self.client.upload_file(file_path, self.bucket_name, object_name)
            logger.info(f"Uploaded {file_path} to s3://{self.bucket_name}/{object_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            raise ExternalServiceError("Failed to upload file", "S3", details={"error": str(e)})

    def read_file_content(self, object_name: str) -> Optional[bytes]:
        """
        Read file content directly from S3 into memory.
        
        Args:
            object_name: S3 object name/key
            
        Returns:
            File content as bytes or None if not found
        """
        if not self.bucket_name:
            logger.error("AWS_S3_BUCKET not configured")
            return None
        
        if not object_name:
            logger.error("object_name is required")
            return None
             
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=object_name)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Failed to read {object_name} from S3: {e}")
            # We return None for read failures to allow graceful handling (e.g. file not found)
            return None

    def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from S3 bucket.
        
        Args:
            object_name: S3 object name/key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.bucket_name:
            logger.error("AWS_S3_BUCKET not configured")
            return False
        
        if not object_name:
            logger.error("object_name is required")
            return False
             
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"Deleted {object_name} from S3")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {object_name} from S3: {e}")
            return False
