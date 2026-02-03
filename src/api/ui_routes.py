"""
UI Routes Blueprint.
Serves HTML pages.
"""
from flask import Blueprint, render_template

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def index():
    """Serve the main capture interface."""
    return render_template('index.html')

@ui_bp.route('/upload-students')
def upload_students_page():
    """Serve student S3 upload page."""
    return render_template('upload_students.html')

@ui_bp.route('/mark')
def mark_attendance_page():
    """Serve attendance marking dashboard."""
    return render_template('mark_attendance.html')

@ui_bp.route('/teacher')
def teacher_dashboard():
    """Serve teacher dashboard."""
    return render_template('teacher_dashboard.html')

@ui_bp.route('/add-teacher')
def add_teacher_page():
    """Serve add teacher page."""
    return render_template('add_teacher.html')

@ui_bp.route('/cost-monitoring')
def cost_monitoring_page():
    """Serve AWS cost monitoring dashboard."""
    return render_template('cost_monitoring.html')

@ui_bp.route('/realtime')
def realtime_dashboard():
    """Serve real-time attendance dashboard."""
    # Get active session if any
    try:
        from src.repositories.telegram_repository import TelegramRepository
        repo = TelegramRepository()
        # Get most recent active session
        session = repo.get_active_session()
        return render_template('realtime_dashboard.html', session=session)
    except:
        return render_template('realtime_dashboard.html', session=None)
