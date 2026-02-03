"""
External API Service for fetching attendance data
"""
import logging
import requests
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
from src.config.settings import Config
from dotenv import load_dotenv
import os
# Load .env from current working directory
load_dotenv()
logger = logging.getLogger(__name__)

class APIService:
    """Service to interact with external attendance API."""
    
    # Class-level cache shared across instances
    _shared_cache = {}
    _cache_ttl = 300  # 5 minutes
    
    def __init__(self):
        self.base_url = os.getenv("BASE_URL", "http://192.168.88.9:7002/api/v1")  # Remove trailing slash
        self.old_base_url = os.getenv("OLD_BASE_URL", "http://192.168.88.9:7002/api/v1")
        
        # Dynamic worker allocation based on system resources
        worker_config = Config.get_optimal_workers()
        max_workers = worker_config['api_workers']
        
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="APIService")
        logger.info(f"API service initialized with {max_workers} workers (CPU cores: {worker_config['cpu_count']}, allocated: {worker_config['project_cores']})")
    
    def get_teacher_attendance_data(self, mentor_id: str) -> Optional[Dict]:
        """Get attendance data for a mentor from external API with caching."""
        import time
        
        # Check shared cache first
        cache_key = f"attendance_{mentor_id}"
        now = time.time()
        
        if cache_key in self._shared_cache:
            cached_data, cached_time = self._shared_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                logger.info(f"Using cached data for mentor {mentor_id} (age: {now - cached_time:.1f}s)")
                return cached_data
        
        try:
            api_start = time.time()
            url = f"{self.old_base_url}/attendance"
            params = {
                "mentorId": mentor_id,
                "role": "Mentor"
            }
            
            logger.info(f"Calling API: {url} with mentorId: {mentor_id}")
            
            response = requests.get(url, params=params, timeout=5)  # Reduced timeout
            api_time = time.time() - api_start
            
            logger.info(f"API Response Time: {api_time:.2f}s, Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                # Cache the result in shared cache
                self._shared_cache[cache_key] = (data, now)
                logger.info(f"Successfully fetched and cached attendance data for mentor {mentor_id}")
                return data
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            api_time = time.time() - api_start if 'api_start' in locals() else 0
            logger.error(f"Error calling attendance API (took {api_time:.2f}s): {e}")
            return None
    
    def get_available_batches_and_subjects(self, mentor_id: str) -> Dict[str, List[str]]:
        """Get available batches and their subjects for a mentor."""
        import time
        
        try:
            process_start = time.time()
            data = self.get_teacher_attendance_data(mentor_id)
            
            if not data:
                return {}
            
            # Extract batches and subjects from attendancePending
            batch_subject_map = {}
            
            for item in data.get("attendancePending", []):
                batch_no = item.get("batchNo")
                subject = item.get("subject")
                
                if batch_no and subject:
                    if batch_no not in batch_subject_map:
                        batch_subject_map[batch_no] = []
                    if subject not in batch_subject_map[batch_no]:
                        batch_subject_map[batch_no].append(subject)
            
            process_time = time.time() - process_start
            logger.info(f"Found {len(batch_subject_map)} batches for mentor {mentor_id} (processing: {process_time:.2f}s)")
            return batch_subject_map
            
        except Exception as e:
            logger.error(f"Error processing attendance data: {e}")
            return {}
    
    def get_students_for_session(self, batch: str, subject: str, location: str = "vijayawada") -> List[Dict]:
        """Get students for a specific batch/subject session."""
        try:
            url = f"{self.base_url}/attend"
            payload = {
                "batches": batch,
                "subject": subject,
                "location": location
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            logger.info(f"Calling: {url}")
            logger.info(f"Payload: {payload}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                students = data.get("students_data", [])
                
                # Debug: Log student IDs being fetched
                student_ids = [s.get('studentId') for s in students if s.get('studentId')]
                logger.info(f"SUCCESS: Fetched {len(students)} students for {batch}/{subject}")
                logger.info(f"Student IDs: {student_ids}")
                
                return students
            else:
                logger.error(f"Failed: {response.status_code} - {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching students: {e}")
            return []
    def send_attendance_to_api(self, attendance_data: Dict, method: str = "POST") -> bool:
        """Send attendance data to API with specified method."""
        try:
            url = f"{self.base_url}/attendance"
            
            if method.upper() == "POST":
                response = requests.post(url, json=attendance_data, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, json=attendance_data, timeout=10)
            else:
                logger.error(f"Unsupported method: {method}")
                return False
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully sent attendance data to API using {method}")
                return True
            else:
                logger.error(f"Failed to send attendance data. Method: {method}, Status: {response.status_code}, Response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending attendance to API: {e}")
            return False
    
    def cleanup(self):
        """Cleanup thread pool resources."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
            logger.info("API service thread pool shut down")
    
    async def send_attendance_to_api_async(self, attendance_data: Dict, method: str = "POST") -> bool:
        """Send attendance data to API asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                partial(self.send_attendance_to_api, attendance_data, method)
            )
            return result
        except Exception as e:
            logger.error(f"Async API call error: {e}")
            return False
    
    def send_attendance_update_to_api(self, update_data: Dict) -> bool:
        """Send attendance update to API (for individual student updates)."""
        try:
            # Try update endpoint first
            update_url = f"{self.base_url}/attendance/update"
            
            response = requests.put(update_url, json=update_data, timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully updated attendance for student {update_data.get('studentId')}")
                return True
            elif response.status_code == 404:
                # Update endpoint doesn't exist, return False to trigger create
                logger.debug("Update endpoint not available, will create new attendance")
                return False
            else:
                logger.error(f"Failed to update attendance. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.debug(f"Update request failed (expected): {e}")
            return False