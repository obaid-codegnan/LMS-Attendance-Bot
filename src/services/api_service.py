"""
External API Service for fetching attendance data
"""
import logging
import requests
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
import time
import jwt
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
    _access_tokens = {}  # Store access tokens per user
    _refresh_tokens = {}  # Store refresh tokens per user
    
    def __init__(self):
        self.base_url = os.getenv("BASE_URL", "https://attendance.codegnan.ai/api/v1")  # Remove trailing slash
        self.old_base_url = os.getenv("OLD_BASE_URL", "https://attendance.codegnan.ai/api/v1")
        
        # JWT configuration
        self.jwt_secret = os.getenv("JWT_SECRET_KEY")
        self.jwt_username = os.getenv("JWT_USERNAME")
        self.jwt_password = os.getenv("JWT_PASSWORD")
        self.jwt_login_endpoint = os.getenv("JWT_LOGIN_ENDPOINT", "/auth/login")
        
        # Dynamic worker allocation based on system resources
        worker_config = Config.get_optimal_workers()
        max_workers = worker_config['api_workers']
        
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="APIService")
        logger.info(f"API service initialized with {max_workers} workers (CPU cores: {worker_config['cpu_count']}, allocated: {worker_config['project_cores']})")
    
    def _get_access_token(self, username: str = None, password: str = None) -> Optional[str]:
        """Get or refresh access token using refresh token if available."""
        auth_username = username or self.jwt_username
        auth_password = password or self.jwt_password
        
        if not auth_username or not auth_password:
            logger.debug("No JWT credentials configured, skipping authentication")
            return None
        
        current_time = time.time()
        user_key = auth_username
        
        logger.debug(f"Getting access token for user: {user_key}")
        
        # Check if we have a valid access token
        if user_key in self._access_tokens:
            token_data, expiry = self._access_tokens[user_key]
            if current_time < (expiry - 60):  # 1 minute buffer
                logger.debug(f"Using cached token for {user_key}")
                return token_data
            else:
                logger.debug(f"Token expired for {user_key}, will refresh")
        
        # Try to refresh using refresh token first
        if user_key in self._refresh_tokens:
            refresh_token, refresh_expiry = self._refresh_tokens[user_key]
            if current_time < refresh_expiry:
                logger.debug(f"Attempting token refresh for {user_key}")
                new_access_token = self._refresh_access_token(refresh_token)
                if new_access_token:
                    return new_access_token
        
        # Login to get new tokens
        logger.debug(f"Performing fresh login for {user_key}")
        return self._login_and_get_tokens(auth_username, auth_password)
    
    def _login_and_get_tokens(self, username: str, password: str) -> Optional[str]:
        """Login and store both access and refresh tokens."""
        try:
            # First, logout all existing sessions
            self._logout_all_sessions(username, password)
            
            login_url = self.jwt_login_endpoint  # Use full URL directly
            login_data = {
                "email": username,
                "password": password
            }
            
            logger.info(f"Sending login request to: {login_url}")
            logger.info(f"Login payload: {login_data}")
            
            response = requests.post(login_url, json=login_data, timeout=10)
            
            logger.info(f"Login response status: {response.status_code}")
            logger.info(f"Login response body: {response.text[:200]}")
            
            if response.status_code == 200:
                token_data = response.json()
                # Extract tokens from nested data structure
                data = token_data.get("data", {})
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token")
                
                if access_token and refresh_token:
                    # Decode tokens to get expiry times
                    try:
                        access_decoded = jwt.decode(access_token, options={"verify_signature": False})
                        refresh_decoded = jwt.decode(refresh_token, options={"verify_signature": False})
                        
                        access_expiry = access_decoded.get("exp", time.time() + 300)  # 5 min default
                        refresh_expiry = refresh_decoded.get("exp", time.time() + 604800)  # 7 days default
                        
                        # Store tokens
                        user_key = username
                        self._access_tokens[user_key] = (access_token, access_expiry)
                        self._refresh_tokens[user_key] = (refresh_token, refresh_expiry)
                        
                        logger.info(f"Successfully obtained tokens for {username}")
                        return access_token
                    except Exception as e:
                        logger.warning(f"Could not decode token expiry: {e}")
                        # Store with default expiry
                        user_key = username
                        self._access_tokens[user_key] = (access_token, time.time() + 300)
                        self._refresh_tokens[user_key] = (refresh_token, time.time() + 604800)
                        return access_token
                else:
                    logger.error(f"Login response missing tokens: {token_data}")
                    return None
            elif response.status_code == 409:
                # User already logged in, force logout and retry
                logger.info(f"User {username} already logged in, forcing logout and retrying...")
                
                # Try logout multiple times with delay
                for attempt in range(3):
                    logout_success = self._logout_all_sessions(username, password)
                    if logout_success:
                        time.sleep(1)  # Wait 1 second for logout to take effect
                        break
                    time.sleep(0.5)
                
                # Retry login after logout
                retry_response = requests.post(login_url, json=login_data, timeout=10)
                logger.info(f"Retry login response status: {retry_response.status_code}")
                logger.info(f"Retry login response body: {retry_response.text[:200]}")
                
                if retry_response.status_code == 200:
                    token_data = retry_response.json()
                    data = token_data.get("data", {})
                    access_token = data.get("access_token")
                    refresh_token = data.get("refresh_token")
                    
                    if access_token and refresh_token:
                        user_key = username
                        self._access_tokens[user_key] = (access_token, time.time() + 300)
                        self._refresh_tokens[user_key] = (refresh_token, time.time() + 604800)
                        logger.info(f"Successfully obtained tokens for {username} after logout")
                        return access_token
                elif retry_response.status_code == 409:
                    # Still getting 409, skip authentication for now
                    logger.warning(f"Still getting 409 after logout for {username}, proceeding without auth")
                    return None
                
                logger.warning(f"Retry login failed for {username}: {retry_response.status_code}")
                return None
            else:
                logger.warning(f"JWT login failed for {username}: {response.status_code}, continuing without auth")
                return None
                
        except Exception as e:
            logger.warning(f"JWT authentication error for {username}: {e}, continuing without auth")
            return None
    
    def _logout_all_sessions(self, username: str, password: str) -> bool:
        """Logout all existing sessions for the user."""
        try:
            # Replace only the endpoint part, keep the domain
            logout_url = self.jwt_login_endpoint.replace('/login', '/logout')
            if 'logout.codegnan.ai' in logout_url:
                logout_url = logout_url.replace('logout.codegnan.ai', 'login.codegnan.ai')
            
            logout_data = {
                "email": username,
                "password": password
            }
            
            response = requests.post(logout_url, json=logout_data, timeout=5)
            logger.info(f"Logout response: {response.status_code}")
            return response.status_code in [200, 201, 204]
            
        except Exception as e:
            logger.warning(f"Logout failed for {username}: {e}")
            return False
        """Use refresh token to get new access token."""
        try:
            refresh_url = f"{self.base_url.rstrip('/api/v1')}/auth/refresh"
            headers = {
                'Authorization': f'Bearer {refresh_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(refresh_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                new_access_token = token_data.get("access_token")
                
                if new_access_token:
                    # Update access token cache
                    try:
                        decoded = jwt.decode(new_access_token, options={"verify_signature": False})
                        expiry = decoded.get("exp", time.time() + 300)
                        username = decoded.get("sub") or decoded.get("email")
                        
                        if username:
                            self._access_tokens[username] = (new_access_token, expiry)
                            logger.info(f"Successfully refreshed access token for {username}")
                            return new_access_token
                    except Exception as e:
                        logger.warning(f"Could not decode refreshed token: {e}")
                        return new_access_token
            else:
                logger.warning(f"Token refresh failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Token refresh error: {e}")
            return None
    
    def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Use refresh token to get new access token."""
        try:
            refresh_url = f"{self.base_url.rstrip('/api/v1')}/auth/refresh"
            headers = {
                'Authorization': f'Bearer {refresh_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(refresh_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                new_access_token = token_data.get("access_token")
                
                if new_access_token:
                    # Update access token cache
                    try:
                        decoded = jwt.decode(new_access_token, options={"verify_signature": False})
                        expiry = decoded.get("exp", time.time() + 300)
                        username = decoded.get("sub") or decoded.get("email")
                        
                        if username:
                            self._access_tokens[username] = (new_access_token, expiry)
                            logger.info(f"Successfully refreshed access token for {username}")
                            return new_access_token
                    except Exception as e:
                        logger.warning(f"Could not decode refreshed token: {e}")
                        return new_access_token
            else:
                logger.warning(f"Token refresh failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Token refresh error: {e}")
            return None
    
    def _get_headers(self, username: str = None, password: str = None) -> Dict[str, str]:
        """Get headers with access token."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        access_token = self._get_access_token(username, password)
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            logger.debug(f"Added Authorization header for user: {username or 'default'}")
        else:
            logger.warning(f"No access token available for user: {username or 'default'}")
        
        return headers
        """Get headers with access token."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        access_token = self._get_access_token(username, password)
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        return headers
    
    def get_teacher_attendance_data(self, mentor_id: str) -> Optional[Dict]:
        """Get attendance data for a mentor from external API with caching."""
        
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
            
            headers = self._get_headers()
            
            logger.info(f"Calling API: {url} with mentorId: {mentor_id}")
            
            response = requests.get(url, params=params, headers=headers, timeout=5)  # Reduced timeout
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
    
    def get_available_batches_and_subjects_with_auth(self, username: str, password: str) -> Dict[str, List[str]]:
        """Get available batches and their subjects using specific user credentials."""
        try:
            # Get teacher data using their credentials
            headers = self._get_headers(username, password)
            
            # Extract mentor_id from JWT token
            access_token = self._get_access_token(username, password)
            if not access_token:
                logger.error(f"Failed to get access token for {username}")
                return {}
            
            # Decode token to get mentor info
            try:
                decoded = jwt.decode(access_token, options={"verify_signature": False})
                mentor_id = decoded.get("id") or decoded.get("sub")
                if not mentor_id:
                    logger.error(f"No mentor ID found in token for {username}")
                    return {}
            except Exception as e:
                logger.error(f"Failed to decode token for {username}: {e}")
                return {}
            
            # Get attendance data using mentor_id
            url = f"{self.old_base_url}/attendance"
            params = {
                "mentorId": mentor_id,
                "role": "Mentor"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
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
                
                logger.info(f"Found {len(batch_subject_map)} batches for mentor {mentor_id} ({username})")
                return batch_subject_map
            else:
                logger.error(f"Authentication failed for {username}: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting batches for {username}: {e}")
            return {}
    
    def get_students_for_session_with_auth(self, batch: str, subject: str, username: str, password: str, location: str = "vijayawada") -> List[Dict]:
        """Get students for a specific batch/subject session using user credentials."""
        try:
            url = f"{self.base_url}/attend"
            payload = {
                "batches": batch,
                "subject": subject,
                "location": location
            }
            
            headers = self._get_headers(username, password)
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                students = data.get("students_data", [])
                
                logger.info(f"SUCCESS: Fetched {len(students)} students for {batch}/{subject} using {username}")
                return students
            else:
                logger.error(f"Failed: {response.status_code} - {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching students: {e}")
            return []
        """Get available batches and subjects for a specific mentor using service account."""
        try:
            # Use service account credentials
            headers = self._get_headers()
            
            # Get attendance data using mentor_id
            url = f"{self.old_base_url}/attendance"
            params = {
                "mentorId": mentor_id,
                "role": "Mentor"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
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
                
                logger.info(f"Found {len(batch_subject_map)} batches for mentor {mentor_id}")
                return batch_subject_map
            else:
                logger.error(f"Failed to get batches for mentor {mentor_id}: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting batches for mentor {mentor_id}: {e}")
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
            
            headers = self._get_headers()
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                students = data.get("students_data", [])
                
                logger.info(f"SUCCESS: Fetched {len(students)} students for {batch}/{subject}")
                return students
            else:
                logger.error(f"Failed: {response.status_code} - {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching students: {e}")
            return []
    
    async def authenticate_async(self, username: str, password: str) -> bool:
        """Authenticate user and store tokens asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            access_token = await loop.run_in_executor(
                self.executor,
                partial(self._get_access_token, username, password)
            )
            return access_token is not None
        except Exception as e:
            logger.error(f"Async authentication error for {username}: {e}")
            return False
    
    def send_attendance_to_api(self, attendance_data: Dict, method: str = "POST") -> bool:
        try:
            url = f"{self.base_url}/attendance"
            headers = self._get_headers()
            
            if method.upper() == "POST":
                response = requests.post(url, json=attendance_data, headers=headers, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, json=attendance_data, headers=headers, timeout=10)
            else:
                logger.error(f"Unsupported method: {method}")
                return False
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully sent attendance data to API using {method}")
                return True
            elif response.status_code == 403:
                # Handle duplicate attendance - this is actually success for our use case
                response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                if response_data.get('status') == 'duplicate':
                    logger.info(f"Attendance already exists (duplicate) - treating as success")
                    return True
                else:
                    logger.error(f"Failed to send attendance data. Method: {method}, Status: {response.status_code}, Response: {response.text}")
                    return False
            else:
                logger.error(f"Failed to send attendance data. Method: {method}, Status: {response.status_code}, Response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending attendance to API: {e}")
            return False
    
    def send_attendance_to_api_with_auth(self, attendance_data: Dict, method: str = "POST", username: str = None, password: str = None) -> bool:
        try:
            url = f"{self.base_url}/attendance"
            headers = self._get_headers(username, password)
            
            if method.upper() == "POST":
                response = requests.post(url, json=attendance_data, headers=headers, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, json=attendance_data, headers=headers, timeout=10)
            else:
                logger.error(f"Unsupported method: {method}")
                return False
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully sent attendance data to API using {method} with auth")
                return True
            elif response.status_code == 403:
                # Handle duplicate attendance - this is actually success for our use case
                response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                if response_data.get('status') == 'duplicate':
                    logger.info(f"Attendance already exists (duplicate) - treating as success")
                    return True
                else:
                    logger.error(f"Failed to send attendance data. Method: {method}, Status: {response.status_code}, Response: {response.text}")
                    return False
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
    
    async def send_attendance_to_api_with_auth_async(self, attendance_data: Dict, method: str = "POST", username: str = None, password: str = None) -> bool:
        """Send attendance data to API asynchronously with authentication."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                partial(self.send_attendance_to_api_with_auth, attendance_data, method, username, password)
            )
            return result
        except Exception as e:
            logger.error(f"Async authenticated API call error: {e}")
            return False
    
    def send_attendance_update_to_api(self, update_data: Dict) -> bool:
        """Send attendance update to API (for individual student updates)."""
        try:
            # Try update endpoint first
            update_url = f"{self.base_url}/attendance/update"
            headers = self._get_headers()
            
            response = requests.put(update_url, json=update_data, headers=headers, timeout=10)
            
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