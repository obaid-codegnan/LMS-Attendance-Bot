#!/usr/bin/env python3
"""
Script to check existing data in S3 bucket
"""
import boto3
import pandas as pd
import os
import tempfile
from src.config.settings import Config

def check_s3_bucket():
    # Initialize S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        region_name=Config.AWS_REGION
    )
    
    bucket_name = Config.AWS_S3_BUCKET
    print(f"Checking S3 bucket: {bucket_name}")
    print("=" * 50)
    
    # List all objects in bucket
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        
        if 'Contents' not in response:
            print("Bucket is empty")
            return
        
        metadata_files = []
        student_folders = {}
        other_files = []
        
        for obj in response['Contents']:
            key = obj['Key']
            size = obj['Size']
            modified = obj['LastModified']
            
            if key.startswith('metadata/'):
                metadata_files.append((key, size, modified))
            elif key.startswith('students/'):
                parts = key.split('/')
                if len(parts) >= 2:
                    batch = parts[1]
                    if batch not in student_folders:
                        student_folders[batch] = []
                    student_folders[batch].append((key, size, modified))
            else:
                other_files.append((key, size, modified))
        
        # Print metadata files
        print("METADATA FILES:")
        for key, size, modified in metadata_files:
            print(f"  {key} ({size} bytes, {modified})")
            
            # Try to download existing Excel file (skip empty folders)
            if size > 0 and key.endswith('.xlsx'):
                try:
                    response = s3_client.get_object(Bucket=bucket_name, Key=key)
                    file_content = response['Body'].read()
                    
                    # Save to temp file and read with pandas
                    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                        tmp_file.write(file_content)
                        tmp_path = tmp_file.name
                    
                    df = pd.read_excel(tmp_path, engine='openpyxl')
                    os.unlink(tmp_path)  # Clean up
                    
                    print(f"    Rows: {len(df)}")
                    print(f"    Columns: {list(df.columns)}")
                    if len(df) > 0:
                        print("    Sample data:")
                        print(df.head().to_string(index=False))
                except Exception as e:
                    print(f"    Error reading Excel: {e}")
            elif size == 0:
                print("    (Empty folder)")
        
        print("\nSTUDENT FOLDERS:")
        for batch, files in student_folders.items():
            print(f"  Batch: {batch} ({len(files)} files)")
            for key, size, modified in files[:5]:  # Show first 5 files
                filename = key.split('/')[-1]
                print(f"    {filename} ({size} bytes)")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more files")
        
        if other_files:
            print("\nOTHER FILES:")
            for key, size, modified in other_files:
                print(f"  {key} ({size} bytes, {modified})")
        
        print(f"\nTOTAL OBJECTS: {len(response['Contents'])}")
        
    except Exception as e:
        print(f"Error accessing S3 bucket: {e}")

if __name__ == "__main__":
    check_s3_bucket()