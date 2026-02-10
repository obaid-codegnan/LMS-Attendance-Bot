# Face Recognition - Classroom Attendance System

A comprehensive, dual-bot attendance system integrating **Telegram**, **AWS Rekognition**, and **External LMS APIs**. The system features separate workflows for Teachers (session management) and Students (location-based face verification).

## 🚀 Features & Technologies

### 1. Teacher Bot Service
*   **Role**: Manages attendance sessions and views reports.
*   **Technologies**:
    *   **Python-Telegram-Bot (Async)**: Handles conversation flow with 30s timeout configuration.
    *   **MongoDB**: Stores teacher credentials, JWT tokens, and session data locally.
    *   **JWT Authentication**: Secure API access with access/refresh token pattern and MongoDB persistence.
    *   **External API Integration**: Fetches batches/subjects and submits attendance to LMS.
    *   **AsyncIO**: Background tasks for auto-sending attendance reports after session expiry.
*   **Key Functions**:
    *   Phone + Password + Email verification.
    *   JWT token management with automatic refresh and cross-restart persistence.
    *   Multi-batch selection with dynamic subject loading.
    *   Session Creation (Generates 6-digit OTP, expires in 120 seconds).
    *   Real-time Location Capture (Sets the "Geofence" center).
    *   Credential caching for returning teachers.
    *   Duplicate session prevention (same teacher/batch/subject/date).
    *   Automatic report generation 15 seconds after OTP expiry.

### 2. Student Bot Service
*   **Role**: Marks attendance securely on-site.
*   **Technologies**:
    *   **Python-Telegram-Bot**: Interactive interface with 30s timeout configuration.
    *   **Geopy**: Precise distance calculation (Geodesic) to ensure student is within **50m** of the class.
    *   **OpenCV (cv2)**: Extracts frames from **Telegram Video Notes** for processing.
    *   **AWS Rekognition**: Enterprise-grade face comparison (70% threshold).
    *   **Queue-based Processing**: Dynamic face verification queue with auto-scaling thread pools (2-100 workers).
*   **Key Features**:
    *   Student ID and OTP validation.
    *   50-meter geofence enforcement.
    *   Video note processing with immediate acknowledgment.
    *   Background face verification (sub-2 second processing).
    *   Automatic attendance submission with teacher JWT credentials.
    *   Retry mechanism (1 retry, 2 total attempts) with duplicate prevention.
    *   Clear error messages for missing ID photos.
    *   /help command with comprehensive instructions.

### 3. Backend Core & API
*   **Framework**: Telegram Bots (no web interface - data from LMS API).
*   **Deployment**: Multi-threaded execution (`threading`) to run both Telegram Bots.
*   **Storage**: 
    *   **AWS S3**: Student images in `codegnan-students-files/profile_pics/{student_id}.jpg`
    *   **MongoDB**: Teacher credentials, JWT tokens, sessions, retry tracking
*   **External API**: Integration with LMS API for student data and attendance submission.
*   **Performance**: Sub-2 second face recognition with concurrent processing.

---

## 🛠️ Setup & Configuration

### 1. Prerequisites
*   Python 3.10+
*   MongoDB Database
*   AWS Account (Rekognition & S3 Access)
*   Telegram Bot Tokens (One for Teacher, One for Student)
*   External LMS API Access

### 2. Installation
```bash
git clone https://github.com/obaid-codegnan/LMS-Attendance-Bot.git
cd LMS-Attendance-Bot
pip install -r requirements.txt
```

### 3. Environment Config
Copy `.env.example` to `.env` and configure:

```ini
# --- TELEGRAM BOTS ---
TEACHER_BOT_TOKEN=your_teacher_bot_token_here
STUDENT_BOT_TOKEN=your_student_bot_token_here

# --- DATABASE ---
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=lms_database

# --- AWS (Face Recognition) ---
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET=codegnan-students-files
AWS_S3_PREFIX=profile_pics/

# --- API ENDPOINTS ---
BASE_URL=http://your-lms-api.com/api/v1

# --- CONFIG ---
OTP_EXPIRY_SECONDS=120
LOCATION_DISTANCE_LIMIT_METERS=50
FACE_MATCH_THRESHOLD=70.0
FACE_VERIFICATION_MAX_RETRIES=1

# --- JWT AUTHENTICATION ---
JWT_LOGIN_ENDPOINT=https://login.codegnan.ai/api/v1/login
ENCRYPTION_KEY=your_encryption_key_here
```

