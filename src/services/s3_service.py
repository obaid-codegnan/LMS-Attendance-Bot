"""
S3 Service for handling file uploads to AWS S3.
"""
import logging
import boto3
from botocore.exceptions import ClientError
from src.config.settings import Config

logger = logging.getLogger(__name__)

class S3Service:
    """Service for AWS S3 operations."""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = Config.AWS_S3_BUCKET
        self._initialize_s3()
    
    def _initialize_s3(self):
        """Initialize S3 client."""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION
            )
            logger.info("S3 client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
    
    def upload_student_face(self, student_id: str, batch_name: str, file) -> str:
        """Upload student face image to S3 in batch-specific folder."""
        try:
            if not self.s3_client:
                raise Exception("S3 client not initialized")
            
            # Generate S3 key with batch folder structure
            file_extension = file.filename.split('.')[-1].lower()
            s3_key = f"students/{batch_name}/{student_id}.{file_extension}"
            
            # Upload file
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs={'ContentType': f'image/{file_extension}'}
            )
            
            # Return S3 URL
            s3_url = f"https://{self.bucket_name}.s3.{Config.AWS_REGION}.amazonaws.com/{s3_key}"
            logger.info(f"Uploaded face image for student {student_id} to {s3_url}")
            
            return s3_url
            
        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            raise Exception(f"Failed to upload image: {e}")
    def update_master_excel(self, students_data: list) -> str:
        """Update master Excel file with student data."""
        try:
            if not self.s3_client:
                raise Exception("S3 client not initialized")
            
            import pandas as pd
            import tempfile
            import os
            
            excel_key = "metadata/training_model.xlsx"
            
            # Try to download existing Excel file
            try:
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=excel_key)
                file_content = response['Body'].read()
                
                # Save to temp file and read with pandas
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                    tmp_file.write(file_content)
                    tmp_path = tmp_file.name
                
                existing_df = pd.read_excel(tmp_path, engine='openpyxl')
                os.unlink(tmp_path)  # Clean up
                
                logger.info(f"Found existing Excel with {len(existing_df)} rows")
                logger.info(f"Existing columns: {list(existing_df.columns)}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchKey':
                    logger.info("Excel file does not exist, creating new one")
                else:
                    logger.error(f"Error accessing Excel file: {e}")
                existing_df = pd.DataFrame()
            except Exception as e:
                logger.error(f"Error reading Excel file: {e}")
                existing_df = pd.DataFrame()
            
            # Convert new data to DataFrame
            new_df = pd.DataFrame(students_data)
            logger.info(f"New data columns: {list(new_df.columns)}")
            
            # Combine with existing data - append new rows
            if not existing_df.empty and len(existing_df) > 0:
                # Ensure column compatibility
                for col in new_df.columns:
                    if col not in existing_df.columns:
                        existing_df[col] = ''
                for col in existing_df.columns:
                    if col not in new_df.columns:
                        new_df[col] = ''
                
                combined_df = pd.concat([existing_df, new_df], ignore_index=True, sort=False)
                logger.info(f"Combined: {len(existing_df)} existing + {len(new_df)} new = {len(combined_df)} total")
            else:
                combined_df = new_df
                logger.info(f"Creating new Excel with {len(combined_df)} rows")
            
            # Save to temporary file
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_path = tmp_file.name
            
            # Write Excel file
            combined_df.to_excel(tmp_path, index=False)
            
            # Upload to S3
            with open(tmp_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    excel_key,
                    ExtraArgs={'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
                )
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            s3_url = f"https://{self.bucket_name}.s3.{Config.AWS_REGION}.amazonaws.com/{excel_key}"
            logger.info(f"Updated master Excel file at {s3_url}")
            return s3_url
            
        except Exception as e:
            logger.error(f"Error updating master Excel: {e}")
            raise
    
    def upload_json_data(self, s3_key: str, json_content: str) -> str:
        """Upload JSON data to S3."""
        try:
            if not self.s3_client:
                raise Exception("S3 client not initialized")
            
            # Upload JSON content
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_content.encode('utf-8'),
                ContentType='application/json'
            )
            
            # Return S3 URL
            s3_url = f"https://{self.bucket_name}.s3.{Config.AWS_REGION}.amazonaws.com/{s3_key}"
            logger.info(f"Uploaded JSON data to {s3_url}")
            
            return s3_url
            
        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            raise Exception(f"Failed to upload JSON data: {e}")
        except Exception as e:
            logger.error(f"Error uploading JSON data: {e}")
            raise