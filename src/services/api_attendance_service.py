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
    
    async def _check_existing_attendance(self, batch: str, subject: str) -> bool:
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
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                data_list = data.get("data", [])
                
                for date_item in data_list:
                    if isinstance(date_item, dict):
                        if 'dates' in date_item and date in date_item['dates']:
                            return subject in date_item['dates'][date]
                        elif date in date_item:
                            return subject in date_item[date]
                            
            return False
        except Exception as e:
            logger.error(f"Error checking existing attendance: {e}")
            return False
    
    async def _create_attendance(self, student_id: str, batch: str, subject: str, students: list) -> bool:
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
            
            success = await self.api_service.send_attendance_to_api_async(attendance_data, method="POST")
            logger.info(f"Created attendance record for {batch}/{subject} with {student_id} present")
            return success
            
        except Exception as e:
            logger.error(f"Error creating attendance: {e}")
            return False
    
    async def _update_attendance(self, student_id: str, batch: str, subject: str, students: list) -> bool:
        """Update existing attendance record using PUT."""
        try:
            # Get current attendance to preserve existing statuses
            current_attendance = await self._get_current_attendance(batch, subject)
            
            attendance_students = []
            for student in students:
                sid = student.get('studentId')
                # Keep existing status or mark new student present
                existing_status = current_attendance.get(sid, 0)
                status = 1 if (sid == student_id or existing_status == 1) else 0
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
            
            success = await self.api_service.send_attendance_to_api_async(attendance_data, method="PUT")
            logger.info(f"Updated attendance record for {batch}/{subject} with {student_id} present")
            return success
            
        except Exception as e:
            logger.error(f"Error updating attendance: {e}")
            return False
    
    async def _get_current_attendance(self, batch: str, subject: str) -> dict:
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
            
            response = requests.get(url, params=params, timeout=10)
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
                            return {s.get("studentId"): s.get("status", 0) for s in students}
            
            return {}
        except Exception as e:
            logger.error(f"Error getting current attendance: {e}")
            return {}
    
    async def mark_student_present_async(self, student_id: str, batch: str, subject: str, mentor_id: str = None) -> bool:
        """Mark student present using POST for first, PUT for subsequent."""
        try:
            # Check if attendance record exists for this batch/subject today
            session_key = f"{batch}:{subject}"
            
            # Get all students for this session
            students = self.api_service.get_students_for_session(batch, subject)
            if not students:
                logger.error(f"No students found for batch {batch}, subject {subject}")
                return False
            
            # Check if attendance already exists
            existing_attendance = await self._check_existing_attendance(batch, subject)
            
            if existing_attendance:
                # Use PUT to update existing attendance
                return await self._update_attendance(student_id, batch, subject, students)
            else:
                # Use POST to create new attendance
                return await self._create_attendance(student_id, batch, subject, students)
                
        except Exception as e:
            logger.error(f"Error marking student present: {e}")
            return False
    
    def get_attendance_report(self, batch: str, subject: str, date: str = None, session_data: dict = None) -> Dict:
        """Get attendance report from API."""
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # Get attendance data from API
            url = f"{self.api_service.base_url}/getattends"
            params = {
                "location": "vijayawada",
                "subject": subject,
                "batch": batch,
                "userType": "Mentor"
            }
            
            logger.info(f"Fetching attendance report with params: {params}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse the correct response format: {"data": [{"2026-02-02": {"Python": {"students": [...]}}}]}
                present = []
                absent = []
                
                # Navigate through the nested structure
                data_list = data.get("data", [])
                
                for i, date_item in enumerate(data_list):
                    if isinstance(date_item, dict):
                        # Check if this item has a 'dates' field
                        if 'dates' in date_item:
                            dates_data = date_item['dates']
                            
                            # Look for today's date in the dates data
                            if date in dates_data:
                                subjects_data = dates_data[date]
                                
                                if subject in subjects_data:
                                    subject_data = subjects_data[subject]
                                    students = subject_data.get("students", [])
                                    
                                    for student in students:
                                        student_id = student.get("studentId")
                                        status = student.get("status", 0)
                                        name = student.get("name", "")
                                        
                                        if student_id:
                                            if status == 1:
                                                present.append(f"{student_id} - {name}")
                                            else:
                                                absent.append(f"{student_id} - {name}")
                                    
                                    break  # Found the subject, no need to continue
                            else:
                                logger.warning(f"Date {date} not found in dates. Available dates: {list(dates_data.keys()) if isinstance(dates_data, dict) else 'None'}")
                        else:
                            # Fallback: check if date is directly in the item (old format)
                            if date in date_item:
                                subjects_data = date_item[date]
                                
                                if subject in subjects_data:
                                    subject_data = subjects_data[subject]
                                    students = subject_data.get("students", [])
                                    
                                    for student in students:
                                        student_id = student.get("studentId")
                                        status = student.get("status", 0)
                                        name = student.get("name", "")
                                        
                                        if student_id:
                                            if status == 1:
                                                present.append(f"{student_id} - {name}")
                                            else:
                                                absent.append(f"{student_id} - {name}")
                                    
                                    break  # Found the subject, no need to continue
                
                return {
                    "present": present,
                    "absent": absent,
                    "total": len(present) + len(absent),
                    "date": date,
                    "batch": batch,
                    "subject": subject
                }
            else:
                logger.error(f"Failed to get attendance report: {response.status_code} - {response.text[:200]}")
                return {"present": [], "absent": [], "total": 0, "date": date, "batch": batch, "subject": subject}
            
        except Exception as e:
            logger.error(f"Error getting attendance report: {e}")
            return {"present": [], "absent": [], "total": 0, "date": date or datetime.now().strftime("%Y-%m-%d")}