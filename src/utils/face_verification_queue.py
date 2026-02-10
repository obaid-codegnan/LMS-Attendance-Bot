"""
Face Verification Queue System
Handles high-scale concurrent face verification with dynamic thread allocation
"""
import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Dict, Optional
from src.config.settings import Config
from src.utils.bot_messages import messages

logger = logging.getLogger(__name__)

@dataclass
class VerificationTask:
    request_id: str
    student_id: str
    video_bytes: bytes
    batch_name: str
    session_info: dict
    user_id: int
    timestamp: float
    teacher_credentials: dict = None
    retry_count: int = 0

class DynamicFaceVerificationQueue:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.task_queue = Queue()
            self.active_tasks = 0
            self.total_processed = 0
            self.executor = None
            self.current_workers = 0
            self.max_workers = Config.MAX_CONCURRENT_FACE_VERIFICATIONS
            self.min_workers = 2
            self.last_scale_time = time.time()
            self.scale_cooldown = 5
            self.worker_lock = threading.Lock()
            self.running = True
            self.accepting_tasks = True
            self.retry_attempts = {}
            self.completed_students = {}
            self.cleanup_thread = None
            
            self._scale_workers(self.min_workers)
            self.processor_thread = threading.Thread(target=self._process_queue, daemon=True)
            self.processor_thread.start()
            
            self._start_cleanup_task()
            self.initialized = True
            logger.info(f"Dynamic face verification queue initialized with {self.current_workers} workers")
    
    def _start_cleanup_task(self):
        """Start background cleanup task."""
        def cleanup_loop():
            while self.running:
                time.sleep(300)  # Run every 5 minutes
                self._cleanup_old_data()
        
        self.cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        logger.info("Session cleanup task started")
    
    def _cleanup_old_data(self):
        """Clean up expired sessions and old retry data."""
        try:
            current_time = time.time()
            
            # Clean retry attempts older than 1 hour
            expired_retries = [k for k, v in self.retry_attempts.items() if current_time - v > 3600]
            for key in expired_retries:
                del self.retry_attempts[key]
            
            # Trim completed students to last 1000 entries
            expired_completed = [k for k in list(self.completed_students.keys())]
            if len(expired_completed) > 1000:
                for key in expired_completed[:-1000]:
                    del self.completed_students[key]
            
            # Clean up expired MongoDB sessions
            try:
                from src.repositories.mongo_repository import MongoRepository
                mongo_repo = MongoRepository()
                deleted_count = mongo_repo.cleanup_expired_sessions()
                if deleted_count > 0:
                    logger.info(f"Cleanup: Removed {deleted_count} expired sessions from MongoDB")
            except Exception as mongo_error:
                logger.error(f"MongoDB session cleanup error: {mongo_error}")
            
            if expired_retries or len(expired_completed) > 1000:
                logger.info(f"Cleanup: Removed {len(expired_retries)} retry entries, trimmed completed to 1000")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    def add_task(self, task: VerificationTask) -> bool:
        """Add verification task to queue."""
        if not self.accepting_tasks:
            logger.warning(f"[{task.request_id}] Queue not accepting new tasks (shutting down)")
            return False
        
        try:
            self.task_queue.put(task, timeout=1)
            queue_size = self.task_queue.qsize()
            
            # Dynamic scaling based on queue size
            self._auto_scale_workers(queue_size)
            
            logger.info(f"[{task.request_id}] Task queued for {task.student_id}. Queue size: {queue_size}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue task {task.request_id}: {e}")
            return False
    
    def stop_accepting(self):
        """Stop accepting new tasks (for graceful shutdown)."""
        self.accepting_tasks = False
        logger.info("Queue stopped accepting new tasks")
    
    def _auto_scale_workers(self, queue_size: int):
        """Automatically scale workers based on queue size and load."""
        current_time = time.time()
        
        # Cooldown check
        if current_time - self.last_scale_time < self.scale_cooldown:
            return
        
        with self.worker_lock:
            target_workers = self.current_workers
            
            # Scale up conditions
            if queue_size > self.current_workers * 2 and self.current_workers < self.max_workers:
                target_workers = min(self.max_workers, self.current_workers + max(2, queue_size // 4))
            
            # Scale down conditions  
            elif queue_size < self.current_workers // 3 and self.current_workers > self.min_workers:
                target_workers = max(self.min_workers, self.current_workers - 1)
            
            if target_workers != self.current_workers:
                self._scale_workers(target_workers)
                self.last_scale_time = current_time
    
    def _scale_workers(self, target_workers: int):
        """Scale thread pool to target worker count."""
        if self.executor:
            self.executor.shutdown(wait=False)
        
        self.executor = ThreadPoolExecutor(
            max_workers=target_workers,
            thread_name_prefix="FaceVerification"
        )
        self.current_workers = target_workers
        
        logger.info(f"Scaled workers to {target_workers} (queue: {self.task_queue.qsize()}, active: {self.active_tasks})")
    
    def _process_queue(self):
        """Main queue processor loop."""
        while self.running:
            try:
                task = self.task_queue.get(timeout=1)
                
                # Submit to thread pool
                future = self.executor.submit(self._process_verification_task, task)
                
                # Don't wait for completion - fire and forget
                self.task_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Queue processor error: {e}")
    
    def _process_verification_task(self, task: VerificationTask):
        """Process individual verification task."""
        self.active_tasks += 1
        start_time = time.time()
        
        try:
            # Check if student already completed
            completion_key = f"{task.student_id}_{task.session_info['otp']}"
            if completion_key in self.completed_students:
                logger.info(f"[{task.request_id}] Student {task.student_id} already completed attendance")
                from telegram import Bot
                bot = Bot(token=Config.STUDENT_BOT_TOKEN)
                asyncio.run(bot.send_message(
                    chat_id=task.user_id,
                    text=messages.verification('already_marked', student_id=task.student_id)
                ))
                return
            
            # Import here to avoid circular imports
            from src.services.face_recognition_service import FaceRecognitionService
            from src.services.api_attendance_service import APIAttendanceService
            from telegram import Bot
            
            face_service = FaceRecognitionService()
            attendance_service = APIAttendanceService()
            bot = Bot(token=Config.STUDENT_BOT_TOKEN)
            
            logger.info(f"[{task.request_id}] Processing verification for {task.student_id}")
            logger.debug(f"[{task.request_id}] Teacher credentials available: {task.teacher_credentials is not None}")
            if task.teacher_credentials:
                logger.debug(f"[{task.request_id}] Using credentials for: {task.teacher_credentials.get('username', 'N/A')}")
            
            # Step 1: Face verification with timing
            face_start = time.time()
            verification_result = asyncio.run(face_service.verify_face_from_video_bytes(
                task.video_bytes, task.student_id, task.batch_name, task.request_id
            ))
            face_time = time.time() - face_start
            
            if verification_result['success']:
                confidence = verification_result.get('confidence', 0)
                
                # Step 2: Mark attendance with timing
                api_start = time.time()
                
                # Determine student's actual batch from session data
                student_data = task.session_info.get('students', {}).get(task.student_id, {})
                student_batch = student_data.get('BatchNo', '')
                
                logger.info(f"[{task.request_id}] Student data from session: {student_data}")
                logger.info(f"[{task.request_id}] Student batch from session: {student_batch}")
                
                if not student_batch or ',' in student_batch:
                    # Batch is combined or missing, use the batch where image was found
                    found_batch = verification_result.get('found_in_batch', '')
                    if found_batch:
                        student_batch = found_batch
                        logger.info(f"[{task.request_id}] Using batch from face recognition: {student_batch}")
                    else:
                        # Fallback: use first batch from session
                        student_batch = task.session_info['batch_name'].split(',')[0].strip()
                        logger.info(f"[{task.request_id}] Using first batch as fallback: {student_batch}")
                
                logger.info(f"[{task.request_id}] Marking attendance for {task.student_id} in batch {student_batch}/{task.session_info['subject']}")
                
                try:
                    success = asyncio.run(attendance_service.mark_student_present_async(
                        student_id=task.student_id,
                        batch=student_batch,
                        subject=task.session_info['subject'],
                        teacher_credentials=task.teacher_credentials
                    ))
                except Exception as attendance_error:
                    logger.error(f"[{task.request_id}] Attendance marking exception: {attendance_error}")
                    import traceback
                    logger.error(f"[{task.request_id}] Traceback: {traceback.format_exc()}")
                    success = False
                    
                api_time = time.time() - api_start
                logger.info(f"[{task.request_id}] Attendance marking result: {success} (took {api_time:.2f}s)")
                
                # Step 3: Send response with timing
                response_start = time.time()
                if success:
                    total_time = time.time() - start_time
                    self.total_processed += 1
                    
                    # Mark student as completed
                    completion_key = f"{task.student_id}_{task.session_info['otp']}"
                    self.completed_students[completion_key] = True
                    
                    # Send success message
                    asyncio.run(bot.send_message(
                        chat_id=task.user_id,
                        text=messages.verification('success',
                            student_id=task.student_id,
                            batch=student_batch,
                            subject=task.session_info['subject'],
                            confidence=int(confidence),
                            time=f"{total_time:.2f}",
                            request_id=task.request_id
                        ) + "\n✅ **Attendance process completed. You may close this chat.**"
                    ))
                    response_time = time.time() - response_start
                    
                    logger.info(f"[{task.request_id}] SUCCESS: {task.student_id} - Face: {face_time:.2f}s, API: {api_time:.2f}s, Response: {response_time:.2f}s, Total: {total_time:.2f}s")
                else:
                    asyncio.run(bot.send_message(
                        chat_id=task.user_id,
                        text=messages.verification('api_error',
                            student_id=task.student_id,
                            error="Failed to record attendance",
                            request_id=task.request_id
                        )
                    ))
            else:
                error_msg = verification_result.get('error', 'Face verification failed')
                retry_key = f"{task.student_id}_{task.session_info['otp']}"
                current_retries = self.retry_attempts.get(retry_key, 0)
                max_retries = Config.FACE_VERIFICATION_MAX_RETRIES
                
                logger.info(f"[{task.request_id}] Verification failed. Current retries: {current_retries}, Max: {max_retries}")
                
                # Check if it's a no face detected error
                if verification_result.get('no_face'):
                    if current_retries < max_retries:
                        self.retry_attempts[retry_key] = current_retries + 1
                        logger.info(f"[{task.request_id}] Sending retry message to user {task.user_id}")
                        try:
                            asyncio.run(bot.send_message(
                                chat_id=task.user_id,
                                text=messages.verification('no_face_retry',
                                    student_id=task.student_id,
                                    request_id=task.request_id,
                                    attempts_left=max_retries - current_retries
                                )
                            ))
                            logger.info(f"[{task.request_id}] Retry message sent successfully")
                        except Exception as msg_error:
                            logger.error(f"[{task.request_id}] Failed to send retry message: {msg_error}")
                        logger.info(f"[{task.request_id}] Allowing retry for {task.student_id} (attempt {current_retries + 1}/{max_retries + 1})")
                    else:
                        logger.info(f"[{task.request_id}] Sending final failure message to user {task.user_id}")
                        try:
                            asyncio.run(bot.send_message(
                                chat_id=task.user_id,
                                text=messages.verification('no_face_detected',
                                    student_id=task.student_id,
                                    request_id=task.request_id
                                ) + "\n\n⚠️ **Maximum attempts reached. Please contact your teacher.**"
                            ))
                            logger.info(f"[{task.request_id}] Final failure message sent successfully")
                        except Exception as msg_error:
                            logger.error(f"[{task.request_id}] Failed to send final message: {msg_error}")
                        logger.warning(f"[{task.request_id}] Max retries reached for {task.student_id}")
                # Check if it's a missing image error
                elif 'not found' in error_msg.lower() or 'no stored image' in error_msg.lower():
                    # Get student's actual batch
                    student_data = task.session_info.get('students', {}).get(task.student_id, {})
                    student_batch = student_data.get('BatchNo', task.session_info['batch_name'])
                    if ',' in student_batch:
                        student_batch = student_batch.split(',')[0].strip()
                    try:
                        asyncio.run(bot.send_message(
                            chat_id=task.user_id,
                            text=messages.verification('image_not_found',
                                student_id=task.student_id,
                                batch=student_batch,
                                request_id=task.request_id
                            )
                        ))
                    except Exception as msg_error:
                        logger.error(f"[{task.request_id}] Failed to send image not found message: {msg_error}")
                else:
                    # Face mismatch - check retry
                    if current_retries < max_retries:
                        self.retry_attempts[retry_key] = current_retries + 1
                        logger.info(f"[{task.request_id}] Sending face mismatch retry message to user {task.user_id}")
                        try:
                            asyncio.run(bot.send_message(
                                chat_id=task.user_id,
                                text=messages.verification('face_not_match_retry',
                                    student_id=task.student_id,
                                    confidence=int(verification_result.get('confidence', 0)),
                                    threshold=Config.FACE_MATCH_THRESHOLD,
                                    request_id=task.request_id,
                                    attempts_left=max_retries - current_retries
                                )
                            ))
                            logger.info(f"[{task.request_id}] Retry message sent successfully")
                        except Exception as msg_error:
                            logger.error(f"[{task.request_id}] Failed to send retry message: {msg_error}")
                        logger.info(f"[{task.request_id}] Allowing retry for {task.student_id} (attempt {current_retries + 1}/{max_retries + 1})")
                    else:
                        logger.info(f"[{task.request_id}] Sending final face mismatch message to user {task.user_id}")
                        try:
                            asyncio.run(bot.send_message(
                                chat_id=task.user_id,
                                text=messages.verification('face_not_match',
                                    student_id=task.student_id,
                                    confidence=int(verification_result.get('confidence', 0)),
                                    threshold=Config.FACE_MATCH_THRESHOLD,
                                    request_id=task.request_id
                                ) + "\n\n⚠️ **Maximum attempts reached. Please contact your teacher.**"
                            ))
                            logger.info(f"[{task.request_id}] Final failure message sent successfully")
                        except Exception as msg_error:
                            logger.error(f"[{task.request_id}] Failed to send final message: {msg_error}")
                        logger.warning(f"[{task.request_id}] Max retries reached for {task.student_id}")
                
                logger.warning(f"[{task.request_id}] FAILED: {task.student_id} - {error_msg} (Face: {face_time:.2f}s)")
                
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"[{task.request_id}] ERROR processing {task.student_id}: {e} (Total: {total_time:.2f}s)")
            try:
                from telegram import Bot
                bot = Bot(token=Config.STUDENT_BOT_TOKEN)
                asyncio.run(bot.send_message(
                    chat_id=task.user_id,
                    text=messages.verification('processing_error',
                        student_id=task.student_id,
                        error=str(e),
                        request_id=task.request_id
                    )
                ))
            except:
                pass
        finally:
            self.active_tasks -= 1
    
    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "queue_size": self.task_queue.qsize(),
            "active_tasks": self.active_tasks,
            "current_workers": self.current_workers,
            "total_processed": self.total_processed,
            "max_workers": self.max_workers,
            "retry_tracking": len(self.retry_attempts),
            "completed_tracking": len(self.completed_students)
        }
    
    def shutdown(self):
        """Shutdown queue processor gracefully."""
        logger.info("Starting graceful shutdown...")
        self.accepting_tasks = False
        
        # Wait for queue to drain (max 5 seconds)
        timeout = 5
        start = time.time()
        while self.task_queue.qsize() > 0:
            if time.time() - start > timeout:
                logger.warning(f"Shutdown timeout reached. {self.task_queue.qsize()} tasks remaining.")
                break
            time.sleep(0.2)
        
        self.running = False
        if self.executor:
            self.executor.shutdown(wait=False)  # Don't wait for threads
        logger.info("Face verification queue shut down")

# Global instance
face_queue = DynamicFaceVerificationQueue()