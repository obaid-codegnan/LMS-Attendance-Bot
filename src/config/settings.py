"""
Configuration module for Face Recognition application.
Handles environment variables and application settings.
"""
import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env from current working directory
load_dotenv()

# If running from a PyInstaller bundle, also load .env from _MEIPASS (extracted data)
_MEIPASS = getattr(sys, "_MEIPASS", None)
if _MEIPASS:
    meipass_env = Path(_MEIPASS) / ".env"
    if meipass_env.exists():
        load_dotenv(dotenv_path=meipass_env, override=False)

class Config:
    """Application configuration class."""
    
    # Flask Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())
    RELOAD: bool = os.getenv("RELOAD", "True").lower() == "true"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    HOST: str = os.getenv("HOST", "127.0.0.1")  # More secure default
    PORT: int = int(os.getenv("PORT", "5000"))
    
    
    
    # Camera Configuration
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "1"))
    CAMERA_DELAY_SECONDS: float = float(os.getenv("CAMERA_DELAY_SECONDS", "0.5"))
    IMAGE_FORMAT: str = os.getenv("IMAGE_FORMAT", "jpg")
    IMAGE_MAX_WIDTH: int = int(os.getenv("IMAGE_MAX_WIDTH", "1920"))
    IMAGE_MAX_HEIGHT: int = int(os.getenv("IMAGE_MAX_HEIGHT", "1080"))
    IMAGE_JPEG_QUALITY: int = int(os.getenv("IMAGE_JPEG_QUALITY", "95"))
    IMAGE_MIN_JPEG_QUALITY: int = int(os.getenv("IMAGE_MIN_JPEG_QUALITY", "80"))
    TARGET_IMAGE_KB: int = int(os.getenv("TARGET_IMAGE_KB", "1024"))
    SAVE_GROUP_IMAGE: bool = os.getenv("SAVE_GROUP_IMAGE", "true").lower() == "true"
    
    # Face Detection Configuration
    FACE_SCALE_FACTOR: float = float(os.getenv("FACE_SCALE_FACTOR", "1.1"))
    FACE_MIN_NEIGHBORS: int = int(os.getenv("FACE_MIN_NEIGHBORS", "5"))
    FACE_MIN_SIZE: int = int(os.getenv("FACE_MIN_SIZE", "60"))
    FACE_OUTPUT_SIZE: int = int(os.getenv("FACE_OUTPUT_SIZE", "256"))
    FACE_CROP_MARGIN: float = float(os.getenv("FACE_CROP_MARGIN", "0.5"))
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "50.0"))
    
    # Application Configuration
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", "524288000"))  # 500MB
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    FACE_DETECTION_PROVIDER: str = os.getenv("FACE_DETECTION_PROVIDER", "aws")
    AWS_S3_BUCKET: Optional[str] = os.getenv("AWS_S3_BUCKET")
    # AWS_REKOGNITION_COLLECTION_ID - Not used (system uses direct face comparison via compare_faces API)
    
    # MongoDB Configuration
    MONGODB_URI: Optional[str] = os.getenv("MONGODB_URI")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "lms_database")
    
        # Telegram Configuration
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TEACHER_BOT_TOKEN: Optional[str] = os.getenv("TEACHER_BOT_TOKEN")
    STUDENT_BOT_TOKEN: Optional[str] = os.getenv("STUDENT_BOT_TOKEN")
    
    # Comma-separated list of admin phone numbers (e.g., "+919999999999,+918888888888")
    ADMIN_PHONE_NUMBERS: list = [x.strip() for x in os.getenv("ADMIN_PHONE_NUMBERS", "").split(",") if x.strip()]
    
    # Session Expiry (in seconds)
    OTP_EXPIRY_SECONDS: int = int(os.getenv("OTP_EXPIRY_SECONDS", "150"))
    
    # Location and Validation Settings
    LOCATION_DISTANCE_LIMIT_METERS: int = int(os.getenv("LOCATION_DISTANCE_LIMIT_METERS", "50"))
    STUDENT_ID_MAX_LENGTH: int = int(os.getenv("STUDENT_ID_MAX_LENGTH", "50"))
    OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", "6"))
    
    # Face Recognition Settings
    DEFAULT_FACE_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "50.0"))
    FACE_VERIFICATION_MAX_RETRIES: int = int(os.getenv("FACE_VERIFICATION_MAX_RETRIES", "1"))
    IMAGE_COMPRESSION_START_QUALITY: int = int(os.getenv("IMAGE_COMPRESSION_START_QUALITY", "80"))
    AWS_MAX_RETRIES: int = int(os.getenv("AWS_MAX_RETRIES", "3"))
    
    # Thread Pool Configuration (Auto-detected for high scale)
    THREAD_POOL_MIN_WORKERS: int = int(os.getenv("THREAD_POOL_MIN_WORKERS", "5"))
    THREAD_POOL_MAX_WORKERS: int = int(os.getenv("THREAD_POOL_MAX_WORKERS", "50"))
    THREAD_POOL_SCALE_THRESHOLD: int = int(os.getenv("THREAD_POOL_SCALE_THRESHOLD", "3"))
    
    # AWS Cost Optimization Settings
    AWS_IMAGE_MAX_WIDTH: int = int(os.getenv("AWS_IMAGE_MAX_WIDTH", "300"))  # Smaller for speed
    AWS_IMAGE_MAX_HEIGHT: int = int(os.getenv("AWS_IMAGE_MAX_HEIGHT", "300"))  # Smaller for speed
    AWS_JPEG_QUALITY: int = int(os.getenv("AWS_JPEG_QUALITY", "40"))  # Lower quality for speed
    AWS_JPEG_OPTIMIZE: bool = os.getenv("AWS_JPEG_OPTIMIZE", "false").lower() == "true"  # Disable for speed
    
    # Dynamic Queue Settings
    QUEUE_MAX_SIZE: int = int(os.getenv("QUEUE_MAX_SIZE", "1000"))
    QUEUE_SCALE_COOLDOWN: int = int(os.getenv("QUEUE_SCALE_COOLDOWN", "5"))
    QUEUE_MIN_WORKERS: int = int(os.getenv("QUEUE_MIN_WORKERS", "2"))
    
    # High Scale Settings
    MAX_CONCURRENT_FACE_VERIFICATIONS: int = int(os.getenv("MAX_CONCURRENT_FACE_VERIFICATIONS", "100"))
    AWS_RATE_LIMIT_PER_SECOND: int = int(os.getenv("AWS_RATE_LIMIT_PER_SECOND", "20"))
    DB_CONNECTION_POOL_SIZE: int = int(os.getenv("DB_CONNECTION_POOL_SIZE", "50"))
    TEMP_FILE_CLEANUP_INTERVAL: int = int(os.getenv("TEMP_FILE_CLEANUP_INTERVAL", "180"))  # 3 minutes
    
    @staticmethod
    def get_optimal_workers() -> dict:
        """Calculate optimal worker counts based on system CPU cores and load."""
        import multiprocessing
        
        cpu_count = multiprocessing.cpu_count()
        
        # Allocate 80% of CPU cores to the project, 20% for system
        project_cores = max(1, int(cpu_count * 0.8))
        
        # Dynamic scaling based on system capacity
        face_workers = max(Config.QUEUE_MIN_WORKERS, min(project_cores * 2, Config.MAX_CONCURRENT_FACE_VERIFICATIONS))
        api_workers = max(8, min(project_cores * 3, 150))
        
        return {
            "cpu_count": cpu_count,
            "project_cores": project_cores,
            "face_workers": face_workers,
            "api_workers": api_workers,
            "queue_capacity": Config.QUEUE_MAX_SIZE
        }
    
    # API Integration Settings
    ATTENDANCE_API_BASE_URL: str = os.getenv("ATTENDANCE_API_BASE_URL", "http://127.0.0.1:5000/api/v1")
    DEFAULT_LOCATION: str = os.getenv("DEFAULT_LOCATION", "vijayawada")
    # Temporary teacher mapping until teacher API is available
    

    @staticmethod
    def _resolve_path(path_str: str) -> str:
        """
        Resolve a resource path; if not found, try PyInstaller's _MEIPASS.
        """
        candidate = Path(path_str)
        if candidate.exists():
            return str(candidate)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            alt = Path(meipass) / path_str
            if alt.exists():
                return str(alt)
        # Fall back to original
        return str(candidate)
    
    @staticmethod
    def validate() -> None:
        """Validate configuration settings."""
        # Validate required environment variables
        required_vars = [
            ("MONGODB_URI", Config.MONGODB_URI),
            ("AWS_ACCESS_KEY_ID", Config.AWS_ACCESS_KEY_ID),
            ("AWS_SECRET_ACCESS_KEY", Config.AWS_SECRET_ACCESS_KEY),
            ("AWS_S3_BUCKET", Config.AWS_S3_BUCKET),
            ("ATTENDANCE_API_BASE_URL", Config.ATTENDANCE_API_BASE_URL)
        ]
        
        missing_vars = [var_name for var_name, var_value in required_vars if not var_value]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Validate numeric ranges
        if Config.FACE_MATCH_THRESHOLD < 0 or Config.FACE_MATCH_THRESHOLD > 100:
            raise ValueError("FACE_MATCH_THRESHOLD must be between 0 and 100")
        
        if Config.OTP_EXPIRY_SECONDS < 30:
            raise ValueError("OTP_EXPIRY_SECONDS must be at least 30")
        
        if Config.LOCATION_DISTANCE_LIMIT_METERS < 10:
            raise ValueError("LOCATION_DISTANCE_LIMIT_METERS must be at least 10")
        
        # Validate file paths (Google Drive is optional)
        if os.path.exists(Config.GOOGLE_DRIVE_CREDENTIALS_PATH):
            Config.GOOGLE_DRIVE_CREDENTIALS_PATH = Config._resolve_path(Config.GOOGLE_DRIVE_CREDENTIALS_PATH)
        
        if os.path.exists(Config.GOOGLE_DRIVE_TOKEN_PATH):
            Config.GOOGLE_DRIVE_TOKEN_PATH = Config._resolve_path(Config.GOOGLE_DRIVE_TOKEN_PATH)
        
        # Create upload folder if it doesn't exist
        if not os.path.exists(Config.UPLOAD_FOLDER):
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        
        # Validate thread pool settings
        if Config.THREAD_POOL_MIN_WORKERS < 1:
            raise ValueError("THREAD_POOL_MIN_WORKERS must be at least 1")
        if Config.THREAD_POOL_MAX_WORKERS < Config.THREAD_POOL_MIN_WORKERS:
            raise ValueError("THREAD_POOL_MAX_WORKERS must be >= THREAD_POOL_MIN_WORKERS")
