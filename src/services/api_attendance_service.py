"""
API Attendance Service
Handles attendance by sending data to external API
"""
import logging
import requests
import asyncio
from typing import Dict, List
from datetime import datetime
from functools import partial
from src.services.api_service import APIService

logger = logging.getLogger(__name__)

class APIAttendanceService:
    """Service to handle attendance via external API."""
    
    def __init__(self):
        self.api_service = APIService()
    
    async def _check_existing_attendance(self, batch: str, subject: str, teacher_credentials: dict = None) -> bool:
        """Check if attendance record exists for today."""
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            url = f"{self.api_service.base_url}/getattends"
            params = {
                "location": "vijayawada",
                "subject": subject,
                "batch": batch,
                "userType": "Mentor"
            }
            
            # Use teacher credentials if available
            if teacher_credentials:
                headers = self.api_service._get_headers(
                    teacher_credentials.get('username'),
                    teacher_credentials.get('password')
                )
            else:
                headers = self.api_service._get_headers()
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            logger.info(f"Checking existing attendance: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                data_list = data.get("data", [])
                
                for date_item in data_list:
                    if isinstance(date_item, dict):
                        # Check both formats
                        if 'dates' in date_item and date in date_item['dates']:
                            subjects_data = date_item['dates'][date]
                            exists = subject in subjects_data
                            logger.info(f"Found attendance record (dates format): {exists}")
                            return exists
                        elif date in date_item:
                            subjects_data = date_item[date]
                            exists = subject in subjects_data
                            logger.info(f"Found attendance record (direct format): {exists}")
                            return exists
                            
            logger.info("No existing attendance record found")
            return False
        except Exception as e:
            logger.error(f"Error checking existing attendance: {e}")
            return False
    
    async def _create_attendance(self, student_id: str, batch: str, subject: str, students: list, teacher_credentials: dict = None) -> bool:
        """Create new attendance record using POST."""
        try:
            attendance_students = []
            for student in students:
                sid = student.get('studentId')
                status = 1 if sid == student_id else 0
                attendance_students.append({
                    "studentId": sid,
                    "status": status
                })
            
            attendance_data = {
                "subject": subject,
                "batch": batch,
                "datetime": datetime.now().strftime("%Y-%m-%d"),
                "location": "vijayawada",
                "userType": "Mentor",
                "students": attendance_students
            }
            
            if teacher_credentials:
                success = await self.api_service.send_attendance_to_api_with_auth_async(
                    attendance_data, 
                    method="POST",
                    username=teacher_credentials['username'],
                    password=teacher_credentials['password']
                )
            else:
                success = await self.api_service.send_attendance_to_api_async(attendance_data, method="POST")
            
            logger.info(f"Created attendance record for {batch}/{subject} with {student_id} present")
            return success
            
        except Exception as e:
            logger.error(f"Error creating attendance: {e}")
            return False
    
    async def _update_attendance(self, student_id: str, batch: str, subject: str, students: list, teacher_credentials: dict = None) -> bool:
        """Update existing attendance record using PUT."""
        try:
            # Small delay to avoid race conditions
            await asyncio.sleep(0.5)
            
            # Get current attendance to preserve existing statuses
            current_attendance = await self._get_current_attendance(batch, subject, teacher_credentials)
            logger.info(f"Updating for {student_id}: Current has {sum(1 for s in current_attendance.values() if s == 1)} present")
            
            attendance_students = []
            for student in students:
                sid = student.get('studentId')
                existing_status = current_attendance.get(sid, 0)
                status = 1 if (sid == student_id or existing_status == 1) else 0
                attendance_students.append({"studentId": sid, "status": status})
            
            present_count = sum(1 for s in attendance_students if s['status'] == 1)
            logger.info(f"Sending PUT with {present_count} present (adding {student_id})")
            
            attendance_data = {
                "subject": subject,
                "batch": batch,
                "datetime": datetime.now().strftime("%Y-%m-%d"),
                "location": "vijayawada",
                "userType": "Mentor",
                "students": attendance_students
            }
            
            if teacher_credentials:
                success = await self.api_service.send_attendance_to_api_with_auth_async(
                    attendance_data, method="PUT",
                    username=teacher_credentials['username'],
                    password=teacher_credentials['password']
                )
            else:
                success = await self.api_service.send_attendance_to_api_async(attendance_data, method="PUT")
            
            logger.info(f"Updated {batch}/{subject} with {student_id} present")
            return success
            
        except Exception as e:
            logger.error(f"Error updating attendance: {e}")
            return False
    
    async def _get_current_attendance(self, batch: str, subject: str, teacher_credentials: dict = None) -> dict:
        """Get current attendance statuses."""
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            url = f"{self.api_service.base_url}/getattends"
            params = {
                "location": "vijayawada",
                "subject": subject,
                "batch": batch,
                "userType": "Mentor"
            }
            
            # Use teacher credentials if available
            if teacher_credentials:
                headers = self.api_service._get_headers(
                    teacher_credentials.get('username'),
                    teacher_credentials.get('password')
                )
            else:
                headers = self.api_service._get_headers()
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            logger.info(f"Getting current attendance: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                data_list = data.get("data", [])
                
                for date_item in data_list:
                    if isinstance(date_item, dict):
                        subjects_data = None
                        if 'dates' in date_item and date in date_item['dates']:
                            subjects_data = date_item['dates'][date]
                        elif date in date_item:
                            subjects_data = date_item[date]
                        
                        if subjects_data and subject in subjects_data:
                            students = subjects_data[subject].get("students", [])
                            attendance_dict = {s.get("studentId"): s.get("status", 0) for s in students}
                            logger.info(f"Current attendance has {len(attendance_dict)} students, {sum(1 for s in attendance_dict.values() if s == 1)} present")
                            logger.debug(f"Present students: {[sid for sid, status in attendance_dict.items() if status == 1]}")
                            return attendance_dict
            
            logger.warning("No current attendance found - returning empty dict")
            return {}
        except Exception as e:
            logger.error(f"Error getting current attendance: {e}")
            return {}
    
    async def mark_student_present_async(self, student_id: str, batch: str, subject: str, mentor_id: str = None, teacher_credentials: dict = None) -> bool:
        """Mark student present using POST for first, PUT for subsequent."""
        try:
            # Get all students for this session using teacher's credentials
            if teacher_credentials:
                logger.info(f"Using teacher credentials: {teacher_credentials.get('username', 'N/A')}")
                
                # Authenticate with teacher credentials first
                auth_success = await self.api_service.authenticate_async(
                    teacher_credentials['username'], 
                    teacher_credentials['password']
                )
                if not auth_success:
                    logger.error(f"Failed to authenticate teacher for attendance marking")
                    return False
                
                # Use async executor to call the sync method
                loop = asyncio.get_event_loop()
                students = await loop.run_in_executor(
                    None,
                    self.api_service.get_students_for_session_with_auth,
                    batch, subject, 
                    teacher_credentials['username'], 
                    teacher_credentials['password']
                )
            else:
                logger.warning("No teacher credentials available, using default authentication")
                loop = asyncio.get_event_loop()
                students = await loop.run_in_executor(
                    None,
                    self.api_service.get_students_for_session,
                    batch, subject
                )
            
            if not students:
                logger.error(f"No students found for batch {batch}, subject {subject}")
                return False
            
            # Check if attendance already exists for this batch/subject today
            existing_attendance = await self._check_existing_attendance(batch, subject, teacher_credentials)
            
            if existing_attendance:
                # Attendance record exists - use PUT to update
                logger.info(f"Attendance exists for {batch}/{subject} - using PUT method")
                return await self._update_attendance(student_id, batch, subject, students, teacher_credentials)
            else:
                # No attendance record - use POST to create first entry
                logger.info(f"No attendance found for {batch}/{subject} - using POST method (first student)")
                return await self._create_attendance(student_id, batch, subject, students, teacher_credentials)
                
        except Exception as e:
            logger.error(f"Error marking student present: {e}")
            return False
    
    def get_attendance_report(self, batch: str, subject: str, date: str = None, session_data: dict = None) -> Dict:
        """Get attendance report from API - handles multi-batch sessions."""
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # Handle multi-batch sessions
            batches = [b.strip() for b in batch.split(',')]
            
            all_present = []
            all_absent = []
            
            # Use teacher credentials from session if available
            teacher_credentials = session_data.get('teacher_credentials') if session_data else None
            if teacher_credentials:
                headers = self.api_service._get_headers(
                    teacher_credentials.get('username'),
                    teacher_credentials.get('password')
                )
            else:
                headers = self.api_service._get_headers()
            
            # Fetch attendance for each batch
            for batch_name in batches:
                url = f"{self.api_service.base_url}/getattends"
                params = {
                    "location": "vijayawada",
                    "subject": subject,
                    "batch": batch_name,
                    "userType": "Mentor"
                }
                
                logger.info(f"Fetching attendance report for batch {batch_name} with params: {params}")
                
                response = requests.get(url, params=params, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    data_list = data.get("data", [])
                    
                    for date_item in data_list:
                        if isinstance(date_item, dict):
                            subjects_data = None
                            
                            # Check both formats
                            if 'dates' in date_item and date in date_item['dates']:
                                subjects_data = date_item['dates'][date]
                            elif date in date_item:
                                subjects_data = date_item[date]
                            
                            if subjects_data and subject in subjects_data:
                                subject_data = subjects_data[subject]
                                students = subject_data.get("students", [])
                                
                                for student in students:
                                    student_id = student.get("studentId")
                                    status = student.get("status", 0)
                                    name = student.get("name", "")
                                    
                                    if student_id:
                                        if status == 1:
                                            all_present.append(f"{student_id} - {name}")
                                        else:
                                            all_absent.append(f"{student_id} - {name}")
                                
                                break
            
            return {
                "present": all_present,
                "absent": all_absent,
                "total": len(all_present) + len(all_absent),
                "date": date,
                "batch": batch,
                "subject": subject
            }
            
        except Exception as e:
            logger.error(f"Error getting attendance report: {e}")
            return {"present": [], "absent": [], "total": 0, "date": date or datetime.now().strftime("%Y-%m-%d"), "batch": batch, "subject": subject}