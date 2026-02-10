"""
Student Bot Service.
Handles the conversation flow for Students: Login (ID), OTP, Location Check, Face Verification.
"""
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler
)
from geopy.distance import geodesic
from src.repositories.mongo_repository import MongoRepository
from src.services.api_attendance_service import APIAttendanceService
from src.config.settings import Config
from src.utils.bot_messages import messages

logger = logging.getLogger(__name__)

# STATES
ID, OTP, LOCATION, SELFIE = range(4)

class StudentBotService:
    def __init__(self):
        self.mongo_repo = MongoRepository()
        self.attendance_service = APIAttendanceService()
        self.app = None
        self.token = Config.STUDENT_BOT_TOKEN
        
        if not self.token:
            logger.warning("STUDENT_BOT_TOKEN not set. Student Bot will not start.")
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

    def setup_handlers(self):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_id)],
                OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_otp)],
                LOCATION: [
                    MessageHandler(filters.LOCATION, self.receive_location),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_location_text)
                ],
                SELFIE: [
                    MessageHandler(filters.VIDEO_NOTE, self.receive_video_note),
                    MessageHandler(filters.VIDEO, self.handle_wrong_video_type),
                    MessageHandler(filters.PHOTO, self.receive_photo)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel), CommandHandler("start", self.start)],
            per_message=False
        )
        self.app.add_handler(conv_handler)
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_error_handler(self.error_handler)
        logger.info("Student Bot Handlers Configured.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        logger.info(f"Student Bot: /start from {update.effective_user.id}")

        await update.message.reply_text(
            messages.student('welcome'),
            parse_mode='Markdown'
        )
        return ID

    async def receive_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        student_id = update.message.text.strip()
        
        if not student_id or len(student_id) > 50:
            await update.message.reply_text(messages.student('invalid_id'))
            return ID
            
        if not student_id.replace('_', '').replace('-', '').isalnum():
            await update.message.reply_text(messages.student('invalid_id_format'))
            return ID
        
        context.user_data['student_id'] = student_id
        await update.message.reply_text(messages.student('id_received'), parse_mode='Markdown')
        return OTP

    async def receive_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        otp = update.message.text.strip()
        
        if not otp.isdigit() or len(otp) != 6:
            await update.message.reply_text(messages.student('invalid_otp'))
            return OTP
        
        student_id = context.user_data['student_id']
        
        # Validate student for the session using API data
        validation_result = self.mongo_repo.validate_student_for_session(student_id, otp)
        
        if not validation_result:
            await update.message.reply_text(
                messages.student('student_not_found', student_id=student_id),
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Store student and session info
        context.user_data['student'] = validation_result
        context.user_data['session'] = validation_result['session_info']
        
        # Debug: Log if teacher credentials are available
        teacher_creds = validation_result['session_info'].get('teacher_credentials')
        logger.info(f"Teacher credentials available in session: {teacher_creds is not None}")
        if teacher_creds:
            logger.info(f"Teacher username: {teacher_creds.get('username', 'N/A')}")
        
        location_btn = KeyboardButton(text="📍 Share Current Location", request_location=True)
        markup = ReplyKeyboardMarkup([[location_btn]], one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            messages.student('welcome_student', 
                name=validation_result['name'],
                batch=validation_result['batch']
            ), 
            reply_markup=markup,
            parse_mode='Markdown'
        )
        return LOCATION

    async def receive_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.location:
            return await self._process_location(update.message.location, update, context)
        else:
            await update.message.reply_text(messages.student('location_not_received'))
            return LOCATION

    async def receive_location_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            txt = update.message.text.strip()
            lat, lng = map(float, txt.split(','))
            class MockLoc:
                latitude = lat
                longitude = lng
            return await self._process_location(MockLoc(), update, context)
        except:
            await update.message.reply_text(messages.student('invalid_location_format'))
            return LOCATION

    async def _process_location(self, user_loc, update: Update, context: ContextTypes.DEFAULT_TYPE):
        session = context.user_data.get('session')
        if not session:
             await update.message.reply_text(messages.student('session_expired'))
             return ConversationHandler.END

        try:
            # Validate session location data
            if session.get('lat') is None or session.get('long') is None:
                logger.error(f"Session location data is None: lat={session.get('lat')}, long={session.get('long')}")
                await update.message.reply_text(messages.student('session_location_error'))
                return ConversationHandler.END
            
            # Validate user location data
            if user_loc is None or user_loc.latitude is None or user_loc.longitude is None:
                logger.error(f"User location data is None: {user_loc}")
                await update.message.reply_text(messages.student('location_not_received'))
                return LOCATION
            
            class_lat = float(session['lat'])
            class_long = float(session['long'])
            user_lat = float(user_loc.latitude)
            user_lng = float(user_loc.longitude)
            
            dist = geodesic((user_lat, user_lng), (class_lat, class_long)).meters
            
        except (ValueError, TypeError) as e:
            logger.error(f"Location processing error: {e}")
            logger.error(f"Session data: {session}")
            logger.error(f"User location: lat={getattr(user_loc, 'latitude', None)}, lng={getattr(user_loc, 'longitude', None)}")
            await update.message.reply_text(messages.student('location_error'))
            return LOCATION
        
        if dist > Config.LOCATION_DISTANCE_LIMIT_METERS: 
            await update.message.reply_text(
                messages.student('too_far', 
                    distance=int(dist), 
                    limit=Config.LOCATION_DISTANCE_LIMIT_METERS
                ), 
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCATION
            
        await update.message.reply_text(
            messages.student('location_verified'),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return SELFIE

    async def receive_video_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import uuid
        import time
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        student_id = context.user_data['student_id']
        session = context.user_data['session']
        
        logger.info(f"[{request_id}] Video received from {student_id}")
        
        # Immediate acknowledgment - no delays!
        await update.message.reply_text(messages.student('processing'))
        
        try:
            # Download video bytes once
            video_file = await update.message.video_note.get_file()
            video_bytes = await video_file.download_as_bytearray()
            
            # Add to queue for processing
            from src.utils.face_verification_queue import face_queue, VerificationTask
            
            task = VerificationTask(
                request_id=request_id,
                student_id=student_id,
                video_bytes=bytes(video_bytes),  # Pass video bytes instead of file object
                batch_name=session['batch_name'],
                session_info=session,
                user_id=update.effective_user.id,
                timestamp=time.time(),
                teacher_credentials=session.get('teacher_credentials')
            )
            
            success = face_queue.add_task(task)
            
            if success:
                # Get queue stats for user feedback
                stats = face_queue.get_stats()
                # Stay in SELFIE state to allow retry
                return SELFIE
            else:
                await update.message.reply_text(messages.student('queue_full', request_id=request_id))
                return SELFIE
                
        except Exception as e:
            logger.error(f"[{request_id}] Error queuing task for {student_id}: {e}")
            await update.message.reply_text(messages.student('processing_error', request_id=request_id))
            return SELFIE

    async def receive_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(messages.student('wrong_media_photo'))
        return SELFIE

    async def handle_wrong_video_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(messages.student('wrong_media_video'))
        return SELFIE

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(messages.student('cancelled'), reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information."""
        help_text = f"""📖 **How to Mark Attendance**

1️⃣ Send /start
2️⃣ Enter your **Student ID**
3️⃣ Enter the **OTP** from teacher
4️⃣ Share your **location**
5️⃣ Record a **video note** of your face

💡 **Tips for Success:**
• Ensure good lighting
• Face the camera directly
• Be within {Config.LOCATION_DISTANCE_LIMIT_METERS} meters of classroom
• You get {Config.FACE_VERIFICATION_MAX_RETRIES + 1} total attempts

📹 **Video Note:**
Tap the microphone icon and hold to record a circular video (not regular video)

❓ **Having Issues?**
Contact your teacher for help"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the bot."""
        from telegram.error import NetworkError, TimedOut
        
        error = context.error
        logger.error(f"Bot error: {error}", exc_info=context.error)
        
        if isinstance(error, (NetworkError, TimedOut)):
            logger.warning(f"Network error (auto-retry): {error}")
            return
        
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