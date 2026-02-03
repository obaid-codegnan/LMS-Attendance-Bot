# Face Recognition - Classroom Attendance System

A comprehensive, dual-bot attendance system integrating **Telegram**, **AWS Rekognition**, and **Supabase**. The system features separate workflows for Teachers (session management) and Students (location-based face verification).

## 🚀 Features & Technologies

### 1. Teacher Bot Service
*   **Role**: Manages attendance sessions and views reports.
*   **Technologies**:
    *   **Python-Telegram-Bot (Async)**: Handles conversation flow (Login, Batch Selection).
    *   **Supabase (PostgreSQL)**: stored teacher profiles and subject mappings.
    *   **AsyncIO**: Background tasks for auto-sending attendance reports after session expiry.
*   **Key Functions**:
    *   Secure Login (Phone Number Verification).
    *   Session Creation (Generates 6-digit OTP).
    *   Real-time Location Capture (Sets the "Geofence" center).

### 2. Student Bot Service
*   **Role**: Marks attendance securely on-site.
*   **Technologies**:
    *   **Python-Telegram-Bot**: Interactive interface for students.
    *   **Geopy**: precise distance calculation (Geodesic) to ensure student is within **300m** of the class.
    *   **OpenCV (cv2)**: Extracts frames from **Telegram Video Notes** (Liveness check) for processing.
    *   **AWS Rekognition**: Enterprise-grade face comparison against stored ID card photos.
    *   **Supabase RPC**: Dynamic handling of table columns (e.g., auto-creating subject columns like `sql`, `python` if missing).

### 3. Backend Core & API
*   **Framework**: **Flask** + **Flask-RESTful**.
*   **Deployment**: Multi-threaded execution (`threading`) to run both Telegram Bots alongside the HTTP API.
*   **Storage**: **AWS S3** (Student images & temp verification frames).
*   **Legacy Support**: Google Drive integration for batch file management.

---

## 🛠️ Setup & Configuration

### 1. Prerequisites
*   Python 3.10+
*   Supabase Project
*   AWS Account (Rekognition & S3 Access)
*   Telegram Bot Tokens (One for Teacher, One for Student)

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Environment Config (`.env`)
Create a `.env` file with the following:

```ini
# --- TELEGRAM BOTS ---
TEACHER_BOT_TOKEN=123456:ABC-DEF...
STUDENT_BOT_TOKEN=987654:XYZ-UVW...
# TELEGRAM_BOT_TOKEN=... (Legacy/Fallback)

# --- DATABASE (Supabase) ---
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# --- AWS (Face Recognition) ---
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=secret...
AWS_REGION=ap-south-1
AWS_S3_BUCKET=your-bucket-name
AWS_REKOGNITION_COLLECTION_ID=your-collection

# --- CONFIG ---
OTP_EXPIRY_SECONDS=300 # 5 Minutes
FACE_MATCH_THRESHOLD=80
```

### 4. Running the System
```bash
python run.py
```
*   Starts the Flask API on `localhost:5000`.
*   Launches **Teacher Bot** (Background Thread).
*   Launches **Student Bot** (Background Thread).

---

## 🔄 Workflow

### Teacher Flow
1.  **Start**: Teacher sends `/start`.
2.  **Verify**: Bot checks database for phone number.
3.  **Select**: Teacher selects **Batch** and **Subject**.
4.  **Launch**: Teacher shares **Live Location** -> Bot generates **OTP**.

### Student Flow
1.  **Start**: Student sends `/start` (or uses Deep Link).
2.  **Auth**: Enters **Student ID** + **Class OTP**.
3.  **Location Check**: Student shares location. System verifies distance < 300m from Teacher.
4.  **Liveness**: Student records a **Video Note** (Circle Video).
5.  **Verify**: System extracts frame -> AWS Rekognition compares with S3 ID Photo -> Marks Attendance in DB.

---

## 📂 Project Structure
```
facerecognition/
├── src/
│   ├── services/
│   │   ├── teacher_bot_service.py   # Teacher Logic
│   │   ├── student_bot_service.py   # Student Logic & Video Processing
│   │   ├── attendance_service.py    # Core Face Matching Logic
│   │   └── ...
│   ├── repositories/
│   │   ├── student_repository.py    # Supabase Interactions (RPC/Tables)
│   │   ├── face_repository.py       # AWS Rekognition Wrapper
│   │   └── ...
│   ├── config/settings.py           # Central Config
│   └── app.py                       # App Factory & Thread Management
├── .env                             # Secrets
├── run.py                           # Entry Point
└── README.md
```

## ⚠️ Common Issues & Fixes
*   **Missing Subject Column**: The system now auto-detects if a subject column (e.g., `sql`) is missing in Supabase and uses an RPC call (`ensure_subject_column`) to create it on the fly.
*   **Video Note Error**: If AWS fails with `InvalidParameterException`, it usually means the captured video frame was too empty or corrupted. The system logs these details for debugging.
























