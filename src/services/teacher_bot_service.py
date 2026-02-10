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
from src.utils.bot_messages import messages

logger = logging.getLogger(__name__)

# STATES
CREDENTIALS, PASSWORD, BATCH, SUBJECT, LOCATION = range(5)

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

        # Configure with longer timeouts
        from telegram.request import HTTPXRequest
        request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0
        )
        
        self.app = ApplicationBuilder().token(self.token).request(request).build()
        self.setup_handlers()

    def setup_handlers(self) -> None:
        """Set up conversation handlers for the bot."""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                CREDENTIALS: [MessageHandler(filters.CONTACT, self.handle_phone_verification)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_password_entry)],
                BATCH: [CallbackQueryHandler(self.handle_batch_selection)],
                SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_subject)],
                LOCATION: [MessageHandler(filters.LOCATION, self.receive_location)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel), CommandHandler("start", self.start)]
        )
        
        self.app.add_handler(conv_handler)
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_error_handler(self.error_handler)
        logger.info("Teacher Bot Handlers Configured.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        user = update.effective_user
        telegram_id = user.id
        
        logger.info(f"Teacher Bot: /start from {telegram_id}")
        
        # Check if teacher exists by telegram ID
        teacher = self.mongo_repo.get_teacher_by_telegram_id(telegram_id)
        
        if teacher and teacher.get('plain_password'):
            # Teacher found with stored password, load batches directly
            context.user_data['teacher'] = teacher
            context.user_data['api_username'] = teacher.get('email')
            context.user_data['api_password'] = teacher.get('plain_password')
            
            await update.message.reply_text(
                messages.teacher('welcome_back', name=teacher.get('name', 'Teacher')),
                parse_mode='Markdown'
            )
            
            return await self._load_batches_with_teacher_credentials(update, context, teacher)
        
        # Ask for phone number verification
        contact_btn = KeyboardButton(text="📱 Share Contact", request_contact=True)
        markup = ReplyKeyboardMarkup([[contact_btn]], one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            messages.teacher('welcome', name=user.first_name or 'Teacher'),
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        return CREDENTIALS
            

    
    async def _load_batches_with_teacher_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE, teacher: dict):
        """Load batches using stored teacher credentials."""
        from src.services.api_service import APIService
        api_service = APIService()
        
        username = context.user_data.get('api_username')
        password = context.user_data.get('api_password')
        
        loop = asyncio.get_event_loop()
        batch_subject_map = await loop.run_in_executor(
            None, 
            lambda: api_service.get_available_batches_and_subjects_with_auth(username, password)
        )
        
        if not batch_subject_map:
            await update.message.reply_text(
                messages.teacher('no_attendance'),
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Show batch selection
        available_batches = list(batch_subject_map.keys())
        context.user_data['available_batches'] = available_batches
        context.user_data['batch_subject_map'] = batch_subject_map
        context.user_data['selected_batches'] = []
        context.user_data['mentor_id'] = teacher.get('id')
        
        markup = self._get_batch_markup(available_batches, [])
        await update.message.reply_text(
            messages.teacher('select_batches'), 
            parse_mode='Markdown', 
            reply_markup=markup
        )
        return BATCH
    
    async def handle_password_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password entry and verify via API."""
        password = update.message.text.strip()
        phone = context.user_data.get('phone')
        
        if not phone:
            await update.message.reply_text(messages.teacher('session_expired'))
            return ConversationHandler.END
        
        # Ask for username (email)
        if not context.user_data.get('username_requested'):
            context.user_data['api_password'] = password
            context.user_data['username_requested'] = True
            
            await update.message.reply_text(messages.teacher('email_prompt'))
            return PASSWORD
        
        # Now we have both username and password
        username = password.lower().strip()  # Normalize email to lowercase
        actual_password = context.user_data.get('api_password')
        
        context.user_data['api_username'] = username
        context.user_data['api_password'] = actual_password
        
        await update.message.reply_text(messages.teacher('loading_batches'))
        
        from src.services.api_service import APIService
        api_service = APIService()
        
        # Debug: Log the credentials being used
        logger.info(f"Attempting authentication with username: {username}, password: [HIDDEN]")
        logger.info(f"Login URL will be: {api_service.jwt_login_endpoint}")
        
        loop = asyncio.get_event_loop()
        batch_subject_map = await loop.run_in_executor(
            None, 
            lambda: api_service.get_available_batches_and_subjects_with_auth(username, actual_password)
        )
        
        if not batch_subject_map:
            await update.message.reply_text(
                messages.teacher('auth_failed', username=username)
            )
            return ConversationHandler.END
        
        # Save teacher credentials for future use
        self.mongo_repo.save_teacher_credentials(
            telegram_id=update.effective_user.id,
            phone=phone,
            email=username,
            password=actual_password,
            name=update.effective_user.first_name or 'Teacher'
        )
        
        # Create teacher record from API response
        teacher = {
            'id': f"teacher_{update.effective_user.id}",
            'name': update.effective_user.first_name or 'Teacher',
            'email': username,
            'PhNumber': phone,
            'telegram_id': update.effective_user.id
        }
        context.user_data['teacher'] = teacher
        
        # Show batch selection
        available_batches = list(batch_subject_map.keys())
        context.user_data['available_batches'] = available_batches
        context.user_data['batch_subject_map'] = batch_subject_map
        context.user_data['selected_batches'] = []
        context.user_data['mentor_id'] = teacher.get('id')
        
        markup = self._get_batch_markup(available_batches, [])
        await update.message.reply_text(
            messages.teacher('auth_success', username=username), 
            parse_mode='Markdown', 
            reply_markup=markup
        )
        return BATCH
    
    async def handle_phone_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle phone number verification using API."""
        if not update.message.contact:
            await update.message.reply_text(messages.teacher('use_share_button'))
            return CREDENTIALS
        
        phone = update.message.contact.phone_number
        
        # Normalize phone number
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Phone verification for: {phone}")
        
        # Ask for password to verify via API
        context.user_data['phone'] = phone
        
        await update.message.reply_text(
            messages.teacher('phone_verified', phone=phone),
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        return PASSWORD

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
            await query.message.reply_text(
                messages.teacher('select_subject', batch=batch_str), 
                parse_mode='Markdown', 
                reply_markup=markup
            )
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
            await update.message.reply_text(messages.teacher('invalid_subject'))
            return SUBJECT
        
        # Check if session already exists for this teacher, batch, and subject today
        teacher = context.user_data.get('teacher', {})
        batch_str = context.user_data.get('sess_batch', '')
        today = datetime.now().strftime("%Y-%m-%d")
        teacher_id = teacher.get('_id') or teacher.get('id')
        existing_session = self._check_existing_session(teacher_id, batch_str, subject, today)
        
        if existing_session:
            await update.message.reply_text(
                messages.teacher('session_exists', subject=subject, batch=batch_str),
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        context.user_data['sess_subject'] = subject
        
        location_btn = KeyboardButton(text="📍 Share Live Location", request_location=True)
        markup = ReplyKeyboardMarkup([[location_btn]], one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            messages.teacher('share_location', subject=subject),
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
        loading_msg = await update.message.reply_text(messages.teacher('creating_session'))
        
        # Fetch students for all batches concurrently using teacher's credentials
        loop = asyncio.get_event_loop()
        tasks = []
        username = context.user_data.get('api_username')
        password = context.user_data.get('api_password')
        
        for batch in selected_batches:
            batch = batch.strip()
            task = loop.run_in_executor(
                None, 
                api_service.get_students_for_session_with_auth, 
                batch, subject, username, password, 'vijayawada'
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
                messages.teacher('no_students', batch=batch_str, subject=subject),
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Create session data
        teacher_id = teacher.get('_id') or teacher.get('id')
        session_data = {
            'otp': otp,
            'teacher_id': teacher_id,
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
        
        # Store teacher credentials in MongoDB session for student bot access
        session_stored = self.mongo_repo.create_session_with_credentials(
            otp=otp,
            lat=location.latitude,
            lng=location.longitude,
            batch_name=batch_str,
            subject=subject,
            students=all_students,
            teacher_id=teacher_id,
            teacher_name=teacher.get('name'),
            teacher_telegram_id=teacher.get('telegram_id'),
            teacher_credentials={
                'username': context.user_data.get('api_username', '').replace('mailto:', ''),
                'password': context.user_data.get('api_password')
            }
        )
        
        if not session_stored:
            logger.warning(f"Failed to store session - duplicate check may not work for future sessions")
        
        logger.info(f"Session created for batches: {batch_str}, subject: {subject}, students: {len(all_students)}")
        
        # Schedule report generation after OTP expiry
        asyncio.create_task(self._schedule_report(
            otp, session_data, Config.OTP_EXPIRY_SECONDS,
            teacher_credentials={
                'username': context.user_data.get('api_username', '').replace('mailto:', ''),
                'password': context.user_data.get('api_password')
            }
        ))
        
        await update.message.reply_text(
            messages.teacher('session_created', 
                otp=otp, 
                batch=batch_str, 
                subject=subject, 
                count=len(all_students),
                minutes=Config.OTP_EXPIRY_SECONDS // 60
            ),
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
    

    async def _schedule_report(self, otp: str, session_data: dict, delay_seconds: int, teacher_credentials: dict = None):
        """Schedule attendance report generation after OTP expiry."""
        await asyncio.sleep(delay_seconds + 15)  # Wait extra 15 seconds for final submissions
        
        try:
            # Generate attendance report using teacher credentials
            report = self.attendance_service.get_attendance_report(
                batch=session_data['batch_name'],
                subject=session_data['subject'],
                session_data={'teacher_credentials': teacher_credentials}
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
        
        return messages.teacher('attendance_report',
            batch=session_data['batch_name'],
            subject=session_data['subject'],
            date=report['date'],
            total=report['total'],
            present_count=len(report['present']),
            absent_count=len(report['absent']),
            present_list=present_list,
            absent_list=absent_list
        )
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation."""
        await update.message.reply_text(messages.teacher('cancelled'), reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information for teachers."""
        help_text = f"""📖 **Teacher Bot Guide**

1️⃣ Send /start
2️⃣ Share your **contact** for verification
3️⃣ Enter your **password** (saved for future use)
4️⃣ Select **batches** (multi-select supported)
5️⃣ Choose **subject**
6️⃣ Share your **location** to generate OTP

📋 **Session Details:**
• OTP expires in {Config.OTP_EXPIRY_SECONDS // 60} minutes
• Students must be within {Config.LOCATION_DISTANCE_LIMIT_METERS}m
• Attendance report sent automatically after session

💡 **Tips:**
• Share OTP with students immediately
• Stay at location until all students mark attendance
• Check report for absent students

❓ **Need Help?**
Contact technical support"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the bot."""
        from telegram.error import NetworkError, TimedOut
        
        error = context.error
        
        # Log all errors
        logger.error(f"Bot error: {error}", exc_info=context.error)
        
        # Handle specific error types silently (expected errors)
        if isinstance(error, (NetworkError, TimedOut)):
            logger.warning(f"Network error (auto-retry): {error}")
            return
        
        # For unexpected errors, notify user if update is available
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ An error occurred. Please try again or contact support."
                )
            except:
                pass
    
    def run_polling(self):
        """Start bot polling."""
        if self.app:
            self.app.run_polling()