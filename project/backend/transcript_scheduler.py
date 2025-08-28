import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from database import get_db, MeetingRaw, UserTokens
from ms_graph_service import MSGraphService
from whisper_service import whisper_service
from routers.auth import async_get_valid_token
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class TranscriptScheduler:
    def __init__(self):
        self.graph_service = MSGraphService()
        self.check_interval_minutes = int(os.getenv("TRANSCRIPT_CHECK_INTERVAL", "30"))  # Default 30 minutes
        self.max_meeting_age_hours = int(os.getenv("MAX_MEETING_AGE_HOURS", "24"))  # Only check meetings from last 24 hours
        # Explicit asyncio timeouts to prevent hangs
        self.cycle_timeout_seconds = int(os.getenv("TRANSCRIPT_CYCLE_TIMEOUT_SECONDS", "300"))  # per cycle timeout
        self.per_meeting_timeout_seconds = int(os.getenv("TRANSCRIPT_PER_MEETING_TIMEOUT_SECONDS", "120"))  # per meeting timeout
        self.running = False
        self.last_updated_count = 0
        
    async def start_scheduler(self):
        """Start the automatic transcript fetching scheduler"""
        if self.running:
            logger.warning("Transcript scheduler is already running")
            return
            
        self.running = True
        logger.info(f"Starting transcript scheduler - checking every {self.check_interval_minutes} minutes")
        
        while self.running:
            try:
                # Run one cycle with an overall timeout
                await asyncio.wait_for(
                    self.check_and_fetch_transcripts(),
                    timeout=self.cycle_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Transcript scheduler cycle timed out after {self.cycle_timeout_seconds}s"
                )
            except asyncio.CancelledError:
                logger.info("Transcript scheduler task cancelled; stopping.")
                self.running = False
                break
            except Exception as e:
                logger.exception(f"Error in transcript scheduler main cycle: {e}")

            if not self.running:
                break

            # Sleep between cycles; allow cancellation to stop promptly
            try:
                await asyncio.sleep(self.check_interval_minutes * 60)
            except asyncio.CancelledError:
                logger.info("Transcript scheduler sleep cancelled; stopping.")
                self.running = False
                break
                
    def stop_scheduler(self):
        """Stop the automatic transcript fetching scheduler"""
        self.running = False
        logger.info("Transcript scheduler stopped")
        
    async def check_and_fetch_transcripts(self):
        """Check for meetings without transcripts and attempt to fetch them"""
        logger.info("Starting transcript check cycle")
        
        # Get database session
        db = next(get_db())
        
        try:
            # Find meetings from the last N hours that don't have transcripts
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.max_meeting_age_hours)
            
            meetings_without_transcripts = db.query(MeetingRaw).filter(
                MeetingRaw.date >= cutoff_time.replace(tzinfo=None),
                MeetingRaw.transcript_text.in_(["Transcript not available", "", None])
            ).all()
            
            logger.info(f"Found {len(meetings_without_transcripts)} meetings without transcripts")
            
            # Determine available user tokens to use for fetching
            tokens = db.query(UserTokens).all()
            if not tokens:
                logger.warning("No user tokens available; cannot fetch transcripts. Ensure at least one user is authenticated via /api/auth/login.")
                return
            
            # Fallback strategy: assign all meetings to the first available token
            default_user_id = tokens[0].user_id
            user_meetings = {default_user_id: meetings_without_transcripts}
            logger.info(
                f"Assigning {len(meetings_without_transcripts)} meetings to default user {default_user_id} for transcript fetching"
            )
            
            logger.info(f"Processing meetings for {len(user_meetings)} users")
            
            # Process meetings for each user
            total_updated = 0
            for user_id, meetings in user_meetings.items():
                try:
                    updated_count = await self.fetch_transcripts_for_user(db, user_id, meetings)
                    total_updated += updated_count
                except Exception as e:
                    logger.error(f"Error processing meetings for user {user_id}: {str(e)}")
                    continue
            
            self.last_updated_count = total_updated
            logger.info(f"Transcript check cycle completed. Updated {total_updated} meetings")
            
        except Exception as e:
            logger.error(f"Error in transcript check cycle: {str(e)}")
        finally:
            db.close()
    
    async def fetch_transcripts_for_user(self, db: Session, user_id: str, meetings: List[MeetingRaw]) -> int:
        """Fetch transcripts for a specific user's meetings"""
        try:
            # Get valid access token
            access_token = await async_get_valid_token(user_id, db)
            
            updated_count = 0
            
            for meeting in meetings:
                async def process_one_meeting() -> int:
                    logger.info(f"Attempting to fetch transcript for meeting {meeting.meeting_id}")
                    
                    # Extract meeting details
                    participants = meeting.participants_json or []
                    start_time = meeting.date
                    end_time = start_time + timedelta(minutes=meeting.duration_minutes or 60)
                    
                    # Extract participant emails
                    participant_emails = []
                    for p in participants:
                        if isinstance(p, dict) and "emailAddress" in p:
                            email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                            if email:
                                participant_emails.append(email)
                        elif isinstance(p, str):
                            participant_emails.append(p)
                    
                    # PRIMARY: Try Whisper transcription first (better for Hindi and other languages)
                    transcript_text = await self.try_whisper_with_teams_recording(access_token, meeting, participant_emails)
                    
                    # FALLBACK: If Whisper failed, try Teams transcript methods
                    if not transcript_text:
                        use_teams_fallback = os.getenv("USE_TEAMS_TRANSCRIPT_FALLBACK", "false").lower() in ("1", "true", "yes")
                        if use_teams_fallback:
                            logger.info(f"Whisper failed, trying Teams transcript fallback for meeting {meeting.meeting_id}")
                            if participant_emails:
                                transcript_text = await self.graph_service.fetch_teams_transcript_directly(
                                    access_token, meeting.title, start_time, end_time, participant_emails
                                )
                            
                            # If direct fetch failed, try other Teams methods
                            if not transcript_text:
                                transcript_text = await self.try_fallback_transcript_methods(
                                    access_token, meeting, participant_emails
                                )
                        else:
                            logger.info("Teams transcript fallback disabled via USE_TEAMS_TRANSCRIPT_FALLBACK environment variable")
                    
                    # Update the meeting if we got a transcript
                    if transcript_text and len(transcript_text.strip()) > 50:  # Minimum meaningful transcript length
                        meeting.transcript_text = transcript_text
                        db.commit()
                        logger.info(
                            f"Successfully updated transcript for meeting {meeting.meeting_id} ({len(transcript_text)} chars)"
                        )
                        return 1
                    else:
                        logger.warning(f"No transcript found for meeting {meeting.meeting_id}")
                        return 0

                try:
                    updated_count += await asyncio.wait_for(
                        process_one_meeting(), timeout=self.per_meeting_timeout_seconds
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Timed out fetching transcript for meeting {meeting.meeting_id} after {self.per_meeting_timeout_seconds}s"
                    )
                except asyncio.CancelledError:
                    logger.info("Per-meeting transcript fetch cancelled; stopping.")
                    raise
                except Exception as e:
                    logger.error(f"Error fetching transcript for meeting {meeting.meeting_id}: {str(e)}")
                    continue
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error fetching transcripts for user {user_id}: {str(e)}")
            return 0
    
    async def try_fallback_transcript_methods(self, access_token: str, meeting: MeetingRaw, participant_emails: List[str]) -> Optional[str]:
        """Try fallback methods to get transcript"""
        try:
            # Method 1: Try to find online meeting by time and participants
            start_time = meeting.date
            end_time = start_time + timedelta(minutes=meeting.duration_minutes or 60)
            
            online_meeting = await self.graph_service.find_online_meeting_by_time_and_participants(
                access_token, start_time, end_time, participant_emails
            )
            
            if isinstance(online_meeting, dict):
                online_meeting_id = online_meeting.get("id")
                if online_meeting_id:
                    logger.info(f"Found online meeting ID via fallback: {online_meeting_id}")
                    
                    # Get transcripts for this meeting
                    transcripts = await self.graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    if transcripts:
                        # Get the latest transcript
                        latest_transcript = transcripts[-1]
                        transcript_id = latest_transcript.get("id")
                        
                        if transcript_id:
                            raw_content = await self.graph_service.get_online_meeting_transcript_content(
                                access_token, online_meeting_id, transcript_id, format="text"
                            )
                            cleaned = self.graph_service.to_plain_text(raw_content)
                            return cleaned or raw_content
            
            # Method 2: Try direct Teams meeting search
            online_meeting = await self.graph_service.search_teams_meetings_directly(
                access_token, start_time, end_time, participant_emails
            )
            
            if isinstance(online_meeting, dict):
                online_meeting_id = online_meeting.get("id")
                if online_meeting_id:
                    logger.info(f"Found online meeting ID via direct search: {online_meeting_id}")
                    
                    # Get transcripts for this meeting
                    transcripts = await self.graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    if transcripts:
                        # Get the latest transcript
                        latest_transcript = transcripts[-1]
                        transcript_id = latest_transcript.get("id")
                        
                        if transcript_id:
                            raw_content = await self.graph_service.get_online_meeting_transcript_content(
                                access_token, online_meeting_id, transcript_id, format="text"
                            )
                            cleaned = self.graph_service.to_plain_text(raw_content)
                            return cleaned or raw_content
            
            # NEW: Try calendarView-based resolution as last resort
            event = await self.graph_service.get_event_by_id(access_token, meeting.meeting_id)
            if event and event.get('onlineMeeting'):
                online_meeting_id = event['onlineMeeting'].get('id')
                if online_meeting_id:
                    transcripts = await self.graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    if transcripts:
                        latest_transcript = transcripts[-1]
                        transcript_id = latest_transcript.get('id')
                        if transcript_id:
                            raw_content = await self.graph_service.get_online_meeting_transcript_content(
                                access_token, online_meeting_id, transcript_id, format="text"
                            )
                            cleaned = self.graph_service.to_plain_text(raw_content)
                            return cleaned or raw_content
            
            return None
            
        except Exception as e:
            logger.error(f"Error in fallback transcript methods: {str(e)}")
            return None
    
    async def try_whisper_with_teams_recording(self, access_token: str, meeting: MeetingRaw, participant_emails: List[str]) -> Optional[str]:
        """Try to download Teams recording and transcribe using Whisper"""
        try:
            # Check if Whisper transcription is enabled
            use_whisper_fallback = os.getenv("USE_WHISPER_FALLBACK", "false").lower() in ("1", "true", "yes")
            if not use_whisper_fallback:
                logger.info("Whisper fallback disabled via USE_WHISPER_FALLBACK environment variable")
                return None
            
            logger.info(f"Attempting Teams recording download and Whisper transcription for meeting {meeting.meeting_id}")
            
            # Calculate meeting time range
            start_time = meeting.date
            end_time = start_time + timedelta(minutes=meeting.duration_minutes or 60)
            
            # Try to download Teams recording
            recording_content = await self.graph_service.find_and_download_meeting_recording(
                access_token, meeting.title or "Meeting", start_time, end_time, participant_emails
            )
            
            if not recording_content:
                logger.warning(f"No Teams recording found for meeting {meeting.meeting_id}")
                # Fallback to local file search if enabled
                return await self.try_whisper_local_file_fallback(meeting)
            
            logger.info(f"Downloaded Teams recording for meeting {meeting.meeting_id} ({len(recording_content)} bytes)")
            
            # Transcribe the downloaded recording using Whisper
            result = await whisper_service.transcribe_audio_bytes(
                recording_content, 
                filename=f"{meeting.meeting_id}_recording.mp4"
            )
            
            if result and result.get("text"):
                transcript_text = result["text"].strip()
                logger.info(f"Whisper transcription successful for meeting {meeting.meeting_id} ({len(transcript_text)} chars)")
                
                # Add metadata to indicate this was transcribed by Whisper from Teams recording
                whisper_metadata = f"\n\n[Transcribed using OpenAI Whisper from Teams recording - Language: {result.get('language', 'auto-detected')}]"
                return transcript_text + whisper_metadata
            else:
                logger.warning(f"Whisper transcription failed or returned empty text for meeting {meeting.meeting_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error in Teams recording download and Whisper transcription for meeting {meeting.meeting_id}: {str(e)}")
            return None

    async def try_whisper_local_file_fallback(self, meeting: MeetingRaw) -> Optional[str]:
        """Fallback to local file transcription if Teams recording not available"""
        try:
            # Check if local file fallback is enabled
            use_local_fallback = os.getenv("USE_LOCAL_FILE_FALLBACK", "true").lower() in ("1", "true", "yes")
            if not use_local_fallback:
                logger.info("Local file fallback disabled via USE_LOCAL_FILE_FALLBACK environment variable")
                return None
            
            logger.info(f"Attempting local file fallback for meeting {meeting.meeting_id}")
            
            # Look for audio file associated with this meeting
            audio_file_path = await self.find_meeting_audio_file(meeting)
            if not audio_file_path:
                logger.warning(f"No local audio file found for meeting {meeting.meeting_id}")
                return None
            
            # Transcribe using Whisper
            result = await whisper_service.transcribe_audio_file(audio_file_path)
            if result and result.get("text"):
                transcript_text = result["text"].strip()
                logger.info(f"Local file Whisper transcription successful for meeting {meeting.meeting_id} ({len(transcript_text)} chars)")
                
                # Add metadata to indicate this was transcribed by Whisper from local file
                whisper_metadata = f"\n\n[Transcribed using OpenAI Whisper from local file: {audio_file_path} - Language: {result.get('language', 'auto-detected')}]"
                return transcript_text + whisper_metadata
            else:
                logger.warning(f"Local file Whisper transcription failed or returned empty text for meeting {meeting.meeting_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error in local file Whisper transcription for meeting {meeting.meeting_id}: {str(e)}")
            return None
    
    async def find_meeting_audio_file(self, meeting: MeetingRaw) -> Optional[str]:
        """Find audio file for a meeting in configured directories"""
        try:
            # Get audio file directories from environment
            audio_dirs = os.getenv("MEETING_AUDIO_DIRECTORIES", "").split(",")
            audio_dirs = [d.strip() for d in audio_dirs if d.strip()]
            
            if not audio_dirs:
                logger.debug("No audio directories configured in MEETING_AUDIO_DIRECTORIES")
                return None
            
            # Common audio file extensions
            audio_extensions = [".wav", ".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".wma", ".aac"]
            
            # Search patterns based on meeting info
            search_patterns = [
                meeting.meeting_id,
                meeting.title.replace(" ", "_") if meeting.title else "",
                f"{meeting.date.strftime('%Y%m%d_%H%M')}_{meeting.title.replace(' ', '_')}" if meeting.title else "",
                meeting.date.strftime('%Y%m%d_%H%M')
            ]
            
            # Remove empty patterns
            search_patterns = [p for p in search_patterns if p]
            
            for audio_dir in audio_dirs:
                if not os.path.exists(audio_dir):
                    continue
                    
                for pattern in search_patterns:
                    for ext in audio_extensions:
                        # Try exact match
                        audio_file = os.path.join(audio_dir, f"{pattern}{ext}")
                        if os.path.exists(audio_file):
                            logger.info(f"Found audio file: {audio_file}")
                            return audio_file
                        
                        # Try case-insensitive search
                        for file in os.listdir(audio_dir):
                            if file.lower().startswith(pattern.lower()) and file.lower().endswith(ext):
                                audio_file = os.path.join(audio_dir, file)
                                logger.info(f"Found audio file (case-insensitive): {audio_file}")
                                return audio_file
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding audio file for meeting {meeting.meeting_id}: {str(e)}")
            return None

# Global scheduler instance
transcript_scheduler = TranscriptScheduler()

async def start_automatic_transcript_fetching():
    """Start the automatic transcript fetching service"""
    await transcript_scheduler.start_scheduler()

def stop_automatic_transcript_fetching():
    """Stop the automatic transcript fetching service"""
    transcript_scheduler.stop_scheduler()
