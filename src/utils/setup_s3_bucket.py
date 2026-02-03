import boto3
import uuid
import logging
import sys
from botocore.exceptions import ClientError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_bucket():
    # 1. Verify Credentials
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        logger.info(f"Credentials verification successful.")
        logger.info(f"Account: {identity['Account']}")
        logger.info(f"ARN: {identity['Arn']}")
    except Exception as e:
        logger.error(f"Credentials invalid or expired: {e}")
        return

    # 2. Create Bucket
    s3 = boto3.client('s3')
    bucket_name = f"face-recognition-students-{uuid.uuid4().hex[:8]}"
    
    try:
        # Create bucket (us-east-1 is default and doesn't require LocationConstraint)
        # If region is not us-east-1, we need to specify it.
        session = boto3.session.Session()
        region = session.region_name or 'us-east-1'
        
        if region == 'us-east-1':
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
            
        logger.info(f"Successfully created bucket: {bucket_name}")
        logger.info("IMPORTANT: Please update your .env file with:")
        logger.info(f"AWS_S3_BUCKET={bucket_name}")
        
    except ClientError as e:
        logger.error(f"Failed to create bucket: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    setup_bucket()
