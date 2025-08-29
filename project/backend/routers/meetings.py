from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from database import get_db, MeetingRaw, MOMStructured, HRData
from ms_graph_service import MSGraphService
from mom_generator import MOMGenerator
from analytics_service import AnalyticsService
from routers.auth import async_get_valid_token
from transcript_scheduler import transcript_scheduler
import logging
from uuid import uuid4
from zoneinfo import ZoneInfo
import httpx
from database import UserTokens
import re

logger = logging.getLogger(__name__)
router = APIRouter()

graph_service = MSGraphService()
mom_generator = MOMGenerator()
analytics_service = AnalyticsService()

@router.post("/sync/{user_id}")
async def sync_meetings(
    user_id: str,
    days_back: int = Query(default=7, description="Number of days back to sync"),
    db: Session = Depends(get_db)
):
    """Sync meetings from Microsoft Teams"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        # Calculate date range (UTC timezone-aware)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        # Fetch meetings from Microsoft Graph
        meetings = await graph_service.get_user_meetings(access_token, start_date, end_date)
        
        logger.info(f"Processing {len(meetings)} meetings from Graph API")
        synced_meetings = []
        
        for i, meeting in enumerate(meetings):
            meeting_id = meeting["id"]
            meeting_title = meeting.get("subject", "Untitled Meeting")
            
            logger.info(f"Processing meeting {i+1}/{len(meetings)}: {meeting_title} (ID: {meeting_id})")
            
            # Check if meeting already exists
            existing_meeting = db.query(MeetingRaw).filter(
                MeetingRaw.meeting_id == meeting_id
            ).first()
            
            if existing_meeting:
                logger.info(f"Meeting {meeting_id} already exists, skipping")
                continue
            
            # Extract meeting data
            try:
                title = meeting.get("subject", "Untitled Meeting")
                # Graph may return dateTime without 'Z' and a separate timeZone field
                def parse_graph_dt(info: dict) -> datetime:
                    if not isinstance(info, dict):
                        raise ValueError("Invalid datetime info")
                    raw = (info.get("dateTime") or "").replace("Z", "+00:00")
                    if not raw:
                        raise ValueError("Missing dateTime")
                    dt = datetime.fromisoformat(raw)
                    if dt.tzinfo is None:
                        tz_name = (info.get("timeZone") or "").upper()
                        if tz_name in ("UTC", "Z"):
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            try:
                                dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                            except Exception:
                                # Fallback to UTC if unknown timezone label
                                dt = dt.replace(tzinfo=timezone.utc)
                    return dt

                start_dt = parse_graph_dt(meeting.get("start") or {})
                end_dt = parse_graph_dt(meeting.get("end") or {})
                # Normalize to naive UTC for DB storage
                start_time = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                end_time = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
                duration_minutes = int((end_time - start_time).total_seconds() / 60)
                
                logger.info(f"Meeting details - Title: {title}, Start(UTC): {start_time}, Duration: {duration_minutes}min")
            except Exception as parse_error:
                logger.error(f"Error parsing meeting data for {meeting_id}: {str(parse_error)}")
                logger.error(f"Meeting data: {meeting}")
                continue
            
            # Get participants
            participants = []
            if meeting.get("attendees"):
                participants = meeting["attendees"]
            
            # Try to fetch transcript via Graph (requires permissions and that transcription was enabled)
            transcript_text = ""
            try:
                # NEW APPROACH: Try direct Teams transcript fetching first
                logger.info(f"Attempting direct Teams transcript fetch for meeting {meeting_id}")
                try:
                    # Calculate end time if not provided
                    end_time = meeting.get("end", {}).get("dateTime")
                    if end_time:
                        end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    else:
                        # Default to 1 hour duration if end time not available
                        end_time = start_time + timedelta(hours=1)
                    
                    # Extract participant emails for matching
                    participant_emails = []
                    for p in participants:
                        if isinstance(p, dict) and "emailAddress" in p:
                            email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                            if email:
                                participant_emails.append(email)
                        elif isinstance(p, str):
                            participant_emails.append(p)
                    
                    if participant_emails:
                        direct_transcript = await graph_service.fetch_teams_transcript_directly(
                            access_token, title, start_time, end_time, participant_emails
                        )
                        if direct_transcript:
                            transcript_text = direct_transcript
                            logger.info(f"Successfully retrieved transcript directly from Teams for {meeting_id} ({len(transcript_text)} chars)")
                        else:
                            logger.info(f"Direct Teams transcript fetch failed for {meeting_id}, trying fallback methods")
                    else:
                        logger.warning(f"No participant emails available for direct Teams transcript fetch for {meeting_id}")
                except Exception as direct_err:
                    logger.warning(f"Direct Teams transcript fetch failed for {meeting_id}: {direct_err}")
                
                # FALLBACK: Original methods if direct fetch failed
                if not transcript_text:
                    logger.info(f"Trying fallback transcript methods for {meeting_id}")
                    
                    # Try to get onlineMeeting from the calendar event itself
                    online_meeting = meeting.get("onlineMeeting")
                    online_meeting_id = None
                    
                    if online_meeting and isinstance(online_meeting, dict):
                        # Get the join URL from the onlineMeeting object
                        join_url = online_meeting.get("joinUrl")
                        logger.info(f"Meeting {meeting_id} has onlineMeeting object with join URL: {join_url}")
                        
                        if join_url:
                            logger.info(f"Attempting join URL lookup for {meeting_id}")
                            online_meeting_obj = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                            if isinstance(online_meeting_obj, dict):
                                online_meeting_id = online_meeting_obj.get("id")
                                logger.info(f"Found onlineMeeting ID via join URL: {online_meeting_id}")
                            else:
                                logger.warning(f"Join URL lookup returned no results for {meeting_id}")
                        else:
                            logger.warning(f"onlineMeeting object exists but no joinUrl for {meeting_id}")
                    else:
                        # Fallback to the old onlineMeetingUrl field
                        join_url = meeting.get("onlineMeetingUrl")
                        logger.info(f"Meeting {meeting_id} onlineMeetingUrl: {join_url}")
                        
                        if join_url:
                            logger.info(f"Attempting join URL lookup for {meeting_id}")
                            online_meeting_obj = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                            if isinstance(online_meeting_obj, dict):
                                online_meeting_id = online_meeting_obj.get("id")
                                logger.info(f"Found onlineMeeting ID via join URL: {online_meeting_id}")
                            else:
                                logger.warning(f"Join URL lookup returned no results for {meeting_id}")
                    
                    # Try time/participants fallback since event expansion doesn't work
                    if not online_meeting_id:
                        logger.info(f"Trying time/participants fallback for {meeting_id}")
                        try:
                            # Calculate end time if not provided
                            end_time = meeting.get("end", {}).get("dateTime")
                            if end_time:
                                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                            else:
                                # Default to 1 hour duration if end time not available
                                end_time = start_time + timedelta(hours=1)
                            
                            # Extract participant emails for matching
                            participant_emails = []
                            for p in participants:
                                if isinstance(p, dict) and "emailAddress" in p:
                                    email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                                    if email:
                                        participant_emails.append(email)
                                elif isinstance(p, str):
                                    participant_emails.append(p)
                            
                            if participant_emails:
                                online_meeting = await graph_service.find_online_meeting_by_time_and_participants(
                                    access_token, start_time, end_time, participant_emails
                                )
                                if isinstance(online_meeting, dict):
                                    online_meeting_id = online_meeting.get("id")
                                    if online_meeting_id:
                                        logger.info(f"Resolved onlineMeeting via time/participants fallback for event {meeting_id}: {online_meeting_id}")
                                    else:
                                        logger.warning(f"Time/participants fallback returned dict but no ID for {meeting_id}")
                                else:
                                    logger.warning(f"Time/participants fallback returned no onlineMeeting for {meeting_id}")
                            else:
                                logger.warning(f"No participant emails available for time/participants fallback for {meeting_id}")
                        except Exception as tp_err:
                            logger.warning(f"Time/participants fallback failed for {meeting_id}: {tp_err}")
                    
                    # Third fallback: search Teams meetings directly
                    if not online_meeting_id:
                        logger.info(f"Trying direct Teams meeting search for {meeting_id}")
                        try:
                            # Calculate end time if not provided
                            end_time = meeting.get("end", {}).get("dateTime")
                            if end_time:
                                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                            else:
                                # Default to 1 hour duration if end time not available
                                end_time = start_time + timedelta(hours=1)
                            
                            # Extract participant emails for matching
                            participant_emails = []
                            for p in participants:
                                if isinstance(p, dict) and "emailAddress" in p:
                                    email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                                    if email:
                                        participant_emails.append(email)
                                elif isinstance(p, str):
                                    participant_emails.append(p)
                            
                            if participant_emails:
                                online_meeting = await graph_service.search_teams_meetings_directly(
                                    access_token, start_time, end_time, participant_emails
                                )
                                if isinstance(online_meeting, dict):
                                    online_meeting_id = online_meeting.get("id")
                                    if online_meeting_id:
                                        logger.info(f"Resolved onlineMeeting via direct Teams search for event {meeting_id}: {online_meeting_id}")
                                    else:
                                        logger.warning(f"Direct Teams search returned dict but no ID for {meeting_id}")
                                else:
                                    logger.warning(f"Direct Teams search returned no onlineMeeting for {meeting_id}")
                            else:
                                logger.warning(f"No participant emails available for direct Teams search for {meeting_id}")
                        except Exception as dt_err:
                            logger.warning(f"Direct Teams search failed for {meeting_id}: {dt_err}")
                
                if online_meeting_id:
                    logger.info(f"Fetching transcripts for onlineMeeting {online_meeting_id}")
                    transcripts = await graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    logger.info(f"Found {len(transcripts)} transcripts for meeting {meeting_id}")
                    if transcripts:
                        # Prefer the newest transcript
                        try:
                            transcripts_sorted = sorted(transcripts, key=lambda t: t.get("createdDateTime", ""))
                        except Exception:
                            transcripts_sorted = transcripts
                        latest = transcripts_sorted[-1]
                        transcript_id = latest.get("id")
                        logger.info(f"Using transcript ID {transcript_id} for meeting {meeting_id}")
                        if transcript_id:
                            raw_content = await graph_service.get_online_meeting_transcript_content(access_token, online_meeting_id, transcript_id, format="text")
                            logger.info(f"Retrieved {len(raw_content)} chars of transcript content for {meeting_id}")
                            cleaned = graph_service.to_plain_text(raw_content)
                            transcript_text = cleaned or raw_content or ""
                    else:
                        logger.warning(f"No transcripts found for onlineMeeting {online_meeting_id}")
                else:
                    logger.warning(f"Could not resolve onlineMeeting ID for event {meeting_id}")
                    # Add more detailed logging for debugging
                    logger.error(f"Meeting {meeting_id} ({title}) transcript fetch failed:")
                    logger.error(f"  - isOnlineMeeting: {meeting.get('isOnlineMeeting')}")
                    logger.error(f"  - onlineMeetingUrl: {meeting.get('onlineMeetingUrl')}")
                    logger.error(f"  - onlineMeeting object: {meeting.get('onlineMeeting')}")
                    logger.error(f"  - attendees count: {len(participants)}")
                    logger.error(f"  - start time: {start_time}")
                    logger.error(f"  - This suggests the meeting is marked as Teams but has no actual Teams session")
                    logger.error(f"  - Check in Microsoft Teams if this meeting actually exists as a Teams meeting")
                    logger.error(f"  - If not, the meeting was created in Outlook/Calendar but never joined in Teams")
                
                if not transcript_text:
                    transcript_text = "Transcript not available"
                    logger.warning(f"Final transcript result for {meeting_id}: empty/unavailable")
                else:
                    logger.info(f"Successfully retrieved transcript for {meeting_id} ({len(transcript_text)} chars)")
            except Exception as e:
                logger.error(f"Could not fetch transcript for meeting {meeting_id}: {str(e)}")
                transcript_text = "Transcript not available"
            
            # Store raw meeting data
            try:
                # Determine initial transcription status
                if transcript_text and transcript_text != "Transcript not available" and len(transcript_text.strip()) > 50:
                    transcription_status = "completed"
                    # Determine method from transcript content
                    if "[Transcribed using OpenAI Whisper" in transcript_text:
                        if "from Teams recording" in transcript_text:
                            transcription_method = "whisper_teams"
                        elif "from local file" in transcript_text:
                            transcription_method = "whisper_local"
                        else:
                            transcription_method = "whisper"
                    else:
                        transcription_method = "teams"
                else:
                    transcription_status = "pending"
                    transcription_method = None
                
                meeting_raw = MeetingRaw(
                    meeting_id=meeting_id,
                    title=title,
                    date=start_time,
                    transcript_text=transcript_text,
                    participants_json=participants,
                    duration_minutes=duration_minutes,
                    transcription_status=transcription_status,
                    transcription_method=transcription_method,
                    mom_generated=False
                )
                
                db.add(meeting_raw)
                db.commit()
                
                logger.info(f"Successfully stored meeting {meeting_id} in database")
            except Exception as db_error:
                logger.error(f"Database error storing meeting {meeting_id}: {str(db_error)}")
                db.rollback()
                continue
            
            # Store analytics data
            analytics_data = {
                "meeting_id": meeting_id,
                "date": start_time,
                "duration_minutes": duration_minutes,
                "participants_json": participants
            }
            
            analytics_service.store_meeting_analytics(db, analytics_data)
            
            synced_meetings.append({
                "meeting_id": meeting_id,
                "title": title,
                "date": start_time.isoformat(),
                "participants_count": len(participants),
                "duration_minutes": duration_minutes,
                "has_transcript": len(transcript_text) > 100
            })
        
        logger.info(f"Synced {len(synced_meetings)} meetings for user {user_id}")
        
        # NEW: After syncing meetings, trigger transcript fetch using the global scheduler instance
        await transcript_scheduler.check_and_fetch_transcripts()
        
        return {
            "synced_count": len(synced_meetings),
            "transcript_updated_count": transcript_scheduler.last_updated_count,
            "meetings": synced_meetings
        }
        
    except HTTPException as he:
        # Propagate HTTP exceptions (e.g., 401) without wrapping
        logger.error(f"HTTP error syncing meetings: {he.detail}")
        raise he
    except Exception as e:
        import traceback
        error_msg = str(e) if str(e) else "Unknown error occurred"
        logger.error(f"Error syncing meetings: {error_msg}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync meetings: {error_msg}"
        )

@router.post("/generate-mom/{meeting_id}")
async def generate_mom(meeting_id: str, db: Session = Depends(get_db)):
    """Generate Minutes of Meeting for a specific meeting"""
    try:
        # Get meeting data
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        
        if not meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found"
            )
        
        # Check if MOM already exists
        existing_mom = db.query(MOMStructured).filter(
            MOMStructured.meeting_id == meeting_id
        ).first()
        
        if existing_mom:
            return {
                "message": "MOM already exists",
                "mom_id": existing_mom.id,
                "mom": {
                    "meeting_title": existing_mom.meeting_title,
                    "date": existing_mom.date.isoformat(),
                    "agenda": existing_mom.agenda,
                    "key_decisions": existing_mom.key_decisions,
                    "action_items": existing_mom.action_items,
                    "follow_up_points": existing_mom.follow_up_points
                }
            }
        
        # Generate MOM using AI
        participants = meeting.participants_json or []
        mom_data = await mom_generator.generate_mom(
            transcript_text=meeting.transcript_text,
            participants=participants,
            meeting_title=meeting.title,
            meeting_date=meeting.date
        )
        
        # Store structured MOM
        mom_structured = MOMStructured(
            meeting_id=meeting_id,
            meeting_title=mom_data["meeting_title"],
            date=datetime.fromisoformat(mom_data["date"]),
            agenda=mom_data["agenda"],
            key_decisions=mom_data["key_decisions"],
            action_items=mom_data["action_items"],
            follow_up_points=mom_data["follow_up_points"]
        )
        
        db.add(mom_structured)
        db.commit()
        
        logger.info(f"Generated MOM for meeting {meeting_id}")
        
        return {
            "message": "MOM generated successfully",
            "mom_id": mom_structured.id,
            "mom": mom_data,
            "action_items_count": len(mom_data["action_items"])
        }
        
    except Exception as e:
        logger.error(f"Error generating MOM: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate MOM: {str(e)}"
        )

@router.get("/")
async def get_meetings(
    skip: int = Query(default=0),
    limit: int = Query(default=20),
    db: Session = Depends(get_db)
):
    """Get list of meetings"""
    # Order by meeting date descending (latest first)
    meetings = db.query(MeetingRaw).order_by(MeetingRaw.date.desc()).offset(skip).limit(limit).all()
    
    meeting_list = []
    for meeting in meetings:
        # Check if MOM exists
        mom_exists = db.query(MOMStructured).filter(
            MOMStructured.meeting_id == meeting.meeting_id
        ).first() is not None
        
        meeting_list.append({
            "meeting_id": meeting.meeting_id,
            "title": meeting.title,
            "date": meeting.date.isoformat(),
            "duration_minutes": meeting.duration_minutes,
            "participants_count": len(meeting.participants_json or []),
            "has_mom": mom_exists,
            "has_transcript": len(meeting.transcript_text or "") > 100,
            "transcription_status": getattr(meeting, 'transcription_status', 'pending'),
            "transcription_method": getattr(meeting, 'transcription_method', None),
            "mom_generated": getattr(meeting, 'mom_generated', False)
        })
    
    return {
        "meetings": meeting_list,
        "total": len(meeting_list)
    }

@router.post("/seed-sample")
async def seed_sample_meeting(
    with_mom: bool = Query(default=False, description="If true, also create a MOM with action items"),
    db: Session = Depends(get_db)
):
    """Create a sample meeting with transcript. Optionally create a ready MOM for testing."""
    try:
        # Unique sample meeting id
        meeting_id = f"sample-{uuid4().hex}"
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        participants = [
            {"emailAddress": {"address": "lakshay.1@kochartech.com", "name": "Lakshay 1"}, "type": "required"},
            {"emailAddress": {"address": "bob.smith@example.com", "name": "Bob Smith"}, "type": "required"},
            {"emailAddress": {"address": "carol.lee@example.com", "name": "Carol Lee"}, "type": "optional"},
        ]

        transcript_text = (
            "[00:00] Alice: Welcome everyone to the project kickoff.\n"
            "[00:05] Bob: Agenda today is introductions, scope, and next steps.\n"
            "[00:12] Carol: We should align on timelines and critical milestones.\n"
            "[00:25] Alice: Action items include setting up the repo, CI, and drafting API contracts.\n"
            "[00:40] Bob: I can prepare initial UI wireframes.\n"
            "[00:55] Carol: I'll draft the API contracts and confirm Graph API access.\n"
            "[01:10] Alice: Great. We'll reconvene next week for progress updates."
        )

        # Store raw meeting
        meeting_raw = MeetingRaw(
            meeting_id=meeting_id,
            title="Project Kickoff - Sample",
            date=now_utc,
            transcript_text=transcript_text,
            participants_json=participants,
            duration_minutes=45,
        )
        db.add(meeting_raw)
        db.commit()

        mom_structured = None
        if with_mom:
            # Optionally create MOM with action items so the Tasks page can show them immediately
            mom_structured = MOMStructured(
                meeting_id=meeting_id,
                meeting_title="Project Kickoff - Sample",
                date=now_utc,
                agenda=[
                    "Introductions",
                    "Scope & Objectives",
                    "Timelines & Milestones",
                ],
                key_decisions=[
                    "Stack: FastAPI backend, React + TS frontend",
                    "Sprints: 2-week cadence",
                ],
                action_items=[
                    {
                        "task": "Set up project repository and CI pipeline",
                        "assigned_to": "lakshay.1@kochartech.com",
                        "due_date": (now_utc + timedelta(days=3)).isoformat(),
                        "priority": "high",
                    },
                    {
                        "task": "Prepare initial UI wireframes",
                        "assigned_to": "lakshay.1@kochartech.com",
                        "due_date": (now_utc + timedelta(days=5)).isoformat(),
                        "priority": "medium",
                    },
                    {
                        "task": "Draft API contracts",
                        "assigned_to": "lakshay.1@kochartech.com",
                        "due_date": (now_utc + timedelta(days=4)).isoformat(),
                        "priority": "medium",
                    },
                ],
                follow_up_points=[
                    "Confirm access to Microsoft Graph API",
                    "Schedule weekly standups",
                ],
            )
            db.add(mom_structured)
            db.commit()

        return {
            "message": "Sample meeting and MOM created",
            "meeting_id": meeting_id,
            "title": meeting_raw.title,
            "date": now_utc.isoformat(),
            "participants_count": len(participants),
            "mom_action_items": len(mom_structured.action_items or []) if mom_structured else 0,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed sample meeting: {str(e)}",
        )
    
@router.get("/mom/{meeting_id}")
async def get_mom(meeting_id: str, db: Session = Depends(get_db)):
    """Get Minutes of Meeting for a specific meeting"""
    mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
    
    if not mom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOM not found for this meeting"
        )
    
    return {
        "mom_id": mom.id,
        "meeting_id": mom.meeting_id,
        "meeting_title": mom.meeting_title,
        "date": mom.date.isoformat(),
        "agenda": mom.agenda,
        "key_decisions": mom.key_decisions,
        "action_items": mom.action_items,
        "follow_up_points": mom.follow_up_points,
        "created_at": mom.created_at.isoformat()
    }

@router.post("/test-transcript-fetch/{user_id}")
async def test_transcript_fetch(user_id: str, db: Session = Depends(get_db)):
    """Manually trigger transcript fetching for testing purposes"""
    try:
        from transcript_scheduler import transcript_scheduler
        
        # Get user's meetings without transcripts from last 24 hours
        from datetime import datetime, timezone, timedelta
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        meetings_without_transcripts = db.query(MeetingRaw).filter(
            MeetingRaw.date >= cutoff_time.replace(tzinfo=None),
            MeetingRaw.transcript_text.in_(["Transcript not available", "", None])
        ).all()
        
        if not meetings_without_transcripts:
            return {
                "message": "No meetings without transcripts found in the last 24 hours",
                "meetings_checked": 0
            }
        
        # Try to fetch transcripts for these meetings
        updated_count = await transcript_scheduler.fetch_transcripts_for_user(
            db, user_id, meetings_without_transcripts
        )
        
        return {
            "message": f"Transcript fetch test completed",
            "meetings_checked": len(meetings_without_transcripts),
            "transcripts_updated": updated_count,
            "success_rate": f"{(updated_count/len(meetings_without_transcripts)*100):.1f}%" if meetings_without_transcripts else "0%"
        }
        
    except Exception as e:
        logger.error(f"Error in test transcript fetch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test transcript fetch failed: {str(e)}"
        )

@router.get("/transcript-status")
async def get_transcript_status(db: Session = Depends(get_db)):
    """Get statistics about transcript availability"""
    try:
        from datetime import datetime, timezone, timedelta
        
        # Get meetings from last 7 days
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
        
        total_meetings = db.query(MeetingRaw).filter(
            MeetingRaw.date >= cutoff_time.replace(tzinfo=None)
        ).count()
        
        meetings_with_transcripts = db.query(MeetingRaw).filter(
            MeetingRaw.date >= cutoff_time.replace(tzinfo=None),
            MeetingRaw.transcript_text.notin_(["Transcript not available", "", None]),
            MeetingRaw.transcript_text != None
        ).count()
        
        meetings_without_transcripts = db.query(MeetingRaw).filter(
            MeetingRaw.date >= cutoff_time.replace(tzinfo=None),
            MeetingRaw.transcript_text.in_(["Transcript not available", "", None])
        ).count()
        
        # Get recent transcript updates (last 2 hours)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        recent_updates = db.query(MeetingRaw).filter(
            MeetingRaw.updated_at >= recent_cutoff.replace(tzinfo=None),
            MeetingRaw.transcript_text.notin_(["Transcript not available", "", None])
        ).count()
        
        return {
            "period": "Last 7 days",
            "total_meetings": total_meetings,
            "meetings_with_transcripts": meetings_with_transcripts,
            "meetings_without_transcripts": meetings_without_transcripts,
            "transcript_success_rate": f"{(meetings_with_transcripts/total_meetings*100):.1f}%" if total_meetings > 0 else "0%",
            "recent_transcript_updates": recent_updates,
            "scheduler_status": "running" if hasattr(transcript_scheduler, 'running') and transcript_scheduler.running else "stopped"
        }
        
    except Exception as e:
        logger.error(f"Error getting transcript status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get transcript status: {str(e)}"
        )

@router.get("/transcript-content/{user_id}/{online_meeting_id}/{transcript_id}")
async def get_transcript_content_by_ids(
    user_id: str,
    online_meeting_id: str,
    transcript_id: str,
    format: Optional[str] = Query(default="text", description="Desired format hint: text|vtt|html"),
    plain: bool = Query(default=True, description="Return cleaned plain text if true"),
    db: Session = Depends(get_db),
):
    """Fetch transcript content from Graph by onlineMeetingId and transcriptId.
    Useful for debugging when you already know the IDs.
    """
    try:
        access_token = await async_get_valid_token(user_id, db)
        raw = await graph_service.get_online_meeting_transcript_content(
            access_token, online_meeting_id, transcript_id, format=format or "text"
        )
        if not raw:
            raise HTTPException(status_code=404, detail="Transcript content not available")

        content = graph_service.to_plain_text(raw) if plain else raw
        return {
            "onlineMeetingId": online_meeting_id,
            "transcriptId": transcript_id,
            "length": len(content or ""),
            "plain": plain,
            "content": content,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transcript content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/{user_id}")
async def debug_graph_api(user_id: str, days_back: int = Query(default=7), db: Session = Depends(get_db)):
    """Debug endpoint to see raw Graph API response"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        # Calculate date range (UTC timezone-aware)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        # Make direct Graph API call with detailed response
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        start_str = start_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end_str = end_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        
        url = "https://graph.microsoft.com/v1.0/me/calendarview"
        params = {
            "startDateTime": start_str,
            "endDateTime": end_str,
            "$select": "id,subject,start,end,onlineMeetingUrl,attendees,organizer,isOnlineMeeting"
        }
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            meetings = data.get("value", [])
            
            # Count different types of meetings
            total_meetings = len(meetings)
            online_meetings = [m for m in meetings if m.get("isOnlineMeeting") is True]
            # Treat any event marked as online meeting as a Teams meeting, even if join URL is missing
            teams_meetings = [
                m for m in meetings
                if (m.get("isOnlineMeeting") is True) or ("teams.microsoft.com" in (m.get("onlineMeetingUrl") or ""))
            ]
            teams_without_join_url = [m for m in teams_meetings if not m.get("onlineMeetingUrl")]
            
            return {
                "date_range": {
                    "start": start_str,
                    "end": end_str,
                    "days_back": days_back
                },
                "total_meetings": total_meetings,
                "online_meetings_count": len(online_meetings),
                "teams_meetings_count": len(teams_meetings),
                "teams_without_join_url_count": len(teams_without_join_url),
                "sample_meetings": meetings[:3],  # First 3 meetings for inspection
                "user_id": user_id
            }
            
    except HTTPException as he:
        logger.error(f"Debug HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debug failed: {str(e)}"
        )

