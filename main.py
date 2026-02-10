"""
Main Application Runner
Starts Teacher Bot and Student Bot
"""
import logging
import threading
import asyncio
import signal
import sys
import os
import time
from src.services.teacher_bot_service import TeacherBotService
from src.services.student_bot_service import StudentBotService
from src.config.settings import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Reduce httpx logging verbosity
logging.getLogger('httpx').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global shutdown flag
shutdown_event = threading.Event()

# Global service instances for cleanup
teacher_service_instance = None
student_service_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info("Received shutdown signal. Stopping all services...")
    shutdown_event.set()

def run_teacher_bot():
    """Run teacher bot in separate thread."""
    global teacher_service_instance
    try:
        logger.info("Initializing Teacher Bot...")
        
        # Create new event loop for this thread
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        teacher_service_instance = TeacherBotService()
        if teacher_service_instance.app:
            logger.info("Starting Teacher Bot polling...")
            teacher_service_instance.app.run_polling()
        else:
            logger.error("Teacher Bot app is None - check token and configuration")
    except Exception as e:
        logger.error(f"Teacher Bot error: {e}")
        import traceback
        traceback.print_exc()

def run_student_bot():
    """Run student bot in separate thread."""
    global student_service_instance
    try:
        logger.info("Initializing Student Bot...")
        
        # Create new event loop for this thread
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        student_service_instance = StudentBotService()
        if student_service_instance.app:
            logger.info("Starting Student Bot polling...")
            student_service_instance.app.run_polling()
        else:
            logger.error("Student Bot app is None - check token and configuration")
    except Exception as e:
        logger.error(f"Student Bot error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main application entry point."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=== Face Recognition Attendance System ===")
    logger.info("Starting Telegram Bot services...")
    
    # Initialize face verification queue
    from src.utils.face_verification_queue import face_queue
    logger.info("Face verification queue initialized")
    
    # Start services in separate threads
    threads = []
    
    # Teacher Bot Thread
    if Config.TEACHER_BOT_TOKEN:
        teacher_thread = threading.Thread(target=run_teacher_bot, daemon=True)
        teacher_thread.start()
        threads.append(teacher_thread)
        logger.info("Teacher Bot thread started")
    else:
        logger.warning("TEACHER_BOT_TOKEN not set - Teacher Bot disabled")
    
    # Student Bot Thread  
    if Config.STUDENT_BOT_TOKEN:
        student_thread = threading.Thread(target=run_student_bot, daemon=True)
        student_thread.start()
        threads.append(student_thread)
        logger.info("Student Bot thread started")
    else:
        logger.warning("STUDENT_BOT_TOKEN not set - Student Bot disabled")
    
    logger.info("All services started successfully!")
    logger.info("Press Ctrl+C to stop all services")
    
    try:
        # Wait for shutdown signal with timeout to allow Ctrl+C handling
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
        shutdown_event.set()
    finally:
        # Cleanup thread pools and queue
        logger.info("Cleaning up thread pools...")
        try:
            # Fast shutdown: stop accepting and force exit
            from src.utils.face_verification_queue import face_queue
            logger.info("Stopping queue and draining tasks...")
            face_queue.stop_accepting()
            
            # Wait for queue to drain (max 5 seconds only)
            timeout = 5
            start_time = time.time()
            while face_queue.get_stats()['queue_size'] > 0:
                if time.time() - start_time > timeout:
                    logger.warning(f"Shutdown timeout after {timeout}s, forcing exit")
                    break
                time.sleep(0.5)
            
            face_queue.shutdown()
            
            if teacher_service_instance and hasattr(teacher_service_instance, 'attendance_service'):
                if hasattr(teacher_service_instance.attendance_service, 'api_service'):
                    teacher_service_instance.attendance_service.api_service.cleanup()
            
            if student_service_instance and hasattr(student_service_instance, 'attendance_service'):
                if hasattr(student_service_instance.attendance_service, 'api_service'):
                    student_service_instance.attendance_service.api_service.cleanup()
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")
        
        logger.info("All services stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()