### 4. Running the System
```bash
python main.py
```
*   Launches **Teacher Bot** (Background Thread).
*   Launches **Student Bot** (Background Thread).
*   Initializes **Face Verification Queue** with dynamic workers.
*   Starts **Session Cleanup Task** (runs every 5 minutes).

---

## 🔄 Current Workflow

### Teacher Flow
1.  **Start**: Teacher sends `/start` to Teacher Bot.
2.  **Phone Verification**: Teacher shares contact via Telegram.
3.  **Password Entry**: Teacher enters API login password.
4.  **Email Collection**: Teacher provides email/username.
5.  **JWT Authentication**: System authenticates with external API and stores credentials (encrypted).
6.  **Batch Loading**: System fetches available batches from external API using teacher's credentials.
7.  **Selection**: Teacher selects **Batches** (multi-select) and **Subject**.
8.  **Location**: Teacher shares **Live Location** → Bot generates **6-digit OTP**.
9.  **Session Creation**: 
    *   Fetches student list from external API for selected batches/subject.
    *   Checks for duplicate sessions (same teacher/batch/subject/date).
    *   Stores session in MongoDB with OTP, location, student data, and encrypted teacher credentials.
    *   Schedules automatic report generation after OTP expiry + 15 seconds.
10. **Report**: Teacher receives attendance report automatically via Telegram.

### Student Flow
1.  **Start**: Student sends `/start` to Student Bot.
2.  **Authentication**: Student enters **Student ID** + **Class OTP**.
3.  **Validation**: System validates OTP and checks if student is enrolled in the session.
4.  **Location Check**: Student shares location → System verifies distance < 50m from Teacher.
5.  **Face Verification**: 
    *   Student records a **Video Note** (Circle Video).
    *   System downloads video bytes and adds to verification queue.
    *   Background worker extracts middle frame and compares with S3 stored ID photo using AWS Rekognition.
    *   Attendance marked via external API using teacher's JWT credentials.
    *   **First student**: POST method creates new attendance record.
    *   **Subsequent students**: PUT method updates existing record.
    *   **Retry Logic**: If verification fails, student gets 1 retry (2 total attempts).
6.  **Result**: Student receives immediate confirmation of attendance status.

### API Integration Flow
1.  **Teacher Authentication**: JWT login with access/refresh tokens (persisted in MongoDB).
2.  **Batch/Subject Fetch**: Using teacher's credentials from external API.
3.  **Student Data**: `POST /attend` - Fetch students for batch/subject.
4.  **Attendance Submission**: 
    *   First student in session: `POST /attendance` (creates record)
    *   Subsequent students: `PUT /attendance` (updates record)
    *   Duplicate handling: 403 errors treated as success
5.  **Report Generation**: Automatic attendance report sent to teacher 15 seconds after OTP expiry.

---

## 📊 Performance Metrics

### Face Recognition Optimization
*   **Before**: 10.5+ seconds per verification
*   **After**: 1.24 seconds per verification
*   **Improvement**: 88% faster processing

### System Performance
*   **Concurrent Students**: 500+ supported
*   **Thread Pool**: Auto-scaling 2-100 workers
*   **API Caching**: 5-minute cache reduces teacher bot response time
*   **Queue Processing**: Immediate user feedback with background processing
*   **JWT Token Persistence**: Tokens survive application restarts

### Timing Breakdown (Typical Student)
*   Face Recognition: 1.24s
*   API Submission: 1.41s  
*   Response Processing: 1.06s
*   **Total**: 2.98s (under 3 seconds)

---

