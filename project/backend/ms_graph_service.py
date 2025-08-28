import httpx
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
import json
import re
import asyncio

load_dotenv(override=True)
logger = logging.getLogger(__name__)

class MSGraphService:
    def __init__(self):
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID")
        self.redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
        
        # Check if Microsoft OAuth is properly configured
        self.is_configured = (
            bool(self.client_id)
            and bool(self.client_secret)
            and bool(self.tenant_id)
            and self.client_id not in ("placeholder_client_id", "your_client_id_here")
            and self.client_secret not in ("placeholder_client_secret", "your_client_secret_here")
            and self.tenant_id not in ("placeholder_tenant_id", "your_tenant_id_here")
        )
        
        if self.is_configured:
            self.app = ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}"
            )
        else:
            self.app = None
            logger.warning("Microsoft OAuth not configured - using placeholder values")
        
        # Use delegated permission scopes (AAD v2). Do NOT include reserved OIDC scopes
        # (openid, profile, offline_access); MSAL adds them automatically.
        # For Teams meeting transcripts: OnlineMeetingTranscript.Read.All is required (typically needs admin consent).
        self.scopes = [
            "User.Read",
            "User.ReadBasic.All",
            "Calendars.Read",
            "OnlineMeetings.Read",
            "Tasks.ReadWrite",
            "Group.ReadWrite.All",
            "Mail.Send",
            "OnlineMeetingTranscript.Read.All",
            "OnlineMeetingRecording.Read.All",
            "Files.Read.All",
            "Sites.Read.All",
        ]

        # Configurable HTTP timeouts to avoid hanging requests
        # Defaults are conservative to balance reliability and latency
        try:
            connect_t = float(os.getenv("GRAPH_HTTP_CONNECT_TIMEOUT", "5"))
        except Exception:
            connect_t = 5.0
        try:
            read_t = float(os.getenv("GRAPH_HTTP_READ_TIMEOUT", "30"))
        except Exception:
            read_t = 30.0
        try:
            write_t = float(os.getenv("GRAPH_HTTP_WRITE_TIMEOUT", "30"))
        except Exception:
            write_t = 30.0
        try:
            pool_t = float(os.getenv("GRAPH_HTTP_POOL_TIMEOUT", "5"))
        except Exception:
            pool_t = 5.0

        self.http_timeout = httpx.Timeout(
            connect=connect_t,
            read=read_t,
            write=write_t,
            pool=pool_t,
        )

    def get_authorization_url(self) -> str:
        """Get Microsoft OAuth2 authorization URL"""
        if not self.is_configured:
            raise Exception("Microsoft OAuth not configured. Please set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_TENANT_ID in .env file")
        
        # Use configured Graph scopes; MSAL adds OIDC reserved scopes automatically.
        # Filter out any reserved scopes if present.
        reserved = {"openid", "profile", "offline_access"}
        scopes = [s for s in self.scopes if s not in reserved]
        logger.info(f"Generating auth URL with redirect_uri={self.redirect_uri} and scopes={scopes}")

        auth_url = self.app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=self.redirect_uri
        )
        return auth_url

    async def get_token_from_code(self, authorization_code: str) -> Dict:
        """Exchange authorization code for access token"""
        if not self.is_configured:
            raise Exception("Microsoft OAuth not configured")
        
        try:
            # Use same configured scopes as authorization URL; filter reserved OIDC scopes
            reserved = {"openid", "profile", "offline_access"}
            scopes = [s for s in self.scopes if s not in reserved]
            
            result = self.app.acquire_token_by_authorization_code(
                authorization_code,
                scopes=scopes,
                redirect_uri=self.redirect_uri
            )
            
            if "access_token" in result:
                logger.info("Successfully obtained access token")
                return result
            else:
                logger.error(f"Failed to get token: {result.get('error_description')}")
                raise Exception(f"Token acquisition failed: {result.get('error_description')}")
                
        except Exception as e:
            logger.error(f"Error getting token: {str(e)}")
            raise

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """Refresh access token using refresh token"""
        if not self.is_configured or not self.app:
            raise Exception("Microsoft OAuth not configured")
        try:
            # Use same configured scopes as authorization URL; filter reserved OIDC scopes
            reserved = {"openid", "profile", "offline_access"}
            scopes = [s for s in self.scopes if s not in reserved]
            
            result = self.app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)
            
            if "access_token" in result:
                logger.info("Successfully refreshed access token")
                return result
            else:
                logger.error(f"Failed to refresh token: {result.get('error_description')}")
                raise Exception(f"Token refresh failed: {result.get('error_description')}")
                
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            raise

    async def get_user_meetings(self, access_token: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Fetch user meetings from Calendar API"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="UTC"'
        }
        
        # Convert to UTC and format with Z suffix for Graph API
        start_str = start_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end_str = end_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        
        logger.info(f"Querying meetings from {start_str} to {end_str}")
        
        url = f"https://graph.microsoft.com/v1.0/me/calendarView"
        params = {
            "startDateTime": start_str,
            "endDateTime": end_str,
            "$select": "id,subject,start,end,onlineMeetingUrl,attendees,organizer,isOnlineMeeting"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                meetings: List[Dict] = []
                page = 1
                while True:
                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    batch = data.get("value", [])
                    meetings.extend(batch)
                    logger.info(f"calendarView page {page}: fetched {len(batch)} events (cumulative {len(meetings)})")
                    next_link = data.get("@odata.nextLink")
                    if not next_link:
                        break
                    # Follow pagination link; when nextLink is absolute, omit params
                    url = next_link
                    params = None
                    page += 1
                
                logger.info(f"Graph API returned {len(meetings)} total calendar events across {page} page(s)")
                
                # TEMPORARY: Include ALL meetings to debug filtering issue
                logger.info(f"DEBUG: Including ALL {len(meetings)} meetings (no filtering)")
                
                # Log first few meetings for debugging
                for i, meeting in enumerate(meetings[:5]):
                    logger.info(f"Meeting {i+1}: '{meeting.get('subject', 'No subject')}' - isOnline: {meeting.get('isOnlineMeeting')}, hasUrl: {bool(meeting.get('onlineMeetingUrl'))}, attendees: {len(meeting.get('attendees', []))}")
                
                return meetings  # Return ALL meetings temporarily
                
        except httpx.HTTPError as e:
            # Log response details if available to aid debugging
            resp_text = ""
            status_code = None
            try:
                if hasattr(e, "response") and e.response is not None:
                    status_code = e.response.status_code
                    resp_text = e.response.text
            except Exception:
                pass
            logger.error(
                f"HTTP error getting meetings: {str(e)}; "
                f"status={status_code}, response={resp_text}"
            )
            raise
        except Exception as e:
            logger.error(f"Error getting meetings: {str(e)}")
            raise

    async def get_online_meeting(self, access_token: str, meeting_id: str) -> Dict:
        """Get online meeting details"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/me/onlineMeetings/{meeting_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                meeting_data = response.json()
                logger.info(f"Retrieved online meeting data for {meeting_id}")
                return meeting_data
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting online meeting: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting online meeting: {str(e)}")
            raise

    async def find_online_meeting_by_join_url(self, access_token: str, join_url: str) -> Optional[Dict]:
        """Find an online meeting by its join (Teams) URL using beta endpoint.
        Returns the meeting object if found, else None.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        # Using /beta and filter by joinWebUrl
        url = "https://graph.microsoft.com/beta/me/onlineMeetings"
        # OData string literal escaping: single quotes doubled
        sanitized = join_url.replace("'", "''") if isinstance(join_url, str) else ""
        params = {"$filter": f"joinWebUrl eq '{sanitized}'"}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                # 403/404 are common when permission or meeting not found
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                items = data.get("value", [])
                return items[0] if items else None
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error finding online meeting by join url: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error finding online meeting by join url: {e}")
            return None

    async def find_online_meeting_by_time_and_participants(self, access_token: str, start_time: datetime, end_time: datetime, participants: List[str]) -> Optional[Dict]:
        """Find an online meeting by matching time and participants.
        This is a fallback when join URL and event expansion don't work.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = "https://graph.microsoft.com/beta/me/onlineMeetings"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                # Page through all available meetings
                items: List[Dict] = []
                next_url = url
                page = 1
                while next_url:
                    resp = await client.get(next_url, headers=headers)
                    if resp.status_code == 404 and page == 1:
                        logger.warning("No online meetings collection available (404)")
                        return None
                    resp.raise_for_status()
                    data = resp.json()
                    batch = data.get("value", [])
                    items.extend(batch)
                    next_url = data.get("@odata.nextLink")
                    logger.info(f"onlineMeetings page {page}: fetched {len(batch)} (cumulative {len(items)})")
                    page += 1

                # Local time-overlap filter
                def parse_dt(s: Optional[str]) -> Optional[datetime]:
                    if not s or not isinstance(s, str):
                        return None
                    try:
                        return datetime.fromisoformat(s.replace("Z", "+00:00"))
                    except Exception:
                        return None

                matching_time: List[Dict] = []
                for m in items:
                    mt_start = parse_dt(m.get("startDateTime"))
                    mt_end = parse_dt(m.get("endDateTime"))
                    if mt_start and mt_end and (mt_start <= end_time and mt_end >= start_time):
                        matching_time.append(m)

                logger.info(f"onlineMeetings time-overlap: {len(matching_time)} candidates")

                # Normalize input participants to emails
                participant_emails = set()
                for p in participants:
                    if isinstance(p, dict) and "emailAddress" in p:
                        email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                        if email:
                            participant_emails.add(email.lower())
                    elif isinstance(p, str):
                        participant_emails.add(p.lower())

                # Score by UPN overlap
                best_match = None
                best_score = 0
                for m in matching_time:
                    attendees = (m.get("participants") or {}).get("attendees", [])
                    upns = { (a.get("upn") or "").lower() for a in attendees if isinstance(a, dict) }
                    score = len(participant_emails.intersection(upns))
                    if score > best_score:
                        best_score = score
                        best_match = m

                # NEW: Fallback to best time match if no participant match
                if best_score == 0 and len(matching_time) > 0:
                    return max(matching_time, key=lambda m: m.get('duration', 0))

                if best_match and best_score > 0:
                    logger.info(f"Found matching online meeting with {best_score} common participants")
                    return best_match
                try:
                    logger.warning(
                        f"No online meeting found with matching participants in time-overlap set; candidates={len(matching_time)}, best_score={best_score}"
                    )
                except Exception:
                    logger.warning("No online meeting found with matching participants in time-overlap set")
                return None
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error finding online meeting by time/participants: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error finding online meeting by time/participants: {e}")
            return None

    async def search_teams_meetings_directly(self, access_token: str, start_time: datetime, end_time: datetime, participants: List[str]) -> Optional[Dict]:
        """Search for Teams meetings directly using the Teams endpoint.
        This bypasses the calendar event issue and looks directly in Teams.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Try to get Teams meetings directly
        url = "https://graph.microsoft.com/beta/me/onlineMeetings"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                # First, try to get all meetings without time filter
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    all_meetings = data.get("value", [])
                    
                    logger.info(f"Found {len(all_meetings)} total online meetings")
                    
                    # Filter by time manually since the API filter isn't working
                    matching_meetings = []
                    for meeting in all_meetings:
                        meeting_start = meeting.get("startDateTime")
                        meeting_end = meeting.get("endDateTime")
                        
                        if meeting_start and meeting_end:
                            try:
                                # Parse meeting times
                                mt_start = datetime.fromisoformat(meeting_start.replace("Z", "+00:00"))
                                mt_end = datetime.fromisoformat(meeting_end.replace("Z", "+00:00"))
                                
                                # Check if times overlap
                                if (mt_start <= end_time and mt_end >= start_time):
                                    matching_meetings.append(meeting)
                            except Exception:
                                continue
                    
                    logger.info(f"Found {len(matching_meetings)} meetings in time range")
                    
                    # Now try to match by participants
                    participant_emails = set()
                    for p in participants:
                        if isinstance(p, dict) and "emailAddress" in p:
                            email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                            if email:
                                participant_emails.add(email.lower())
                        elif isinstance(p, str):
                            participant_emails.add(p.lower())
                    
                    # Find best match
                    best_match = None
                    best_score = 0
                    
                    for meeting in matching_meetings:
                        meeting_participants = meeting.get("participants", {}).get("attendees", [])
                        meeting_emails = set()
                        
                        for mp in meeting_participants:
                            if isinstance(mp, dict) and "upn" in mp:
                                meeting_emails.add(mp["upn"].lower())
                        
                        # Calculate match score
                        common_emails = participant_emails.intersection(meeting_emails)
                        score = len(common_emails)
                        
                        if score > best_score:
                            best_score = score
                            best_match = meeting
                    
                    if best_match and best_score > 0:
                        logger.info(f"Found matching Teams meeting with {best_score} common participants")
                        return best_match
                    else:
                        logger.warning(f"No Teams meeting found with matching participants")
                        return None
                        
                else:
                    logger.warning(f"Failed to get online meetings: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.warning(f"Error searching Teams meetings directly: {e}")
            return None

    async def fetch_teams_transcript_directly(self, access_token: str, meeting_title: str, start_time: datetime, end_time: datetime, participants: List[str]) -> Optional[str]:
        """Fetch Teams meeting transcript directly by searching through Teams meetings.
        This is the main method that should work for getting transcripts from Teams.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            # NOTE: Microsoft Graph API requires a filter for /onlineMeetings endpoint
            # We cannot get all meetings without a filter, so we need to use a different approach
            
            # Step 1: Try to find Teams meeting by searching with a time-based filter
            url = "https://graph.microsoft.com/beta/me/onlineMeetings"
            
            # Create a time filter that covers our meeting time
            # Use a wider range to ensure we catch the meeting
            search_start = start_time - timedelta(hours=2)  # 2 hours before
            search_end = end_time + timedelta(hours=2)     # 2 hours after
            
            start_iso = self._iso_utc(search_start)
            end_iso = self._iso_utc(search_end)
            
            # The /onlineMeetings endpoint doesn't support time-based filtering
            # We need to use calendar events instead
            # First, try to get calendar events with online meeting info
            calendar_url = "https://graph.microsoft.com/v1.0/me/calendarView"
            calendar_params = {
                "startDateTime": start_iso,
                "endDateTime": end_iso,
                "$select": "id,subject,start,end,attendees,organizer,onlineMeetingUrl,isOnlineMeeting"
            }
            
            calendar_headers = dict(headers)
            calendar_headers["Prefer"] = 'outlook.timezone="UTC"'
            
            best_match = None
            best_score = 0
            
            try:
                async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                    # Try to get calendar events with Teams meetings
                    logger.info(f"Fetching calendar events from {start_iso} to {end_iso}")
                    response = await client.get(calendar_url, headers=calendar_headers, params=calendar_params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        events = data.get("value", [])
                        logger.info(f"Found {len(events)} calendar events with Teams meetings")
                        
                        # Score each event based on title, time, and participants
                        for event in events:
                            score = 0
                                
                            # Check title similarity
                            event_subject = event.get("subject", "").lower()
                            if meeting_title.lower() in event_subject or event_subject in meeting_title.lower():
                                score += 3
                            
                            # Check time overlap
                            event_start = event.get("start", {}).get("dateTime")
                            event_end = event.get("end", {}).get("dateTime")
                            if event_start and event_end:
                                try:
                                    et_start = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
                                    et_end = datetime.fromisoformat(event_end.replace("Z", "+00:00"))
                                    
                                    # Check if times overlap (within 30 minutes tolerance)
                                    tolerance = timedelta(minutes=30)
                                    if (et_start - tolerance <= end_time and et_end + tolerance >= start_time):
                                        score += 2
                                except Exception:
                                    pass
                            
                            # Check participant overlap
                            participant_emails = set()
                            for p in participants:
                                if isinstance(p, dict) and "emailAddress" in p:
                                    email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                                    if email:
                                        participant_emails.add(email.lower())
                                elif isinstance(p, str):
                                    participant_emails.add(p.lower())
                            
                            event_attendees = event.get("attendees", [])
                            event_emails = set()
                            for attendee in event_attendees:
                                if isinstance(attendee, dict) and "emailAddress" in attendee:
                                    email = attendee["emailAddress"].get("address", "")
                                    if email:
                                        event_emails.add(email.lower())
                            
                            common_emails = participant_emails.intersection(event_emails)
                            score += len(common_emails)
                            
                            if score > best_score:
                                best_score = score
                                best_match = event
                    
                    elif response.status_code == 400:
                        logger.warning(f"Calendar API request failed: {response.text}")
                    else:
                        logger.warning(f"Calendar API failed with status {response.status_code}")
                        
            except Exception as e:
                logger.warning(f"Calendar events fetch failed: {e}")
            
            if not best_match or best_score < 2:
                logger.warning(f"No suitable Teams meeting found. Best score: {best_score}")
                return None
            
            logger.info(f"Found matching calendar event: {best_match.get('subject')} with score {best_score}")

            # Toggle mock behavior via env flag
            use_mock = os.getenv("USE_MOCK_TRANSCRIPTS", "false").lower() in ("1", "true", "yes")
            if use_mock:
                logger.info("USE_MOCK_TRANSCRIPTS=true -> returning placeholder transcript")
                mock_transcript = (
                    f"Mock transcript for meeting: {best_match.get('subject', 'Unknown')}\n"
                    f"Meeting time: {start_time} to {end_time}\n"
                    f"Participants: {', '.join(self._participants_to_emails(participants)) if participants else 'Unknown'}\n\n"
                    f"This is a placeholder transcript. In production, actual transcript content would be fetched from Teams.\n"
                )
                return mock_transcript

            # Attempt to obtain a real onlineMeeting.id by expanding the event
            event_id = best_match.get("id")
            online_meeting_id: Optional[str] = None
            try:
                if event_id:
                    om = await self.get_online_meeting_from_event(access_token, event_id)
                    if om and isinstance(om, dict):
                        online_meeting_id = om.get("id") or om.get("meetingId")
                        logger.info(f"Expanded event onlineMeeting id: {online_meeting_id}")
            except Exception as e:
                logger.warning(f"Failed to expand event for onlineMeeting id: {e}")

            # Fallback: try extracting meeting id from join URL if present on the event
            if not online_meeting_id:
                # Prefer resolving the proper OnlineMeeting id via join URL lookup
                join_url: Optional[str] = None
                try:
                    # If we expanded the event above, try to pull join URL from that object first
                    # (property name varies between joinWebUrl and joinUrl across resources)
                    om_join_url = None
                    try:
                        om_join_url = (om or {}).get("joinWebUrl") or (om or {}).get("joinUrl")
                    except Exception:
                        om_join_url = None

                    join_url = om_join_url or best_match.get("onlineMeetingUrl")
                except Exception:
                    join_url = best_match.get("onlineMeetingUrl")

                if join_url and isinstance(join_url, str):
                    try:
                        resolved = await self.find_online_meeting_by_join_url(access_token, join_url)
                        if isinstance(resolved, dict):
                            online_meeting_id = resolved.get("id")
                            logger.info(f"Resolved onlineMeeting id via joinUrl lookup: {online_meeting_id}")
                    except Exception as e:
                        logger.warning(f"Join URL lookup failed: {e}")

                # As a last resort, attempt to extract a thread id pattern from the join URL (often not accepted by transcripts API)
                if not online_meeting_id and join_url and isinstance(join_url, str):
                    try:
                        import urllib.parse, re
                        decoded_url = urllib.parse.unquote(join_url)
                        m = re.search(r"19:meeting_([A-Za-z0-9-]+)@thread\.v2", decoded_url)
                        if m:
                            extracted = m.group(0)
                            # Keep for diagnostics; generally the transcripts API expects the OnlineMeeting GUID id
                            logger.info("Extracted thread id from joinUrl, but will prefer OnlineMeeting GUID when available")
                    except Exception:
                        pass

            if not online_meeting_id:
                logger.warning("No usable onlineMeeting id available to fetch transcripts")
                return None

            # List transcripts for this online meeting
            transcripts = await self.list_online_meeting_transcripts(access_token, online_meeting_id)
            if not transcripts:
                logger.warning(f"No transcripts available for onlineMeeting {online_meeting_id}")
                return None

            # Choose the latest transcript by timestamp if possible
            items_sorted = self._sort_transcripts(transcripts)
            latest = items_sorted[-1] if items_sorted else None
            transcript_id = latest.get("id") if isinstance(latest, dict) else None
            if not transcript_id:
                logger.warning("Transcript item had no id")
                return None

            # Fetch content (try text first, then default)
            content = await self.get_online_meeting_transcript_content(access_token, online_meeting_id, transcript_id, format="text")
            if not content:
                logger.warning("Transcript content empty or unavailable")
                return None

            # Best-effort conversion to plain text
            plain = self.to_plain_text(content)
            return plain or content
                
        except Exception as e:
            logger.error(f"Error fetching Teams transcript directly: {e}")
            return None

    async def get_online_meeting_from_event(self, access_token: str, event_id: str) -> Optional[Dict]:
        """Fetch the event and select its onlineMeeting info (not expandable).
        Uses beta endpoint: /beta/me/events/{id}?$select=onlineMeeting,onlineMeetingUrl
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"https://graph.microsoft.com/beta/me/events/{event_id}"
        params = {"$select": "onlineMeeting,onlineMeetingUrl,onlineMeetingProvider"}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code >= 400:
                    try:
                        logger.warning(
                            f"get_online_meeting_from_event failed: status={resp.status_code}, body={resp.text}"
                        )
                    except Exception:
                        pass
                resp.raise_for_status()
                data = resp.json()
                om = data.get("onlineMeeting")
                return om if isinstance(om, dict) else None
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error selecting event onlineMeeting: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error selecting event onlineMeeting: {e}")
            return None

    async def get_event_by_id(self, access_token: str, event_id: str) -> Optional[Dict]:
        """Get a calendar event by id with online meeting info.
        Selects fields needed for resolving an OnlineMeeting via join URL.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="UTC"',
        }
        url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"
        params = {
            "$select": "id,subject,start,end,isOnlineMeeting,onlineMeetingUrl,onlineMeeting,onlineMeetingProvider,attendees,organizer"
        }
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 400:
                    try:
                        logger.warning(
                            f"get_event_by_id failed: status={resp.status_code}, body={resp.text}"
                        )
                    except Exception:
                        pass
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error getting event by id: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error getting event by id: {e}")
            return None

    async def list_online_meeting_transcripts(self, access_token: str, online_meeting_id: str) -> List[Dict]:
        """List transcripts for an online meeting (beta)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"https://graph.microsoft.com/beta/me/onlineMeetings/{online_meeting_id}/transcripts"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                items: List[Dict] = []
                page = 1
                next_url = url
                while True:
                    response = await client.get(next_url, headers=headers)
                    if response.status_code == 404:
                        if page == 1:
                            logger.warning(f"No transcripts found for onlineMeeting {online_meeting_id} (404)")
                        break
                    if response.status_code >= 400:
                        try:
                            logger.warning(
                                f"list_online_meeting_transcripts failed: status={response.status_code}, body={response.text}"
                            )
                        except Exception:
                            pass
                        response.raise_for_status()
                    data = response.json()
                    batch = data.get("value", [])
                    items.extend(batch)
                    req_id = response.headers.get("request-id")
                    logger.info(
                        f"list_online_meeting_transcripts page {page}: fetched {len(batch)} item(s) (cumulative {len(items)}) for onlineMeeting {online_meeting_id}; request-id={req_id}"
                    )
                    next_link = data.get("@odata.nextLink")
                    if not next_link:
                        break
                    next_url = next_link
                    page += 1
                return items
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error listing transcripts: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error listing transcripts: {e}")
            return []

    async def get_online_meeting_transcript_content(self, access_token: str, online_meeting_id: str, transcript_id: str, format: str = "text") -> str:
        """Fetch transcript content for an online meeting transcript.
        Notes:
        - Graph commonly supports transcript content as WebVTT. Use Accept: text/vtt.
        - Passing $format=text is invalid; normalize to a valid mime when provided.
        """
        # Normalize requested format to a Graph-accepted value
        fmt = (format or "").strip().lower()
        normalized_fmt = None
        if fmt in ("text", "vtt", "text/vtt"):
            normalized_fmt = "text/vtt"
        elif fmt in ("html", "text/html"):
            normalized_fmt = "text/html"
        elif fmt in ("plain", "text/plain"):
            # Graph typically returns VTT; try text/plain via Accept only
            normalized_fmt = None

        accept_values = []
        if normalized_fmt:
            accept_values.append(normalized_fmt)
        # Prefer VTT, then anything
        if "text/vtt" not in accept_values:
            accept_values.append("text/vtt")
        accept_values.append("*/*")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": ", ".join(accept_values),
        }

        base = f"https://graph.microsoft.com/beta/me/onlineMeetings/{online_meeting_id}/transcripts/{transcript_id}/content"
        urls = []
        if normalized_fmt:
            urls.append(f"{base}?$format={normalized_fmt}")
        # Also try without explicit $format
        urls.append(base)
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                max_attempts = 3
                backoff_base = 1.0
                for attempt in range(max_attempts):
                    for url in urls:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code in (404, 406):
                            # Not found or not acceptable format; try next url
                            try:
                                logger.info(f"transcript content attempt: status={resp.status_code} url={url}")
                            except Exception:
                                pass
                            continue
                        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                            retry_after = resp.headers.get("Retry-After")
                            try:
                                delay = float(retry_after) if retry_after and str(retry_after).isdigit() else backoff_base * (2 ** attempt)
                            except Exception:
                                delay = backoff_base * (2 ** attempt)
                            logger.warning(f"Transcript content transient error status={resp.status_code}; retrying in {delay}s")
                            try:
                                await asyncio.sleep(delay)
                            except Exception:
                                pass
                            continue
                        resp.raise_for_status()
                        ct = resp.headers.get("Content-Type")
                        req_id = resp.headers.get("request-id")
                        logger.info(f"transcript content fetched: content-type={ct}, len={len(resp.text)}; request-id={req_id}")
                        return resp.text
                    # small backoff between attempts
                    try:
                        await asyncio.sleep(backoff_base * (2 ** attempt))
                    except Exception:
                        pass
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error getting transcript content: {e}")
        except Exception as e:
            logger.warning(f"Error getting transcript content: {e}")
        return ""

    def to_plain_text(self, content: str) -> str:
        """Convert transcript content (VTT/HTML) to plain text best-effort."""
        if not content:
            return ""
        text = content
        # Remove HTML tags if any
        try:
            text = re.sub(r"<[^>]+>", " ", text)
        except Exception:
            pass
        lines = [ln.strip() for ln in text.splitlines()]
        cleaned: List[str] = []
        for ln in lines:
            if not ln or ln.upper().startswith("WEBVTT"):
                continue
            # Skip typical VTT timecode lines
            if "-->" in ln and ":" in ln:
                continue
            if ln.isdigit():
                continue
            cleaned.append(ln)
        return " ".join(cleaned).strip()

    def _iso_utc(self, dt: datetime) -> str:
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            return dt.isoformat()

    def _parse_iso(self, s: Optional[str]) -> Optional[datetime]:
        if not s or not isinstance(s, str):
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    def _participants_to_emails(self, participants: List[str]) -> List[str]:
        emails: List[str] = []
        try:
            for p in participants or []:
                if isinstance(p, dict) and "emailAddress" in p:
                    email = p["emailAddress"].get("address") if isinstance(p["emailAddress"], dict) else p["emailAddress"]
                    if email:
                        emails.append(str(email).lower())
                elif isinstance(p, str):
                    emails.append(p.lower())
        except Exception:
            pass
        return emails

    def _sort_transcripts(self, items: List[Dict]) -> List[Dict]:
        def sort_key(it: Dict):
            for key in ("createdDateTime", "lastModifiedDateTime", "endDateTime", "startDateTime"):
                dt = self._parse_iso(it.get(key))
                if dt:
                    return dt
            # fallback to a deterministic minimal value
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return sorted(items or [], key=sort_key)
        except Exception:
            return items or []

    async def get_call_transcripts(self, access_token: str, call_record_id: str) -> List[Dict]:
        """Fetch call transcripts (Teams Premium required)"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/beta/communications/callRecords/{call_record_id}/transcripts"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 404:
                    logger.warning(f"No transcripts found for call record {call_record_id}")
                    return []
                
                response.raise_for_status()
                data = response.json()
                transcripts = data.get("value", [])
                
                logger.info(f"Found {len(transcripts)} transcripts for call {call_record_id}")
                return transcripts
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting transcripts: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting transcripts: {str(e)}")
            raise

    async def get_transcript_content(self, access_token: str, call_record_id: str, transcript_id: str) -> str:
        """Get transcript content"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "text/plain, text/vtt, */*"
        }
        
        url = f"https://graph.microsoft.com/beta/communications/callRecords/{call_record_id}/transcripts/{transcript_id}/content"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                transcript_content = response.text
                ct = response.headers.get("Content-Type")
                req_id = response.headers.get("request-id")
                logger.info(f"Retrieved transcript content ({len(transcript_content)} chars), content-type={ct}; request-id={req_id}")
                return transcript_content
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting transcript content: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting transcript content: {str(e)}")
            raise

    async def create_planner_task(self, access_token: str, plan_id: str, bucket_id: str, 
                                task_title: str, assigned_user_id: str, due_date: Optional[datetime] = None) -> Dict:
        """Create task in Microsoft Planner"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "planId": plan_id,
            "bucketId": bucket_id,
            "title": task_title,
            "assignments": {
                assigned_user_id: {
                    "@odata.type": "#microsoft.graph.plannerAssignment",
                    "orderHint": " !"
                }
            }
        }
        
        if due_date:
            try:
                # Ensure UTC ISO 8601 with 'Z' suffix for Graph API
                from datetime import timezone
                due_dt_utc = due_date
                if due_dt_utc.tzinfo is None:
                    # treat naive as UTC
                    due_dt_utc = due_dt_utc.replace(tzinfo=timezone.utc)
                else:
                    due_dt_utc = due_dt_utc.astimezone(timezone.utc)
                payload["dueDateTime"] = due_dt_utc.isoformat().replace("+00:00", "Z")
            except Exception:
                # Fallback to raw isoformat
                payload["dueDateTime"] = due_date.isoformat()
        
        url = "https://graph.microsoft.com/v1.0/planner/tasks"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    # Log detailed error payload from Graph for troubleshooting
                    try:
                        logger.error(
                            f"Planner task create failed: status={response.status_code}, body={response.text}"
                        )
                    except Exception:
                        pass
                response.raise_for_status()
                
                task_data = response.json()
                logger.info(f"Created Planner task: {task_title}")
                return task_data
                
        except httpx.HTTPError as e:
            # Try to surface response details if present
            status_code = getattr(getattr(e, 'response', None), 'status_code', None)
            text = getattr(getattr(e, 'response', None), 'text', None)
            logger.error(f"HTTP error creating Planner task: {e}; status={status_code}, body={text}")
            raise
        except Exception as e:
            logger.error(f"Error creating Planner task: {str(e)}")
            raise

    async def send_email(self, access_token: str, to_email: str, subject: str, body: str) -> Dict:
        """Send email using Outlook API"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ]
            }
        }
        
        url = "https://graph.microsoft.com/v1.0/me/sendMail"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                logger.info(f"Email sent to {to_email}")
                return {"status": "sent", "recipient": to_email}
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error sending email: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            raise

    async def list_online_meeting_recordings(self, access_token: str, online_meeting_id: str) -> List[Dict]:
        """List recordings for an online meeting"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"https://graph.microsoft.com/beta/me/onlineMeetings/{online_meeting_id}/recordings"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                items: List[Dict] = []
                page = 1
                next_url = url
                
                while True:
                    response = await client.get(next_url, headers=headers)
                    if response.status_code == 404:
                        if page == 1:
                            logger.warning(f"No recordings found for onlineMeeting {online_meeting_id} (404)")
                        break
                    if response.status_code >= 400:
                        logger.warning(f"list_online_meeting_recordings failed: status={response.status_code}")
                        response.raise_for_status()
                    
                    data = response.json()
                    batch = data.get("value", [])
                    items.extend(batch)
                    
                    logger.info(f"list_online_meeting_recordings page {page}: fetched {len(batch)} item(s) (cumulative {len(items)})")
                    
                    next_link = data.get("@odata.nextLink")
                    if not next_link:
                        break
                    next_url = next_link
                    page += 1
                
                return items
                
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error listing recordings: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error listing recordings: {e}")
            return []

    async def download_meeting_recording(self, access_token: str, online_meeting_id: str, recording_id: str) -> Optional[bytes]:
        """Download a meeting recording as bytes"""
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        url = f"https://graph.microsoft.com/beta/me/onlineMeetings/{online_meeting_id}/recordings/{recording_id}/content"
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    logger.warning(f"Recording content not found: {recording_id}")
                    return None
                response.raise_for_status()
                
                logger.info(f"Downloaded recording {recording_id} ({len(response.content)} bytes)")
                return response.content
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error downloading recording: {e}")
            return None
        except Exception as e:
            logger.error(f"Error downloading recording: {e}")
            return None

    async def search_onedrive_for_recording(self, access_token: str, meeting_title: str, start_time: datetime) -> Optional[bytes]:
        """Search OneDrive directly for Teams recording files"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            # Search for video files in OneDrive that might be the recording
            search_terms = [
                meeting_title.replace(" ", "%20") if meeting_title else "",
                start_time.strftime("%Y-%m-%d"),
                "recording",
                "Teams"
            ]
            
            for search_term in search_terms:
                if not search_term:
                    continue
                    
                # Search OneDrive for files
                url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{search_term}')"
                
                async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        files = data.get("value", [])
                        
                        # Look for video files that might be recordings
                        for file in files:
                            name = file.get("name", "").lower()
                            mime_type = file.get("file", {}).get("mimeType", "")
                            
                            if any(ext in name for ext in [".mp4", ".avi", ".mov", ".wmv"]) or "video" in mime_type:
                                # Check if it's likely a Teams recording
                                if any(keyword in name for keyword in ["recording", "teams", meeting_title.lower()]):
                                    download_url = file.get("@microsoft.graph.downloadUrl")
                                    if download_url:
                                        logger.info(f"Found potential recording file: {file.get('name')}")
                                        
                                        # Download the file
                                        download_resp = await client.get(download_url)
                                        if download_resp.status_code == 200:
                                            logger.info(f"Successfully downloaded recording from OneDrive: {len(download_resp.content)} bytes")
                                            return download_resp.content
                                        
        except Exception as e:
            logger.warning(f"OneDrive search failed: {e}")
            
        return None

    async def find_and_download_meeting_recording(self, access_token: str, meeting_title: str, start_time: datetime, end_time: datetime, participants: List[str]) -> Optional[bytes]:
        """Find and download the first available recording for a meeting"""
        try:
            online_meeting = None
            
            # NEW: First try to find the calendar event and use its joinUrl
            try:
                # Try to find the calendar event by searching recent events
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                # Search for events in the time range
                start_iso = self._iso_utc(start_time)
                end_iso = self._iso_utc(end_time)
                
                url = f"https://graph.microsoft.com/v1.0/me/calendarView?startDateTime={start_iso}&endDateTime={end_iso}&$select=id,subject,start,end,onlineMeeting,onlineMeetingUrl,isOnlineMeeting"
                
                async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    events = resp.json().get("value", [])
                    
                    # Find matching event by title
                    matching_event = None
                    for event in events:
                        if event.get("subject", "").strip().lower() == meeting_title.strip().lower():
                            matching_event = event
                            break
                    
                    if matching_event and matching_event.get("onlineMeeting"):
                        join_url = matching_event["onlineMeeting"].get("joinUrl")
                        if join_url:
                            logger.info(f"Found joinUrl from calendar event: {join_url}")
                            online_meeting = await self.find_online_meeting_by_join_url(access_token, join_url)
                            if online_meeting:
                                logger.info("Successfully found online meeting via calendar event joinUrl")
            except Exception as e:
                logger.warning(f"Calendar event search failed: {e}")
            
            # FALLBACK: Original search methods if calendar event approach failed
            if not online_meeting:
                logger.info("Trying fallback search methods...")
                online_meeting = await self.find_online_meeting_by_time_and_participants(
                    access_token, start_time, end_time, participants
                )
                
                if not online_meeting:
                    # Try alternative search methods
                    online_meeting = await self.search_teams_meetings_directly(
                        access_token, start_time, end_time, participants
                    )
            
            if not online_meeting:
                logger.warning("No online meeting found for recording download")
                return None
            
            online_meeting_id = online_meeting.get("id")
            if not online_meeting_id:
                logger.warning("Online meeting found but no ID available")
                return None
            
            # List recordings for this meeting
            recordings = await self.list_online_meeting_recordings(access_token, online_meeting_id)
            if not recordings:
                logger.warning(f"No recordings found for meeting {online_meeting_id}")
                return None
            
            # Get the latest recording (or first if no timestamp sorting available)
            latest_recording = recordings[-1] if recordings else None
            recording_id = latest_recording.get("id") if latest_recording else None
            
            if not recording_id:
                logger.warning("Recording found but no ID available")
                return None
            
            # Download the recording
            recording_content = await self.download_meeting_recording(access_token, online_meeting_id, recording_id)
            
            if recording_content:
                logger.info(f"Successfully downloaded recording for meeting: {meeting_title}")
                return recording_content
            else:
                logger.warning(f"Failed to download recording content for meeting: {meeting_title}")
                return None
                
        except Exception as e:
            logger.error(f"Error finding and downloading meeting recording: {e}")
            return None