@router.get("/meetings-without-transcripts")
async def get_meetings_without_transcripts(
    hours_back: int = Query(default=24, description="Hours back to check"),
    db: Session = Depends(get_db)
):
    """Get list of meetings without transcripts for monitoring"""
    try:
        from datetime import datetime, timezone, timedelta
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        meetings = db.query(MeetingRaw).filter(
            MeetingRaw.date >= cutoff_time.replace(tzinfo=None),
            MeetingRaw.transcript_text.in_(["Transcript not available", "", None])
        ).order_by(MeetingRaw.date.desc()).all()
        
        meeting_list = []
        for meeting in meetings:
            meeting_list.append({
                "meeting_id": meeting.meeting_id,
                "title": meeting.title,
                "date": meeting.date.isoformat(),
                "duration_minutes": meeting.duration_minutes,
                "participants_count": len(meeting.participants_json or []),
                "transcript_status": meeting.transcript_text or "No transcript",
                "created_at": meeting.created_at.isoformat(),
                "updated_at": meeting.updated_at.isoformat() if meeting.updated_at else None
            })
        
        return {
            "period": f"Last {hours_back} hours",
            "meetings_without_transcripts": len(meeting_list),
            "meetings": meeting_list
        }
        
    except Exception as e:
        logger.error(f"Error getting meetings without transcripts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get meetings without transcripts: {str(e)}"
        )