## 📂 Project Structure
```
LMS-Attendance-Bot/
├── src/
│   ├── services/
│   │   ├── teacher_bot_service.py   # Teacher Logic & API Integration
│   │   ├── student_bot_service.py   # Student Logic & Video Processing
│   │   ├── face_recognition_service.py # AWS Rekognition & S3 Integration
│   │   ├── api_service.py           # External API Communication
│   │   └── api_attendance_service.py # Attendance API Wrapper
│   ├── repositories/
│   │   ├── mongo_repository.py      # MongoDB Operations
│   │   ├── face_repository.py       # AWS Rekognition Operations
│   │   └── s3_repository.py         # AWS S3 Operations
│   ├── utils/
│   │   ├── face_verification_queue.py # Queue-based Processing
│   │   ├── error_responses.py       # Structured Error Handling
│   │   ├── credential_manager.py    # Password Encryption
│   │   └── ...
│   ├── config/
│   │   ├── settings.py              # Central Configuration
│   │   └── bot_messages.json        # Bot Message Templates
│   └── ...
├── .env                             # Environment Configuration
├── main.py                          # Application Entry Point
└── README.md
```

---

## 🔧 Key Features

### Performance Optimizations
*   **Video Processing**: Single download with bytes processing (eliminates duplicate downloads)
*   **Frame Extraction**: Optimized to single middle frame (50% position) for speed
*   **API Caching**: Class-level shared cache for teacher bot responses
*   **Async Processing**: Non-blocking operations with thread pools
*   **Dynamic Scaling**: CPU-based worker allocation (80% project, 20% system)
*   **Image Caching**: S3 images cached in memory for retry scenarios

### Security & Reliability
*   **Location Verification**: 50m geofence validation
*   **Face Recognition**: AWS Rekognition with 70% similarity threshold
*   **Session Management**: OTP-based secure sessions with 120-second expiry
*   **Password Encryption**: Fernet encryption for stored credentials
*   **JWT Token Persistence**: Tokens stored in MongoDB, survive restarts
*   **Error Handling**: Comprehensive logging and graceful failure handling
*   **Duplicate Prevention**: Session and attendance duplicate checks

### Scalability
*   **Queue System**: Handles 500+ concurrent students
*   **Thread Pools**: Auto-scaling based on system resources
*   **Caching**: Reduces external API load
*   **Async Architecture**: Non-blocking operations throughout
*   **Session Cleanup**: Automatic cleanup every 5 minutes

### Data Management
*   **MongoDB Collections**:
    *   `teachers` - Teacher credentials and encrypted passwords
    *   `sessions` - Active attendance sessions with OTP and location
    *   `jwt_tokens` - Persisted JWT tokens for cross-restart authentication
*   **AWS S3 Structure**: `codegnan-students-files/profile_pics/{student_id}.jpg`
*   **No Web Interface**: Student data managed through LMS API

---

## 🚀 Deployment

### Production Setup
1. Configure environment variables in `.env`
2. Set up MongoDB database
3. Configure AWS S3 bucket and Rekognition access
4. Upload student ID photos to S3: `profile_pics/{student_id}.jpg`
5. Run with process manager (PM2, systemd, etc.)

### Monitoring
*   Built-in logging with timing metrics
*   Queue status monitoring
*   API response time tracking
*   Error rate monitoring
*   Session cleanup logs

---

## 📞 Support

For issues or questions:
1. Check logs for detailed error information
2. Verify environment configuration
3. Ensure external API connectivity
4. Validate AWS credentials and permissions
5. Check MongoDB connection

---

## 🔄 Recent Updates

### Improvements Implemented:
1. ✅ Removed duplicate code in api_service.py
2. ✅ Removed unused AWS_REKOGNITION_COLLECTION_ID
3. ✅ Fixed README geofence distance (300m → 50m)
4. ✅ Added session cleanup for expired OTPs (every 5 minutes)
5. ✅ Added structured error responses with standard error codes
6. ✅ JWT token persistence in MongoDB (survive restarts)
7. ✅ Removed web interface (data from LMS API)
8. ✅ Reduced report delay (30s → 15s after OTP expiry)
9. ✅ Removed unused temp_uploads folder

### System Optimizations:
*   Face verification retry mechanism (1 retry, 2 total attempts)
*   Duplicate submission prevention
*   Conversation flow improvements (stay in SELFIE state for retries)
*   Shutdown timeout reduced (30s → 5s)
*   Help commands added to both bots
*   Session cleanup integrated with queue cleanup task
