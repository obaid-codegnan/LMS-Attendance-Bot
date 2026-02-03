"""
Main Application Factory with Database Connection Pooling.
"""
from flask import Flask
from flask_restful import Api
from src.config.settings import Config
from src.api.resources.attendance_resource import AttendanceResource
from src.api.resources.student_upload_resource import StudentUploadResource
from src.api.resources.batch_resource import BatchResource

from src.api.ui_routes import ui_bp
from src.middleware.error_handler import handle_errors, log_requests
import logging
import os
import threading
import atexit



# Configure centralized logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Silence verbose libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def cleanup_resources():
    """Cleanup resources on application shutdown."""
    try:
        from src.utils.connection_pool import close_connection_pool
        close_connection_pool()
        logging.info("Database connection pool closed")
    except Exception as e:
        logging.error(f"Error closing connection pool: {e}")

# Register cleanup function
atexit.register(cleanup_resources)

def create_app():
    """
    Create and configure Flask application.
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Validate configuration
    try:
        Config.validate()
    except Exception as e:
        logging.error(f"Configuration validation failed: {e}")
        raise
    
    # Set up error handling and logging middleware
    handle_errors(app)
    log_requests(app)
    
    # Set security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    api = Api(app)
    
    # Register Resources
    api.add_resource(AttendanceResource, '/api/attendance')
    api.add_resource(StudentUploadResource, '/api/upload-students/<string:action>')

    api.add_resource(BatchResource, '/api/batches')
    
    from src.api.resources.batch_resource import BatchFilesResource
    api.add_resource(BatchFilesResource, '/api/batches/<string:batch_id>/files')
    

    
    from src.api.resources.telegram_status_resource import TelegramStatusResource
    api.add_resource(TelegramStatusResource, '/api/telegram/status')
    


    from src.api.resources.teacher_resource import TeacherResource
    api.add_resource(TeacherResource, '/api/teachers')
    

    

    

    
    # Register monitoring dashboard
    from src.api.monitor import monitor_bp
    app.register_blueprint(monitor_bp)
    
    # Register UI
    app.register_blueprint(ui_bp)
    
    # Start background services (prevent double execution with Flask reloader)
    if not Config.RELOAD or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_background_services()

    return app

def _start_background_services():
    """Start background services in separate threads."""
    
    # Teacher Bot
    if Config.TEACHER_BOT_TOKEN:
        try:
            from src.services.teacher_bot_service import TeacherBotService
            def start_teacher_bot():
                try:
                    import asyncio
                    asyncio.set_event_loop(asyncio.new_event_loop())
                    bot = TeacherBotService()
                    bot.run_polling()
                except Exception as e:
                    logging.error(f"Teacher Bot error: {e}")
                    
            t_thread = threading.Thread(target=start_teacher_bot, daemon=True)
            t_thread.start()
            logging.info("Teacher Bot started.")
        except Exception as e:
            logging.error(f"Failed to start Teacher Bot: {e}")
    else:
        logging.warning("TEACHER_BOT_TOKEN not set.")

    # Student Bot
    if Config.STUDENT_BOT_TOKEN:
        try:
            from src.services.student_bot_service import StudentBotService
            def start_student_bot():
                try:
                    import asyncio
                    asyncio.set_event_loop(asyncio.new_event_loop())
                    bot = StudentBotService()
                    bot.run_polling()
                except Exception as e:
                    logging.error(f"Student Bot error: {e}")
                    
            s_thread = threading.Thread(target=start_student_bot, daemon=True)
            s_thread.start()
            logging.info("Student Bot started.")
        except Exception as e:
            logging.error(f"Failed to start Student Bot: {e}")
    else:
        logging.warning("STUDENT_BOT_TOKEN not set.")