@router.get("/debug-transcript/{user_id}/{meeting_id}")
async def debug_transcript_fetching(user_id: str, meeting_id: str, db: Session = Depends(get_db)):
    """Debug endpoint to test transcript fetching for a specific meeting"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        # First, get the meeting details without expansion
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Get basic meeting details first
        basic_url = f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}"
        basic_params = {
            "$select": "id,subject,start,end,attendees,isOnlineMeeting,onlineMeetingUrl,onlineMeetingProvider,bodyPreview,body,organizer,webLink"
        }
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            basic_response = await client.get(basic_url, headers=headers, params=basic_params)
            basic_response.raise_for_status()
            basic_meeting = basic_response.json()
            
            debug_info = {
                "meeting_id": meeting_id,
                "subject": basic_meeting.get("subject"),
                "isOnlineMeeting": basic_meeting.get("isOnlineMeeting"),
                "onlineMeetingUrl": basic_meeting.get("onlineMeetingUrl"),
                "meetingType": basic_meeting.get("meetingType"),
                "allowNewTimeProposals": basic_meeting.get("allowNewTimeProposals"),
                "responseStatus": basic_meeting.get("responseStatus"),
                "showAs": basic_meeting.get("showAs"),
                "onlineMeetingProvider": basic_meeting.get("onlineMeetingProvider"),
                "organizer": basic_meeting.get("organizer")
            }
            # Resolve onlineMeeting without $expand using our fallbacks
            try:
                # Parse start/end and participants from the basic event
                def parse_dt(info: dict):
                    raw = ((info or {}).get("dateTime") or "").replace("Z", "+00:00")
                    return datetime.fromisoformat(raw) if raw else None
                start_dt = parse_dt(basic_meeting.get("start"))
                end_dt = parse_dt(basic_meeting.get("end")) or (start_dt + timedelta(hours=1) if start_dt else None)
                participants = basic_meeting.get("attendees") or []

                # Try joinUrl lookup first
                online_meeting_id = None
                # Prefer explicit onlineMeetingUrl; if missing, try to extract from body/bodyPreview
                join_url = basic_meeting.get("onlineMeetingUrl")
                if not join_url:
                    body_html = ((basic_meeting.get("body") or {}).get("content") or "")
                    body_preview = basic_meeting.get("bodyPreview") or ""
                    # Look for a Teams join link in HTML or preview text
                    pattern = re.compile(r"https?://teams\.microsoft\.com/[^'\"\s<>]+", re.IGNORECASE)
                    m = pattern.findall(body_html) or pattern.findall(body_preview)
                    if m:
                        join_url = m[0]
                        debug_info["joinUrl_from_body"] = join_url
                if join_url:
                    try:
                        om = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                        if isinstance(om, dict):
                            online_meeting_id = om.get("id")
                            debug_info["onlineMeetingId_via_joinUrl"] = online_meeting_id
                    except Exception as e:
                        debug_info["joinUrl_lookup_error"] = str(e)

                # Fallback to time/participants
                if not online_meeting_id and start_dt and end_dt:
                    try:
                        emails = []
                        for p in participants:
                            if isinstance(p, dict) and "emailAddress" in p:
                                ea = p["emailAddress"]
                                emails.append(ea.get("address") if isinstance(ea, dict) else ea)
                        om = await graph_service.find_online_meeting_by_time_and_participants(access_token, start_dt, end_dt, [e for e in emails if e])
                        if isinstance(om, dict):
                            online_meeting_id = om.get("id")
                            debug_info["onlineMeetingId_via_fallback"] = online_meeting_id
                    except Exception as e:
                        debug_info["time_participants_lookup_error"] = str(e)

                # If we have an onlineMeeting id, list transcripts using service (with pagination)
                if online_meeting_id:
                    transcripts = await graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    debug_info["onlineMeetingId"] = online_meeting_id
                    debug_info["transcripts_count"] = len(transcripts)
                    debug_info["transcripts"] = transcripts
                else:
                    # As a last resort, search Teams meetings directly and try again
                    try:
                        if start_dt and end_dt:
                            direct = await graph_service.search_teams_meetings_directly(access_token, start_dt, end_dt, participants)
                            if isinstance(direct, dict) and direct.get("id"):
                                online_meeting_id = direct.get("id")
                                debug_info["onlineMeetingId_via_direct_search"] = online_meeting_id
                                transcripts = await graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                                debug_info["onlineMeetingId"] = online_meeting_id
                                debug_info["transcripts_count"] = len(transcripts)
                                debug_info["transcripts"] = transcripts
                            else:
                                debug_info["transcripts_error"] = "Could not resolve onlineMeeting ID"
                        else:
                            debug_info["transcripts_error"] = "Could not resolve onlineMeeting ID (missing event times)"
                    except Exception as e:
                        debug_info["direct_search_error"] = str(e)
            except Exception as e:
                debug_info["resolution_error"] = str(e)

            return debug_info
            
    except HTTPException as he:
        logger.error(f"Debug transcript HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Debug transcript error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debug transcript failed: {str(e)}"
        )

@router.post("/resync/{meeting_id}")
async def resync_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """Force re-sync a specific meeting to retry transcript fetching"""
    try:
        # Get the existing meeting
        existing_meeting = db.query(MeetingRaw).filter(
            MeetingRaw.meeting_id == meeting_id
        ).first()
        
        if not existing_meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found"
            )
        
        # Get user ID from the meeting (we'll need to determine this)
        # For now, let's assume we can get it from the first user in the database
        user = db.query(UserTokens).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user found in database"
            )
        
        user_id = user.user_id
        access_token = await async_get_valid_token(user_id, db)
        
        # Get the meeting details from Graph API
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}"
        params = {
            "$select": "id,subject,start,end,attendees,isOnlineMeeting,onlineMeetingUrl,onlineMeeting"
        }
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            meeting = response.json()
        
        # Extract meeting data
        title = meeting.get("subject", "Untitled Meeting")
        
        # Parse datetime
        def parse_graph_dt(info: dict) -> datetime:
            if not isinstance(info, dict):
                raise ValueError("Invalid datetime info")
            raw = (info.get("dateTime") or "").replace("Z", "+00:00")
            if not raw:
                raise ValueError("Missing dateTime")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                tz_name = (info.get("timeZone") or "").upper()
                if tz_name in ("UTC", "Z"):
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    try:
                        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                    except Exception:
                        dt = dt.replace(tzinfo=timezone.utc)
            return dt

        start_dt = parse_graph_dt(meeting.get("start") or {})
        end_dt = parse_graph_dt(meeting.get("end") or {})
        start_time = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
        end_time = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        # Get participants
        participants = meeting.get("attendees", [])
        
        # Try to fetch transcript with all fallback methods
        transcript_text = ""
        try:
            # NEW APPROACH: Try direct Teams transcript fetching first
            logger.info(f"Attempting direct Teams transcript fetch for meeting {meeting_id}")
            try:
                # Calculate end time if not provided
                end_time = meeting.get("end", {}).get("dateTime")
                if end_time:
                    end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                else:
                    # Default to 1 hour duration if end time not available
                    end_time = start_time + timedelta(hours=1)
                
                # Extract participant emails for matching
                participant_emails = []
                for p in participants:
                    if isinstance(p, dict) and "emailAddress" in p:
                        email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                        if email:
                            participant_emails.append(email)
                    elif isinstance(p, str):
                        participant_emails.append(p)
                
                if participant_emails:
                    direct_transcript = await graph_service.fetch_teams_transcript_directly(
                        access_token, title, start_time, end_time, participant_emails
                    )
                    if direct_transcript:
                        transcript_text = direct_transcript
                        logger.info(f"Successfully retrieved transcript directly from Teams for {meeting_id} ({len(transcript_text)} chars)")
                    else:
                        logger.info(f"Direct Teams transcript fetch failed for {meeting_id}, trying fallback methods")
                else:
                    logger.warning(f"No participant emails available for direct Teams transcript fetch for {meeting_id}")
            except Exception as direct_err:
                logger.warning(f"Direct Teams transcript fetch failed for {meeting_id}: {direct_err}")
            
            # FALLBACK: Original methods if direct fetch failed
            if not transcript_text:
                logger.info(f"Trying fallback transcript methods for {meeting_id}")
                
                # Try to get onlineMeeting from the calendar event itself
                online_meeting = meeting.get("onlineMeeting")
                online_meeting_id = None
                
                if online_meeting and isinstance(online_meeting, dict):
                    # Get the join URL from the onlineMeeting object
                    join_url = online_meeting.get("joinUrl")
                    logger.info(f"Meeting {meeting_id} has onlineMeeting object with join URL: {join_url}")
                    
                    if join_url:
                        logger.info(f"Attempting join URL lookup for {meeting_id}")
                        online_meeting_obj = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                        if isinstance(online_meeting_obj, dict):
                            online_meeting_id = online_meeting_obj.get("id")
                            logger.info(f"Found onlineMeeting ID via join URL: {online_meeting_id}")
                        else:
                            logger.warning(f"Join URL lookup returned no results for {meeting_id}")
                    else:
                        logger.warning(f"onlineMeeting object exists but no joinUrl for {meeting_id}")
                else:
                    # Fallback to the old onlineMeetingUrl field
                    join_url = meeting.get("onlineMeetingUrl")
                    logger.info(f"Meeting {meeting_id} onlineMeetingUrl: {join_url}")
                    
                    if join_url:
                        logger.info(f"Attempting join URL lookup for {meeting_id}")
                        online_meeting_obj = await graph_service.find_online_meeting_by_join_url(access_token, join_url)
                        if isinstance(online_meeting_obj, dict):
                            online_meeting_id = online_meeting_obj.get("id")
                            logger.info(f"Found onlineMeeting ID via join URL: {online_meeting_id}")
                        else:
                            logger.warning(f"Join URL lookup returned no results for {meeting_id}")
                
                # Try time/participants fallback since event expansion doesn't work
                if not online_meeting_id:
                    logger.info(f"Trying time/participants fallback for {meeting_id}")
                    try:
                        # Calculate end time if not provided
                        end_time = meeting.get("end", {}).get("dateTime")
                        if end_time:
                            end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        else:
                            # Default to 1 hour duration if end time not available
                            end_time = start_time + timedelta(hours=1)
                        
                        # Extract participant emails for matching
                        participant_emails = []
                        for p in participants:
                            if isinstance(p, dict) and "emailAddress" in p:
                                email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                                if email:
                                    participant_emails.append(email)
                            elif isinstance(p, str):
                                participant_emails.append(p)
                        
                        if participant_emails:
                            online_meeting = await graph_service.find_online_meeting_by_time_and_participants(
                                access_token, start_time, end_time, participant_emails
                            )
                            if isinstance(online_meeting, dict):
                                online_meeting_id = online_meeting.get("id")
                                if online_meeting_id:
                                    logger.info(f"Resolved onlineMeeting via time/participants fallback for event {meeting_id}: {online_meeting_id}")
                                else:
                                    logger.warning(f"Time/participants fallback returned dict but no ID for {meeting_id}")
                            else:
                                logger.warning(f"Time/participants fallback returned no onlineMeeting for {meeting_id}")
                        else:
                            logger.warning(f"No participant emails available for time/participants fallback for {meeting_id}")
                    except Exception as tp_err:
                        logger.warning(f"Time/participants fallback failed for {meeting_id}: {tp_err}")
                
                # Third fallback: search Teams meetings directly
                if not online_meeting_id:
                    logger.info(f"Trying direct Teams meeting search for {meeting_id}")
                    try:
                        # Calculate end time if not provided
                        end_time = meeting.get("end", {}).get("dateTime")
                        if end_time:
                            end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        else:
                            # Default to 1 hour duration if end time not available
                            end_time = start_time + timedelta(hours=1)
                        
                        # Extract participant emails for matching
                        participant_emails = []
                        for p in participants:
                            if isinstance(p, dict) and "emailAddress" in p:
                                email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                                if email:
                                    participant_emails.append(email)
                            elif isinstance(p, str):
                                participant_emails.append(p)
                        
                        if participant_emails:
                            online_meeting = await graph_service.search_teams_meetings_directly(
                                access_token, start_time, end_time, participant_emails
                            )
                            if isinstance(online_meeting, dict):
                                online_meeting_id = online_meeting.get("id")
                                if online_meeting_id:
                                    logger.info(f"Resolved onlineMeeting via direct Teams search for event {meeting_id}: {online_meeting_id}")
                                else:
                                    logger.warning(f"Direct Teams search returned dict but no ID for {meeting_id}")
                            else:
                                logger.warning(f"Direct Teams search returned no onlineMeeting for {meeting_id}")
                        else:
                            logger.warning(f"No participant emails available for direct Teams search for {meeting_id}")
                    except Exception as dt_err:
                        logger.warning(f"Direct Teams search failed for {meeting_id}: {dt_err}")
                
                if online_meeting_id:
                    logger.info(f"Fetching transcripts for onlineMeeting {online_meeting_id}")
                    transcripts = await graph_service.list_online_meeting_transcripts(access_token, online_meeting_id)
                    logger.info(f"Found {len(transcripts)} transcripts for meeting {meeting_id}")
                    if transcripts:
                        # Prefer the newest transcript
                        try:
                            transcripts_sorted = sorted(transcripts, key=lambda t: t.get("createdDateTime", ""))
                        except Exception:
                            transcripts_sorted = transcripts
                        latest = transcripts_sorted[-1]
                        transcript_id = latest.get("id")
                        logger.info(f"Using transcript ID {transcript_id} for meeting {meeting_id}")
                        if transcript_id:
                            raw_content = await graph_service.get_online_meeting_transcript_content(access_token, online_meeting_id, transcript_id, format="text")
                            logger.info(f"Retrieved {len(raw_content)} chars of transcript content for {meeting_id}")
                            cleaned = graph_service.to_plain_text(raw_content)
                            transcript_text = cleaned or raw_content or ""
                    else:
                        logger.warning(f"No transcripts found for onlineMeeting {online_meeting_id}")
                else:
                    logger.warning(f"Could not resolve onlineMeeting ID for event {meeting_id}")
                    transcript_text = "Transcript not available - onlineMeeting ID not found"
            
            if not transcript_text:
                transcript_text = "Transcript not available"
                logger.warning(f"Final transcript result for {meeting_id}: empty/unavailable")
            else:
                logger.info(f"Successfully retrieved transcript for {meeting_id} ({len(transcript_text)} chars)")
                
        except Exception as e:
            logger.error(f"Could not fetch transcript for meeting {meeting_id}: {str(e)}")
            transcript_text = "Transcript not available - error occurred"
        
        # Update the existing meeting with new transcript data
        existing_meeting.transcript_text = transcript_text
        # existing_meeting.updated_at = datetime.now()  # Column doesn't exist yet
        
        db.commit()
        
        logger.info(f"Successfully re-synced meeting {meeting_id}")
        
        return {
            "meeting_id": meeting_id,
            "title": title,
            "transcript_length": len(transcript_text),
            "has_transcript": len(transcript_text) > 100,
            "transcript_preview": transcript_text[:200] + "..." if len(transcript_text) > 200 else transcript_text
        }
        
    except HTTPException as he:
        logger.error(f"Re-sync HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Re-sync error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to re-sync meeting: {str(e)}"
        )

@router.get("/diagnose/{user_id}/{meeting_id}")
async def diagnose_meeting(user_id: str, meeting_id: str, db: Session = Depends(get_db)):
    """Diagnostic endpoint to check what's available in Microsoft Graph API for a meeting"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        diagnostics = {
            "meeting_id": meeting_id,
            "graph_api_checks": {}
        }
        
        # Check 1: Basic meeting details
        try:
            basic_url = f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}"
            async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
                response = await client.get(basic_url, headers=headers)
                if response.status_code == 200:
                    meeting_data = response.json()
                    diagnostics["graph_api_checks"]["basic_meeting"] = {
                        "status": "success",
                        "subject": meeting_data.get("subject"),
                        "isOnlineMeeting": meeting_data.get("isOnlineMeeting"),
                        "onlineMeetingUrl": meeting_data.get("onlineMeetingUrl"),
                        "meetingType": meeting_data.get("meetingType"),
                        "start": meeting_data.get("start"),
                        "end": meeting_data.get("end"),
                        "attendees_count": len(meeting_data.get("attendees", []))
                    }
                else:
                    diagnostics["graph_api_checks"]["basic_meeting"] = {
                        "status": "failed",
                        "status_code": response.status_code,
                        "error": response.text
                    }
        except Exception as e:
            diagnostics["graph_api_checks"]["basic_meeting"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check 2: Online meetings in time range
        try:
            if diagnostics["graph_api_checks"]["basic_meeting"]["status"] == "success":
                meeting_data = diagnostics["graph_api_checks"]["basic_meeting"]
                start_time = meeting_data.get("start", {}).get("dateTime")
                end_time = meeting_data.get("end", {}).get("dateTime")
                
                if start_time and end_time:
                    # Convert to datetime for filtering
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    
                    # Search for online meetings in this time range
                    online_meetings_url = "https://graph.microsoft.com/beta/me/onlineMeetings"
                    start_iso = start_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    end_iso = end_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    
                    params = {
                        "$filter": f"startDateTime ge {start_iso} and endDateTime le {end_iso}"
                        # Removed $top parameter that was causing 400 error
                    }
                    
                    async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
                        response = await client.get(online_meetings_url, headers=headers, params=params)
                        if response.status_code == 200:
                            data = response.json()
                            online_meetings = data.get("value", [])
                            diagnostics["graph_api_checks"]["online_meetings_search"] = {
                                "status": "success",
                                "meetings_found": len(online_meetings),
                                "meetings": [
                                    {
                                        "id": m.get("id"),
                                        "subject": m.get("subject"),
                                        "startDateTime": m.get("startDateTime"),
                                        "endDateTime": m.get("endDateTime"),
                                        "joinWebUrl": m.get("joinWebUrl")
                                    } for m in online_meetings[:3]  # Show first 3
                                ]
                            }
                        else:
                            diagnostics["graph_api_checks"]["online_meetings_search"] = {
                                "status": "failed",
                                "status_code": response.status_code,
                                "error": response.text
                            }
                else:
                    diagnostics["graph_api_checks"]["online_meetings_search"] = {
                        "status": "skipped",
                        "reason": "No start/end time available"
                    }
        except Exception as e:
            diagnostics["graph_api_checks"]["online_meetings_search"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check 3: Try to get onlineMeeting from event (this should fail based on our earlier tests)
        try:
            expand_url = f"https://graph.microsoft.com/beta/me/events/{meeting_id}"
            expand_params = {"$expand": "onlineMeeting"}
            
            async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
                response = await client.get(expand_url, headers=headers, params=expand_params)
                diagnostics["graph_api_checks"]["event_expansion"] = {
                    "status": "failed" if response.status_code >= 400 else "success",
                    "status_code": response.status_code,
                    "response": response.text if response.status_code >= 400 else "Success"
                }
        except Exception as e:
            diagnostics["graph_api_checks"]["event_expansion"] = {
                "status": "error",
                "error": str(e)
            }
        
        return diagnostics
        
    except HTTPException as he:
        logger.error(f"Diagnose HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Diagnose error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnose failed: {str(e)}"
        )

@router.get("/test-teams-meetings/{user_id}")
async def test_teams_meetings(user_id: str, db: Session = Depends(get_db)):
    """Test endpoint to see what Teams meetings are available directly"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Try to get all online meetings
        url = "https://graph.microsoft.com/beta/me/onlineMeetings"
        params = {
            "$filter": "startDateTime ge 2025-08-01T00:00:00Z"  # Get meetings from August 1st onwards
        }
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                meetings = data.get("value", [])
                
                # Get basic info about each meeting
                meeting_info = []
                for meeting in meetings[:10]:  # Show first 10
                    meeting_info.append({
                        "id": meeting.get("id"),
                        "subject": meeting.get("subject"),
                        "startDateTime": meeting.get("startDateTime"),
                        "endDateTime": meeting.get("endDateTime"),
                        "joinWebUrl": meeting.get("joinWebUrl"),
                        "participants_count": len(meeting.get("participants", {}).get("attendees", [])),
                        "participants": [
                            {
                                "upn": p.get("upn"),
                                "role": p.get("role")
                            } for p in meeting.get("participants", {}).get("attendees", [])[:3]  # Show first 3
                        ]
                    })
                
                return {
                    "status": "success",
                    "total_meetings": len(meetings),
                    "meetings": meeting_info
                }
            else:
                return {
                    "status": "failed",
                    "status_code": response.status_code,
                    "error": response.text
                }
                
    except HTTPException as he:
        logger.error(f"Test Teams meetings HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Test Teams meetings error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test Teams meetings failed: {str(e)}"
        )

@router.put("/update-transcript/{meeting_id}")
async def update_meeting_transcript(meeting_id: str, transcript: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Manually update a meeting's transcript"""
    try:
        # Get the existing meeting
        existing_meeting = db.query(MeetingRaw).filter(
            MeetingRaw.meeting_id == meeting_id
        ).first()
        
        if not existing_meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found"
            )
        
        # Update the transcript
        existing_meeting.transcript_text = transcript
        
        db.commit()
        
        logger.info(f"Successfully updated transcript for meeting {meeting_id}")
        
        return {
            "meeting_id": meeting_id,
            "title": existing_meeting.title,
            "transcript_length": len(transcript),
            "has_transcript": len(transcript) > 100,
            "message": "Transcript updated successfully"
        }
        
    except HTTPException as he:
        logger.error(f"Update transcript HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Update transcript error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update transcript: {str(e)}"
        )

@router.get("/test-direct-transcript/{user_id}/{meeting_id}")
async def test_direct_transcript_fetch(user_id: str, meeting_id: str, db: Session = Depends(get_db)):
    """Test endpoint to directly test the new Teams transcript fetching method"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        # Get the meeting details from Graph API
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}"
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            meeting = response.json()
        
        # Extract meeting data
        title = meeting.get("subject", "Untitled Meeting")
        
        # Parse datetime
        def parse_graph_dt(info: dict) -> datetime:
            if not isinstance(info, dict):
                raise ValueError("Invalid datetime info")
            raw = (info.get("dateTime") or "").replace("Z", "+00:00")
            if not raw:
                raise ValueError("Missing dateTime")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                tz_name = (info.get("timeZone") or "").upper()
                if tz_name in ("UTC", "Z"):
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    try:
                        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                    except Exception:
                        dt = dt.replace(tzinfo=timezone.utc)
            return dt

        start_dt = parse_graph_dt(meeting.get("start") or {})
        end_dt = parse_graph_dt(meeting.get("end") or {})
        start_time = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
        end_time = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        # Get participants
        participants = meeting.get("attendees", [])
        
        # Test the direct Teams transcript fetching
        logger.info(f"Testing direct Teams transcript fetch for meeting: {title}")
        logger.info(f"Start time: {start_time}, End time: {end_time}")
        logger.info(f"Participants: {participants}")
        
        # Extract participant emails
        participant_emails = []
        for p in participants:
            if isinstance(p, dict) and "emailAddress" in p:
                email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                if email:
                    participant_emails.append(email)
            elif isinstance(p, str):
                participant_emails.append(p)
        
        logger.info(f"Participant emails: {participant_emails}")
        
        # Call the direct transcript fetching method
        direct_transcript = await graph_service.fetch_teams_transcript_directly(
            access_token, title, start_time, end_time, participant_emails
        )
        
        if direct_transcript:
            logger.info(f"SUCCESS: Retrieved transcript directly from Teams ({len(direct_transcript)} characters)")
            return {
                "status": "success",
                "meeting_id": meeting_id,
                "title": title,
                "transcript_length": len(direct_transcript),
                "transcript_preview": direct_transcript[:200] + "..." if len(direct_transcript) > 200 else direct_transcript,
                "message": "Transcript successfully retrieved directly from Teams"
            }
        else:
            logger.warning("FAILED: Could not retrieve transcript directly from Teams")
            return {
                "status": "failed",
                "meeting_id": meeting_id,
                "title": title,
                "message": "Direct Teams transcript fetch failed",
                "debug_info": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "participant_emails": participant_emails,
                    "participants_count": len(participants)
                }
            }
        
    except HTTPException as he:
        logger.error(f"Test direct transcript HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Test direct transcript error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test direct transcript failed: {str(e)}"
        )

@router.get("/debug-token/{user_id}")
async def debug_token(user_id: str, db: Session = Depends(get_db)):
    """Debug endpoint to get access token for testing"""
    try:
        access_token = await async_get_valid_token(user_id, db)
        return {"access_token": access_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/test-teams-access/{user_id}")
async def test_teams_access(user_id: str, db: Session = Depends(get_db)):
    """Test endpoint to check if we can access Teams meetings at all"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Try to access calendar events with Teams meetings
        # The /onlineMeetings endpoint doesn't support time filtering
        # Instead, we get calendar events and expand onlineMeeting property
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
        end_time = (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        
        url = f"https://graph.microsoft.com/v1.0/me/calendarView"
        params = {
            "startDateTime": start_time,
            "endDateTime": end_time
        }
        
        async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                meetings = data.get("value", [])
                
                # Filter for Teams meetings and show their properties
                teams_meetings = []
                for m in meetings:
                    if m.get("isOnlineMeeting") or m.get("onlineMeetingUrl"):
                        teams_meetings.append({
                            "id": m.get("id"),
                            "subject": m.get("subject"),
                            "start": m.get("start"),
                            "end": m.get("end"),
                            "isOnlineMeeting": m.get("isOnlineMeeting"),
                            "onlineMeetingUrl": m.get("onlineMeetingUrl"),
                            "onlineMeeting": m.get("onlineMeeting"),
                            "attendees_count": len(m.get("attendees", []))
                        })
                
                return {
                    "status": "success",
                    "total_events": len(meetings),
                    "teams_meetings_count": len(teams_meetings),
                    "sample_meetings": teams_meetings[:3],  # Show first 3 Teams meetings
                    "message": f"Found {len(teams_meetings)} Teams meetings out of {len(meetings)} calendar events."
                }
            else:
                return {
                    "status": "failed",
                    "status_code": response.status_code,
                    "error": response.text,
                    "message": f"Failed to access Teams meetings endpoint. Status: {response.status_code}"
                }
                
    except HTTPException as he:
        logger.error(f"Test Teams access HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Test Teams access error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test Teams access failed: {str(e)}"
        )

@router.get("/test-alternative-endpoints/{user_id}")
async def test_alternative_endpoints(user_id: str, db: Session = Depends(get_db)):
    """Test endpoint to check for alternative Microsoft Graph endpoints that might work for Teams meetings"""
    try:
        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Test various alternative endpoints
        endpoints_to_test = [
            "https://graph.microsoft.com/v1.0/me/calendarView",
            "https://graph.microsoft.com/v1.0/me/events",
            "https://graph.microsoft.com/beta/me/events",
            "https://graph.microsoft.com/v1.0/me/joinedTeams",
            "https://graph.microsoft.com/v1.0/me/teamwork/installedApps",
            "https://graph.microsoft.com/v1.0/communications/callRecords",
            "https://graph.microsoft.com/beta/communications/callRecords"
        ]
        
        results = {}
        
        for endpoint in endpoints_to_test:
            try:
                async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
                    response = await client.get(endpoint, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "value" in data:
                            results[endpoint] = {
                                "status": "success",
                                "items_count": len(data.get("value", [])),
                                "sample_data": str(data.get("value", [])[:200]) + "..." if len(str(data.get("value", []))) > 200 else str(data.get("value", []))
                            }
                        else:
                            results[endpoint] = {
                                "status": "success",
                                "data": str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                            }
                    else:
                        results[endpoint] = {
                            "status": "failed",
                            "status_code": response.status_code,
                            "error": response.text[:200] + "..." if len(response.text) > 200 else response.text
                        }
                        
            except Exception as e:
                results[endpoint] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "status": "completed",
            "endpoints_tested": len(endpoints_to_test),
            "results": results
        }
        
    except HTTPException as he:
        logger.error(f"Test alternative endpoints HTTP error: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Test alternative endpoints error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test alternative endpoints failed: {str(e)}"
        )

# Moved to the end to avoid shadowing static routes like /transcript-status
@router.get("/{meeting_id}")
async def get_meeting_details(meeting_id: str, db: Session = Depends(get_db)):
    """Get detailed meeting information"""
    meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Enrich participants with names (Graph name or HRData fallback)
    participants_raw = meeting.participants_json or []
    participants = []
    for p in (participants_raw if isinstance(participants_raw, list) else []):
        email = None
        name = None
        p_type = None
        if isinstance(p, dict):
            email_addr = (p.get("emailAddress") or {}) if isinstance(p.get("emailAddress"), dict) else {}
            email = email_addr.get("address")
            name = email_addr.get("name")
            p_type = p.get("type")
        elif isinstance(p, str):
            email = p
        if email and not name:
            hr = db.query(HRData).filter(HRData.user_email == email).first()
            if hr and hr.display_name:
                name = hr.display_name
        participants.append({
            "email": email,
            "name": name or email,
            "type": p_type
        })
    
    # Get MOM if exists
    mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
    mom_data = None
    if mom:
        mom_data = {
            "meeting_title": mom.meeting_title,
            "date": mom.date.isoformat(),
            "agenda": mom.agenda,
            "key_decisions": mom.key_decisions,
            "action_items": mom.action_items,
            "follow_up_points": mom.follow_up_points,
            "created_at": mom.created_at.isoformat()
        }
    
    return {
        "meeting_id": meeting.meeting_id,
        "title": meeting.title,
        "date": meeting.date.isoformat(),
        "duration_minutes": meeting.duration_minutes,
        "participants": participants,
        "transcript": meeting.transcript_text,
        "mom": mom_data,
        "created_at": meeting.created_at.isoformat()
    }