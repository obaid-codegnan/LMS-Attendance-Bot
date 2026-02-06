# Face Recognition - Classroom Attendance System

A comprehensive, dual-bot attendance system integrating **Telegram**, **AWS Rekognition**, and **External APIs**. The system features separate workflows for Teachers (session management) and Students (location-based face verification).

## 🚀 Features & Technologies

### 1. Teacher Bot Service
*   **Role**: Manages attendance sessions and views reports.
*   **Technologies**:
    *   **Python-Telegram-Bot (Async)**: Handles conversation flow with 30s timeout configuration.
    *   **MongoDB**: Stores teacher credentials and session data locally.
    *   **JWT Authentication**: Secure API access with access/refresh token pattern.
    *   **External API Integration**: Fetches batches/subjects and submits attendance.
    *   **AsyncIO**: Background tasks for auto-sending attendance reports after session expiry.
*   **Key Functions**:
    *   Phone + Password + Email verification.
    *   JWT token management with automatic refresh.
    *   Multi-batch selection with dynamic subject loading.
    *   Session Creation (Generates 6-digit OTP, expires in 90 seconds).
    *   Real-time Location Capture (Sets the "Geofence" center).
    *   Credential caching for returning teachers.

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
    *   Clear error messages for missing ID photos.

### 3. Backend Core & API
*   **Framework**: **Flask** + **Flask-RESTful**.
*   **Deployment**: Multi-threaded execution (`threading`) to run both Telegram Bots alongside the HTTP API.
*   **Storage**: **AWS S3** (Student images & temp verification frames).
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
MONGODB_URI=mongodb://localhost:27017/attendance_db

# --- AWS (Face Recognition) ---
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET=your-bucket-name
AWS_REKOGNITION_COLLECTION_ID=your-collection

# --- API ENDPOINTS ---
BASE_URL=http://your-lms-api.com/api/v1
OLD_BASE_URL=http://your-lms-api.com/api/v1

# --- CONFIG ---
OTP_EXPIRY_SECONDS=90
LOCATION_DISTANCE_LIMIT_METERS=50
FACE_MATCH_THRESHOLD=70

# --- JWT AUTHENTICATION ---
JWT_LOGIN_ENDPOINT=https://login.codegnan.ai/api/v1/login
```

### 4. Running the System
```bash
python main.py
```
*   Starts the Flask API on `localhost:5000`.
*   Launches **Teacher Bot** (Background Thread).
*   Launches **Student Bot** (Background Thread).
*   Initializes **Face Verification Queue** with dynamic workers.

---

## 🔄 Current Workflow

### Teacher Flow
1.  **Start**: Teacher sends `/start` to Teacher Bot.
2.  **Phone Verification**: Teacher shares contact via Telegram.
3.  **Password Entry**: Teacher enters API login password.
4.  **Email Collection**: Teacher provides email/username.
5.  **JWT Authentication**: System authenticates with external API and stores credentials.
6.  **Batch Loading**: System fetches available batches from external API using teacher's credentials.
7.  **Selection**: Teacher selects **Batches** (multi-select) and **Subject**.
8.  **Location**: Teacher shares **Live Location** → Bot generates **6-digit OTP**.
9.  **Session Creation**: 
    *   Fetches student list from external API for selected batches/subject.
    *   Stores session in MongoDB with OTP, location, student data, and teacher credentials.
    *   Schedules automatic report generation after OTP expiry (90 seconds).

### Student Flow
1.  **Start**: Student sends `/start` to Student Bot.
2.  **Authentication**: Student enters **Student ID** + **Class OTP**.
3.  **Validation**: System validates OTP and checks if student is enrolled in the session.
4.  **Location Check**: Student shares location → System verifies distance < 50m from Teacher.
5.  **Face Verification**: 
    *   Student records a **Video Note** (Circle Video).
    *   System downloads video bytes and adds to verification queue.
    *   Background worker extracts frame and compares with S3 stored ID photo using AWS Rekognition.
    *   Attendance marked via external API using teacher's JWT credentials.
    *   **First student**: POST method creates new attendance record.
    *   **Subsequent students**: PUT method updates existing record.
6.  **Result**: Student receives immediate confirmation of attendance status.

### API Integration Flow
1.  **Teacher Authentication**: JWT login with access/refresh tokens.
2.  **Batch/Subject Fetch**: Using teacher's credentials from external API.
3.  **Student Data**: `POST /attend` - Fetch students for batch/subject.
4.  **Attendance Submission**: 
    *   First student in session: `POST /attendance` (creates record)
    *   Subsequent students: `PUT /attendance` (updates record)
    *   Duplicate handling: 403 errors treated as success
5.  **Report Generation**: Automatic attendance report sent to teacher after session expiry.

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
│   │   └── s3_repository.py         # AWS S3 Operations
│   ├── utils/
│   │   ├── face_verification_queue.py # Queue-based Processing
│   │   └── ...
│   ├── config/settings.py           # Central Configuration
│   └── web/                         # Flask Web Interface
├── .env.example                     # Environment Template
├── main.py                          # Application Entry Point
└── README.md
```

---

## 🔧 Key Features

### Performance Optimizations
*   **Video Processing**: Single download with bytes processing (eliminates duplicate downloads)
*   **Frame Extraction**: Optimized to single frame (frame 7) for speed
*   **API Caching**: Class-level shared cache for teacher bot responses
*   **Async Processing**: Non-blocking operations with thread pools
*   **Dynamic Scaling**: CPU-based worker allocation (80% project, 20% system)

### Security & Reliability
*   **Location Verification**: 300m geofence validation
*   **Face Recognition**: AWS Rekognition with configurable threshold
*   **Session Management**: OTP-based secure sessions with expiry
*   **Error Handling**: Comprehensive logging and graceful failure handling
*   **Rate Limiting**: Built-in protection against abuse

### Scalability
*   **Queue System**: Handles 500+ concurrent students
*   **Thread Pools**: Auto-scaling based on system resources
*   **Caching**: Reduces external API load
*   **Async Architecture**: Non-blocking operations throughout

---

## 🚀 Deployment

### Production Setup
1. Configure environment variables in `.env`
2. Set up MongoDB database
3. Configure AWS S3 bucket and Rekognition collection
4. Upload student ID photos to S3 in format: `students/{batch}/{studentId}.jpg`
5. Run with process manager (PM2, systemd, etc.)

### Monitoring
*   Built-in logging with timing metrics
*   Queue status monitoring
*   API response time tracking
*   Error rate monitoring

---

## 📞 Support

For issues or questions:
1. Check logs for detailed error information
2. Verify environment configuration
3. Ensure external API connectivity
4. Validate AWS credentials and permissions
























