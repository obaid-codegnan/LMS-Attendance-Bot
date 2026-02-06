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
        logger.info("Student Bot Handlers Configured.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        logger.info(f"Student Bot: /start from {update.effective_user.id}")

        await update.message.reply_text(
            "👨🎓 **Welcome Student!**\n"
            "Please enter your **Student ID** to mark attendance:",
            parse_mode='Markdown'
        )
        return ID

    async def receive_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        student_id = update.message.text.strip()
        
        if not student_id or len(student_id) > 50:
            await update.message.reply_text("❌ Invalid Student ID. Please enter a valid ID.")
            return ID
            
        if not student_id.replace('_', '').replace('-', '').isalnum():
            await update.message.reply_text("❌ Student ID can only contain letters, numbers, hyphens, and underscores.")
            return ID
        
        context.user_data['student_id'] = student_id
        await update.message.reply_text("✅ **Student ID received!**\nEnter **Class OTP**:", parse_mode='Markdown')
        return OTP

    async def receive_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        otp = update.message.text.strip()
        
        if not otp.isdigit() or len(otp) != 6:
            await update.message.reply_text("❌ Invalid OTP format. Please enter a 6-digit OTP.")
            return OTP
        
        student_id = context.user_data['student_id']
        
        # Validate student for the session using API data
        validation_result = self.mongo_repo.validate_student_for_session(student_id, otp)
        
        if not validation_result:
            await update.message.reply_text(
                f"❌ Student ID '{student_id}' not found in this session or session expired.\n"
                f"Please check your Student ID and OTP.",
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
            f"✅ Welcome **{validation_result['name']}**!\n"
            f"🏫 Batch: {validation_result['batch']}\n\n"
            f"📍 Please share your **current location** to verify you're in class:", 
            reply_markup=markup,
            parse_mode='Markdown'
        )
        return LOCATION

    async def receive_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.location:
            return await self._process_location(update.message.location, update, context)
        else:
            await update.message.reply_text("❌ Location not received. Please try sharing your location again.")
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
            await update.message.reply_text("Invalid format. Use button or 'lat,long'.")
            return LOCATION

    async def _process_location(self, user_loc, update: Update, context: ContextTypes.DEFAULT_TYPE):
        session = context.user_data.get('session')
        if not session:
             await update.message.reply_text("❌ Session expired. Please start again with /start")
             return ConversationHandler.END

        try:
            # Validate session location data
            if session.get('lat') is None or session.get('long') is None:
                logger.error(f"Session location data is None: lat={session.get('lat')}, long={session.get('long')}")
                await update.message.reply_text("❌ Session location not available. Please contact teacher.")
                return ConversationHandler.END
            
            # Validate user location data
            if user_loc is None or user_loc.latitude is None or user_loc.longitude is None:
                logger.error(f"User location data is None: {user_loc}")
                await update.message.reply_text("❌ Location data not received. Please try sharing location again.")
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
            await update.message.reply_text("❌ Error processing location. Please try again.")
            return LOCATION
        
        if dist > Config.LOCATION_DISTANCE_LIMIT_METERS: 
            await update.message.reply_text(
                f"❌ Too far ({int(dist)}m). Limit: {Config.LOCATION_DISTANCE_LIMIT_METERS}m.\nYou must be in the class.", 
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCATION
            
        await update.message.reply_text(
            "📍 Location Verified!\n📸 Record a **Video Note** (Circle Video) of your face.\n_(Tap mic icon to switch to video note)_",
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
        await update.message.reply_text(
            f"✅Attendance Processing\n\n"
            f"You will receive confirmation shortly."
        )
        
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
                
                
            else:
                await update.message.reply_text(
                    f"❌ **Queue is full. Please try again in a moment.**\n"
                    f"_Process ID: {request_id}_"
                )
                
        except Exception as e:
            logger.error(f"[{request_id}] Error queuing task for {student_id}: {e}")
            await update.message.reply_text(
                f"❌ **Error processing video. Please try again.**\n"
                f"_Process ID: {request_id}_"
            )
        
        return ConversationHandler.END

    async def receive_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Please send a **Video Note** (Circle), not a photo.")
        return SELFIE

    async def handle_wrong_video_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Please record a **Video Note** (the circular one).")
        return SELFIE

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🚫 Cancelled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    def run_polling(self):
        """Start bot polling."""
        if self.app:
            self.app.run_polling()