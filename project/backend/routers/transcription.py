from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import logging
import tempfile
import os
from pathlib import Path
from datetime import timedelta

from whisper_service import whisper_service
from database import get_db, MeetingRaw
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transcription", tags=["transcription"])

@router.post("/upload")
async def transcribe_audio_upload(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    meeting_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload an audio file and transcribe it using OpenAI Whisper
    
    Args:
        file: Audio file to transcribe
        language: Optional language code (e.g., 'en', 'es', 'fr')
        meeting_id: Optional meeting ID to associate transcript with
        
    Returns:
        Transcription results including text, language, and segments
    """
    temp_file = None
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith(('audio/', 'video/')):
            # Also accept common video formats that contain audio
            allowed_extensions = whisper_service.get_supported_formats()
            file_ext = Path(file.filename or "").suffix.lower()
            if file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file type. Supported formats: {', '.join(allowed_extensions)}"
                )
        
        # Check file size (limit to 500MB)
        max_size = 500 * 1024 * 1024  # 500MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=413,
                detail="File too large. Maximum size is 500MB."
            )
        
        logger.info(f"Starting transcription for uploaded file: {file.filename} ({len(file_content)} bytes)")
        
        # Transcribe the audio
        transcription_options = {}
        if language:
            transcription_options["language"] = language
        
        result = await whisper_service.transcribe_audio_bytes(
            file_content, 
            filename=file.filename or "audio.wav",
            **transcription_options
        )
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Transcription failed. Please check the audio file and try again."
            )
        
        # If meeting_id is provided, update the meeting record
        if meeting_id:
            meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
            if meeting:
                # Add metadata to indicate this was transcribed by Whisper
                whisper_metadata = f"\n\n[Transcribed using OpenAI Whisper from uploaded file: {file.filename}]"
                meeting.transcript_text = result["text"] + whisper_metadata
                db.commit()
                logger.info(f"Updated meeting {meeting_id} with Whisper transcript")
            else:
                logger.warning(f"Meeting {meeting_id} not found, transcript not saved to database")
        
        return JSONResponse(content={
            "success": True,
            "transcript": result["text"],
            "language": result.get("language"),
            "duration": result.get("duration"),
            "segments_count": len(result.get("segments", [])),
            "meeting_id": meeting_id,
            "filename": file.filename
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing uploaded file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Transcription error: {str(e)}"
        )

@router.post("/url")
async def transcribe_audio_url(
    audio_url: str,
    language: Optional[str] = None,
    meeting_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Transcribe audio from a URL using OpenAI Whisper
    
    Args:
        audio_url: URL to audio file
        language: Optional language code
        meeting_id: Optional meeting ID to associate transcript with
        
    Returns:
        Transcription results
    """
    try:
        logger.info(f"Starting transcription for URL: {audio_url}")
        
        # Transcribe the audio from URL
        transcription_options = {}
        if language:
            transcription_options["language"] = language
        
        result = await whisper_service.transcribe_url(audio_url, **transcription_options)
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Transcription failed. Please check the URL and try again."
            )
        
        # If meeting_id is provided, update the meeting record
        if meeting_id:
            meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
            if meeting:
                whisper_metadata = f"\n\n[Transcribed using OpenAI Whisper from URL: {audio_url}]"
                meeting.transcript_text = result["text"] + whisper_metadata
                db.commit()
                logger.info(f"Updated meeting {meeting_id} with Whisper transcript")
            else:
                logger.warning(f"Meeting {meeting_id} not found, transcript not saved to database")
        
        return JSONResponse(content={
            "success": True,
            "transcript": result["text"],
            "language": result.get("language"),
            "duration": result.get("duration"),
            "segments_count": len(result.get("segments", [])),
            "meeting_id": meeting_id,
            "audio_url": audio_url
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing audio from URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Transcription error: {str(e)}"
        )

@router.get("/status")
async def get_transcription_status():
    """Get Whisper transcription service status and configuration"""
    try:
        model_info = whisper_service.get_model_info()
        
        return JSONResponse(content={
            "success": True,
            "service": "OpenAI Whisper",
            "status": "available" if model_info["model_loaded"] or True else "loading",
            "model_name": model_info["model_name"],
            "device": model_info["device"],
            "default_language": model_info["language"],
            "supported_formats": model_info["supported_formats"]
        })
        
    except Exception as e:
        logger.error(f"Error getting transcription status: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )

@router.post("/meeting/{meeting_id}/transcribe-from-teams")
async def transcribe_from_teams_recording(
    meeting_id: str,
    language: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Download Teams recording and transcribe using Whisper
    
    Args:
        meeting_id: ID of the meeting to transcribe
        language: Optional language code for Whisper
        
    Returns:
        Transcription results from Teams recording
    """
    try:
        # Find the meeting
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Get access token (using first available user token)
        from database import UserTokens
        from routers.auth import async_get_valid_token
        
        tokens = db.query(UserTokens).first()
        if not tokens:
            raise HTTPException(
                status_code=401,
                detail="No user tokens available. Please authenticate first."
            )
        
        access_token = await async_get_valid_token(tokens.user_id, db)
        
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
        
        # Download Teams recording
        from ms_graph_service import MSGraphService
        graph_service = MSGraphService()
        
        # Try direct approach using the joinUrl from the meeting event
        recording_content = None
        try:
            # Get the calendar event to extract joinUrl
            event = await graph_service.get_event_by_id(access_token, meeting_id)
            if event and event.get("onlineMeeting") and event["onlineMeeting"].get("joinUrl"):
                join_url = event["onlineMeeting"]["joinUrl"]
                logger.info(f"Using joinUrl from event: {join_url}")
                
                # Try to find online meeting by joinUrl
                online_meeting = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                if online_meeting:
                    online_meeting_id = online_meeting.get("id")
                    logger.info(f"Found online meeting ID: {online_meeting_id}")
                    
                    # List recordings for this meeting
                    recordings = await graph_service.list_online_meeting_recordings(access_token, online_meeting_id)
                    logger.info(f"Found {len(recordings)} recordings")
                    
                    if recordings:
                        # Get the latest recording
                        latest_recording = recordings[-1]
                        recording_id = latest_recording.get("id")
                        
                        if recording_id:
                            # Download the recording
                            recording_content = await graph_service.download_meeting_recording(
                                access_token, online_meeting_id, recording_id
                            )
                            logger.info(f"Downloaded recording: {len(recording_content) if recording_content else 0} bytes")
        except Exception as e:
            logger.warning(f"Direct joinUrl approach failed: {e}")
        
        # Fallback: Try OneDrive search if direct approach failed
        if not recording_content:
            logger.info("Trying OneDrive search for recording...")
            recording_content = await graph_service.search_onedrive_for_recording(
                access_token, meeting.title or "Meeting", start_time
            )
        
        # Final fallback to original method
        if not recording_content:
            recording_content = await graph_service.find_and_download_meeting_recording(
                access_token, meeting.title or "Meeting", start_time, end_time, participant_emails
            )
        
        if not recording_content:
            raise HTTPException(
                status_code=404,
                detail="No Teams recording found for this meeting"
            )
        
        # Transcribe using Whisper
        transcription_options = {}
        if language:
            transcription_options["language"] = language
        
        result = await whisper_service.transcribe_audio_bytes(
            recording_content,
            filename=f"{meeting_id}_teams_recording.mp4",
            **transcription_options
        )
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Whisper transcription failed"
            )
        
        # Update the meeting record
        whisper_metadata = f"\n\n[Transcribed using OpenAI Whisper from Teams recording]"
        meeting.transcript_text = result["text"] + whisper_metadata
        db.commit()
        
        logger.info(f"Successfully transcribed Teams recording for meeting {meeting_id}")
        
        return JSONResponse(content={
            "success": True,
            "transcript": result["text"],
            "language": result.get("language"),
            "duration": result.get("duration"),
            "segments_count": len(result.get("segments", [])),
            "meeting_id": meeting_id,
            "source": "teams_recording",
            "recording_size_bytes": len(recording_content)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing Teams recording for meeting {meeting_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Teams recording transcription error: {str(e)}"
        )

@router.post("/meeting/{meeting_id}/debug-recording-search")
async def debug_recording_search(
    meeting_id: str,
    db: Session = Depends(get_db)
):
    """
    Debug Teams recording search process for a specific meeting
    """
    try:
        # Find the meeting
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Get access token (using first available user token)
        from database import UserTokens
        from routers.auth import async_get_valid_token
        
        tokens = db.query(UserTokens).first()
        if not tokens:
            raise HTTPException(
                status_code=401,
                detail="No user tokens available. Please authenticate first."
            )
        
        access_token = await async_get_valid_token(tokens.user_id, db)
        
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
        
        from ms_graph_service import MSGraphService
        graph_service = MSGraphService()
        
        debug_info = {
            "meeting_id": meeting_id,
            "meeting_title": meeting.title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "participant_emails": participant_emails,
            "search_results": {}
        }
        
        # Try method 1: find_online_meeting_by_time_and_participants
        try:
            online_meeting_1 = await graph_service.find_online_meeting_by_time_and_participants(
                access_token, start_time, end_time, participant_emails
            )
            debug_info["search_results"]["method_1_time_participants"] = {
                "success": online_meeting_1 is not None,
                "result": online_meeting_1
            }
        except Exception as e:
            debug_info["search_results"]["method_1_time_participants"] = {
                "success": False,
                "error": str(e)
            }
        
        # Try method 2: search_teams_meetings_directly
        try:
            online_meeting_2 = await graph_service.search_teams_meetings_directly(
                access_token, start_time, end_time, participant_emails
            )
            debug_info["search_results"]["method_2_direct_search"] = {
                "success": online_meeting_2 is not None,
                "result": online_meeting_2
            }
        except Exception as e:
            debug_info["search_results"]["method_2_direct_search"] = {
                "success": False,
                "error": str(e)
            }
        
        # Try method 3: get_event_by_id (if available)
        try:
            event = await graph_service.get_event_by_id(access_token, meeting_id)
            debug_info["search_results"]["method_3_event_by_id"] = {
                "success": event is not None,
                "result": event,
                "has_online_meeting": event.get("onlineMeeting") is not None if event else False
            }
        except Exception as e:
            debug_info["search_results"]["method_3_event_by_id"] = {
                "success": False,
                "error": str(e)
            }
        
        return JSONResponse(content=debug_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error debugging recording search for meeting {meeting_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Debug error: {str(e)}"
        )

@router.post("/meeting/{meeting_id}/retranscribe")
async def retranscribe_meeting(
    meeting_id: str,
    force_whisper: bool = False,
    language: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retranscribe a specific meeting using Whisper
    
    Args:
        meeting_id: ID of the meeting to retranscribe
        force_whisper: Force use of Whisper even if transcript exists
        language: Optional language code for Whisper
        
    Returns:
        Transcription results
    """
    try:
        # Find the meeting
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Check if transcript already exists and force_whisper is False
        if meeting.transcript_text and not force_whisper and meeting.transcript_text not in ["Transcript not available", "", None]:
            return JSONResponse(content={
                "success": True,
                "message": "Meeting already has transcript. Use force_whisper=true to retranscribe.",
                "existing_transcript_length": len(meeting.transcript_text),
                "meeting_id": meeting_id
            })
        
        # Try to find audio file for this meeting
        from transcript_scheduler import transcript_scheduler
        audio_file_path = await transcript_scheduler.find_meeting_audio_file(meeting)
        
        if not audio_file_path:
            raise HTTPException(
                status_code=404,
                detail="No audio file found for this meeting. Please upload an audio file or configure MEETING_AUDIO_DIRECTORIES."
            )
        
        # Transcribe using Whisper
        transcription_options = {}
        if language:
            transcription_options["language"] = language
        
        result = await whisper_service.transcribe_audio_file(audio_file_path, **transcription_options)
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Whisper transcription failed"
            )
        
        # Update the meeting record
        whisper_metadata = f"\n\n[Retranscribed using OpenAI Whisper from: {audio_file_path}]"
        meeting.transcript_text = result["text"] + whisper_metadata
        db.commit()
        
        logger.info(f"Successfully retranscribed meeting {meeting_id} using Whisper")
        
        return JSONResponse(content={
            "success": True,
            "transcript": result["text"],
            "language": result.get("language"),
            "duration": result.get("duration"),
            "segments_count": len(result.get("segments", [])),
            "meeting_id": meeting_id,
            "audio_file": audio_file_path
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retranscribing meeting {meeting_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Retranscription error: {str(e)}"
        )
