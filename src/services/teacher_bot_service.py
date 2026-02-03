"""
Teacher Bot Service.
Handles the conversation flow for Teachers: Login, Select Batch (Multi), Start Session, Receive Report.
"""
import logging
import asyncio
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ConversationHandler
)
from src.repositories.mongo_repository import MongoRepository
from src.services.api_attendance_service import APIAttendanceService
from src.utils.string_utils import sanitize_batch_name
from src.config.settings import Config

logger = logging.getLogger(__name__)

# STATES
BATCH, SUBJECT, LOCATION = range(3)

class TeacherBotService:
    """Service for handling teacher bot operations."""
    
    def __init__(self):
        self.mongo_repo = MongoRepository()
        self.attendance_service = APIAttendanceService()
        self.app = None
        self.token = Config.TEACHER_BOT_TOKEN
        
        if not self.token:
            logger.warning("TEACHER_BOT_TOKEN not set. Teacher Bot will not start.")
            return

        self.app = ApplicationBuilder().token(self.token).build()
        self.setup_handlers()

    def setup_handlers(self) -> None:
        """Set up conversation handlers for the bot."""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                BATCH: [CallbackQueryHandler(self.handle_batch_selection)],
                SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_subject)],
                LOCATION: [MessageHandler(filters.LOCATION, self.receive_location)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel), CommandHandler("start", self.start)],
            per_message=False
        )
        
        self.app.add_handler(conv_handler)
        logger.info("Teacher Bot Handlers Configured.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import time
        start_time = time.time()
        
        context.user_data.clear()
        user = update.effective_user
        telegram_id = user.id
        
        logger.info(f"Teacher Bot: /start from {telegram_id}")
        
        # Send immediate response
        await update.message.reply_text(f"👋 Welcome, **{user.first_name or 'Teacher'}**!\n🔄 Loading your batches...", parse_mode='Markdown')
        
        # Check MongoDB for existing teacher with telegram_id
        mongo_start = time.time()
        teacher = self.mongo_repo.get_teacher_by_telegram_id(telegram_id)
        mongo_time = time.time() - mongo_start
        logger.info(f"MongoDB lookup: {mongo_time:.2f}s")
        
        if teacher and teacher.get('mentor_id'):
            context.user_data['teacher'] = teacher
            return await self._show_batch_options_from_api(update, context, teacher)
        
        # Try to fetch data directly from API using hardcoded mentor_id for testing
        from src.services.api_service import APIService
        api_service = APIService()
        
        # Use hardcoded mentor_id for testing
        test_mentor_id = "bafceeb1-8638-4854-8210-7be787420dec"
        
        # Make API call in thread pool to avoid blocking
        api_start = time.time()
        loop = asyncio.get_event_loop()
        batch_subject_map = await loop.run_in_executor(
            None, 
            api_service.get_available_batches_and_subjects, 
            test_mentor_id
        )
        api_time = time.time() - api_start
        total_time = time.time() - start_time
        
        logger.info(f"TEACHER BOT TIMING - API: {api_time:.2f}s, Total: {total_time:.2f}s")
        
        if batch_subject_map:
            # Create temporary teacher record
            teacher = {
                '_id': str(telegram_id),
                'name': user.first_name or 'Teacher',
                'telegram_id': telegram_id,
                'mentor_id': test_mentor_id
            }
            context.user_data['teacher'] = teacher
            
            return await self._show_batch_options_from_api(update, context, teacher)
        else:
            await update.message.reply_text(
                f"❌ Access Denied. Your Telegram ID ({telegram_id}) is not registered or has no pending attendance.\n"
                f"Please contact admin to register your account.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    async def verify_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        phone = update.message.contact.phone_number
        return await self._verify_identity(update, context, phone)

    async def verify_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        phone = update.message.text.strip()
        return await self._verify_identity(update, context, phone)

    async def _verify_identity(self, update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str) -> int:
        """Verify teacher identity using MongoDB or API fallback."""
        if not phone.startswith('+'):
            phone = '+' + phone if len(phone) < 13 else phone 
        
        logger.info(f"Verifying Teacher Identity: {phone}")

        # Try MongoDB first
        teacher = self.mongo_repo.get_teacher_by_phone(phone)
        
        if teacher:
            # Link telegram ID
            self.mongo_repo.update_teacher_telegram_id(teacher['_id'], update.effective_user.id)
            
            context.user_data['teacher'] = teacher
            await update.message.reply_text(f"✅ Verified as Teacher: **{teacher.get('name', 'Teacher')}**!", parse_mode='Markdown')
            return await self._show_batch_options_from_mongodb(update, context, teacher)
        
        # Fallback to temporary mapping if MongoDB fails
        logger.warning("MongoDB not available, using temporary mapping")
        teacher_mapping = Config.TEMP_TEACHER_MAPPING
        teacher = teacher_mapping.get(phone)
        
        if teacher:
            context.user_data['teacher'] = teacher
            await update.message.reply_text(f"✅ Verified as Teacher: **{teacher['name']}**!", parse_mode='Markdown')
            return await self._show_batch_options_from_mongodb(update, context, teacher)
        else:
            # Show available phone numbers for debugging
            available_phones = list(teacher_mapping.keys())
            await update.message.reply_text(
                f"❌ Access Denied. Your number ({phone}) is not registered.\n"
                f"Available numbers: {', '.join(available_phones)}", 
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    async def _show_batch_options_from_api(self, update: Update, context: ContextTypes.DEFAULT_TYPE, teacher):
        """Get batches from external API based on hardcoded mentor_id."""
        # Use hardcoded mentor_id for testing
        mentor_id = teacher.get('mentor_id', "bafceeb1-8638-4854-8210-7be787420dec")
        
        # Fetch from external API asynchronously
        from src.services.api_service import APIService
        api_service = APIService()
        
        loop = asyncio.get_event_loop()
        batch_subject_map = await loop.run_in_executor(
            None, 
            api_service.get_available_batches_and_subjects, 
            mentor_id
        )
        
        if not batch_subject_map:
            await update.message.reply_text(
                "❌ No pending attendance found for today. Please contact admin.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        available_batches = list(batch_subject_map.keys())
        context.user_data['available_batches'] = available_batches
        context.user_data['batch_subject_map'] = batch_subject_map
        context.user_data['mentor_id'] = mentor_id
        context.user_data['selected_batches'] = []
        
        markup = self._get_batch_markup(available_batches, [])
        await update.message.reply_text("📚 **Select Batches**:", parse_mode='Markdown', reply_markup=markup)
        return BATCH

    def _get_batch_markup(self, available: List[str], selected: List[str]) -> InlineKeyboardMarkup:
        """Generate inline keyboard markup for batch selection."""
        keyboard = []
        for batch in available:
            is_selected = batch in selected
            icon = "✅" if is_selected else "⬜"
            keyboard.append([InlineKeyboardButton(f"{icon} {batch}", callback_data=f"TOGGLE_{batch}")])
            
        keyboard.append([InlineKeyboardButton("Done ➡️", callback_data="DONE")])
        return InlineKeyboardMarkup(keyboard)

    async def handle_batch_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        selected = context.user_data.get('selected_batches', [])
        available = context.user_data.get('available_batches', [])
        
        if data == "DONE":
            if not selected:
                await query.edit_message_reply_markup(reply_markup=self._get_batch_markup(available, selected))
                return BATCH
                
            # Done, proceed to Subject
            batch_str = ", ".join(selected)
            context.user_data['sess_batch'] = batch_str
            
            # Get subjects from API data
            batch_subject_map = context.user_data.get('batch_subject_map', {})
            
            # Get subjects for selected batches from API
            available_subjects = set()
            for batch in selected:
                if batch in batch_subject_map:
                    available_subjects.update(batch_subject_map[batch])
            assigned_subjects = list(available_subjects)
            
            if not assigned_subjects:
                await query.message.reply_text(
                    "❌ No subjects available for selected batches. Please contact admin.",
                    reply_markup=ReplyKeyboardRemove()
                )
                return ConversationHandler.END
             
            keyboard = [[KeyboardButton(s)] for s in assigned_subjects]
            markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            
            # Send new message because we are moving from inline to reply keyboard
            await query.message.reply_text(f"Selected: *{batch_str}*\n📖 **Select Subject**:", parse_mode='Markdown', reply_markup=markup)
            return SUBJECT
        
        elif data.startswith("TOGGLE_"):
            batch = data[7:]  # Remove "TOGGLE_" prefix
            if batch in selected:
                selected.remove(batch)
            else:
                selected.append(batch)
            
            context.user_data['selected_batches'] = selected
            # Update keyboard
            markup = self._get_batch_markup(available, selected)
            await query.edit_message_reply_markup(reply_markup=markup)
            return BATCH
    
    async def select_subject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle subject selection."""
        subject = update.message.text.strip()
        
        # Get available subjects from API data
        batch_subject_map = context.user_data.get('batch_subject_map', {})
        selected_batches = context.user_data.get('sess_batch', '').split(', ')
        
        # Validate against API subjects for selected batches
        available_subjects = set()
        for batch in selected_batches:
            if batch.strip() in batch_subject_map:
                available_subjects.update(batch_subject_map[batch.strip()])
        assigned_subjects = list(available_subjects)
        
        if subject not in assigned_subjects:
            await update.message.reply_text("❌ Invalid subject. Please select from the keyboard.")
            return SUBJECT
        
        # Check if session already exists for this teacher, batch, and subject today
        teacher = context.user_data.get('teacher', {})
        batch_str = context.user_data.get('sess_batch', '')
        today = datetime.now().strftime("%Y-%m-%d")
        existing_session = self._check_existing_session(teacher.get('_id'), batch_str, subject, today)
        
        if existing_session:
            await update.message.reply_text(
                f"❌ Session already exists for {subject} in {batch_str} today.\n"
                f"Please wait for the current session to complete or contact admin.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        context.user_data['sess_subject'] = subject
        
        location_btn = KeyboardButton(text="📍 Share Live Location", request_location=True)
        markup = ReplyKeyboardMarkup([[location_btn]], one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Subject: *{subject}*\n📍 **Share your Live Location** to start the session:",
            parse_mode='Markdown',
            reply_markup=markup
        )
        return LOCATION
    
    async def receive_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle location and create session."""
        location = update.message.location
        teacher = context.user_data.get('teacher', {})
        batch_str = context.user_data.get('sess_batch', '')
        subject = context.user_data.get('sess_subject', '')
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Generate OTP
        otp = str(random.randint(100000, 999999))
        
        # Fetch students from API for this session (async)
        from src.services.api_service import APIService
        api_service = APIService()
        
        # Get students for each selected batch asynchronously
        all_students = {}
        selected_batches = batch_str.split(', ')
        
        # Send loading message
        loading_msg = await update.message.reply_text("🔄 Creating session and fetching students...")
        
        # Fetch students for all batches concurrently
        loop = asyncio.get_event_loop()
        tasks = []
        for batch in selected_batches:
            batch = batch.strip()
            task = loop.run_in_executor(
                None, 
                api_service.get_students_for_session, 
                batch, subject, 'vijayawada'
            )
            tasks.append((batch, task))
        
        # Wait for all API calls to complete
        for batch, task in tasks:
            students = await task
            if students:
                # Convert to dict with studentId as key
                for student in students:
                    student_id = student.get('studentId')
                    if student_id:
                        all_students[student_id] = {
                            'studentId': student_id,
                            'name': student.get('name', ''),
                            'email': student.get('email', ''),
                            'BatchNo': student.get('BatchNo', batch)
                        }
        
        # Delete loading message
        try:
            await loading_msg.delete()
        except:
            pass
        
        if not all_students:
            await update.message.reply_text(
                f"❌ No students found for {batch_str} - {subject}. Please contact admin.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Create session data
        session_data = {
            'otp': otp,
            'teacher_id': teacher.get('_id'),
            'teacher_name': teacher.get('name'),
            'teacher_telegram_id': teacher.get('telegram_id'),
            'batch_name': batch_str,
            'subject': subject,
            'lat': location.latitude,
            'long': location.longitude,
            'created_at': datetime.now().isoformat(),
            'date': today,
            'location': 'vijayawada'
        }
        
        # Store session data in MongoDB for student validation
        session_stored = self.mongo_repo.create_session(
            otp=otp,
            lat=location.latitude,
            lng=location.longitude,
            batch_name=batch_str,
            subject=subject,
            students=all_students,
            teacher_id=teacher.get('_id'),
            teacher_name=teacher.get('name'),
            teacher_telegram_id=teacher.get('telegram_id')
        )
        
        if not session_stored:
            logger.warning(f"Failed to store session - duplicate check may not work for future sessions")
        
        logger.info(f"Session created for batches: {batch_str}, subject: {subject}, students: {len(all_students)}")
        
        # Schedule report generation after OTP expiry
        asyncio.create_task(self._schedule_report(otp, session_data, Config.OTP_EXPIRY_SECONDS))
        
        await update.message.reply_text(
            f"✅ Session Created!\n\n"
            f"📋 Class OTP: {otp}\n"
            f"📚 Batches: {batch_str}\n"
            f"📖 Subject: {subject}\n"
            f"👥 Students: {len(all_students)}\n"
            f"⏰ Valid for: {Config.OTP_EXPIRY_SECONDS // 60} minutes\n\n"
            f"Share this OTP with students to mark attendance.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        return ConversationHandler.END
    
    def _check_existing_session(self, teacher_id: str, batch: str, subject: str, date: str) -> bool:
        """Check if session already exists for teacher, batch, subject on given date."""
        try:
            if self.mongo_repo.db is None:
                logger.warning("MongoDB not connected - cannot check existing sessions")
                return False
            
            # Check sessions collection
            existing_session = self.mongo_repo.db.sessions.find_one({
                "teacher_id": teacher_id,
                "batch_name": batch,
                "subject": subject,
                "date": date
            })
            
            # Also check attendance_records collection
            existing_attendance = self.mongo_repo.db.attendance_records.find_one({
                "batch": batch,
                "subject": subject,
                "datetime": date
            })
            
            if existing_session:
                logger.info(f"Found existing session for teacher {teacher_id}, batch {batch}, subject {subject} on {date}")
                return True
            elif existing_attendance:
                logger.info(f"Found existing attendance record for batch {batch}, subject {subject} on {date}")
                return True
            else:
                logger.info(f"No existing session found for teacher {teacher_id}, batch {batch}, subject {subject} on {date}")
                return False
            
        except Exception as e:
            logger.error(f"Error checking existing session: {e}")
            return False
    

    async def _schedule_report(self, otp: str, session_data: dict, delay_seconds: int):
        """Schedule attendance report generation after OTP expiry."""
        await asyncio.sleep(delay_seconds + 30)  # Wait extra 30 seconds for final submissions
        
        try:
            # Generate attendance report
            report = self.attendance_service.get_attendance_report(
                batch=session_data['batch_name'],
                subject=session_data['subject'],
                session_data=session_data
            )
            
            # Get teacher's telegram ID from session data
            teacher_telegram_id = session_data.get('teacher_telegram_id')
            if not teacher_telegram_id:
                logger.warning(f"Cannot send report - teacher telegram_id not found for session {otp}")
                return
            
            # Format report message
            report_msg = self._format_attendance_report(session_data, report)
            
            # Send report to teacher
            await self.app.bot.send_message(
                chat_id=teacher_telegram_id,
                text=report_msg
            )
            
            logger.info(f"Sent attendance report for session {otp} to teacher {session_data.get('teacher_name')}")
            
        except Exception as e:
            logger.error(f"Failed to send attendance report for session {otp}: {e}")
    
    def _format_attendance_report(self, session_data: dict, report: dict) -> str:
        """Format attendance report message."""
        present_list = "\n".join([f"✅ {student}" for student in report['present']]) or "None"
        absent_list = "\n".join([f"❌ {student}" for student in report['absent']]) or "None"
        
        return f"""📊 Attendance Report

📚 Batch: {session_data['batch_name']}
📖 Subject: {session_data['subject']}
📅 Date: {report['date']}

👥 Summary:
• Total Students: {report['total']}
• Present: {len(report['present'])}
• Absent: {len(report['absent'])}

✅ Present Students:
{present_list}

❌ Absent Students:
{absent_list}

⏰ Session completed automatically."""
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation."""
        await update.message.reply_text("🚫 Cancelled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    def run_polling(self):
        """Start bot polling."""
        if self.app:
            self.app.run_polling()