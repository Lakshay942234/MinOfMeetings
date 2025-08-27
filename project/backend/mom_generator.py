from openai import AsyncOpenAI
import logging
from typing import Dict, List
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
logger = logging.getLogger(__name__)

class MOMGenerator:
    def __init__(self):
        # Initialize MAXAI-compatible OpenAI client
        self.client = AsyncOpenAI(
            base_url=os.getenv("MAXAI_BASE_URL", "https://maxai.knowmax.in/llm"),
            api_key=os.getenv("MAXAI_API_KEY"),
        )
        # Default model/settings provided by user
        self.settings = {
            "model": "km/maxai",
            "temperature": 0.1,
            "presence_penalty": 1.5,
            "frequency_penalty": 1.5,
            "top_p": 0.8,
            "max_tokens": 8192,
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
        }

    async def generate_mom(self, transcript_text: str, participants: List[Dict], 
                          meeting_title: str, meeting_date: datetime) -> Dict:
        """Generate structured Minutes of Meeting from transcript"""
        
        participants_info = []
        for participant in participants:
            # Microsoft Graph attendees: { emailAddress: { name, address }, type }
            email_addr = participant.get("emailAddress") if isinstance(participant, dict) else None
            if isinstance(email_addr, dict):
                name = email_addr.get("name") or "Unknown"
                email = email_addr.get("address", "")
            else:
                name = participant.get("displayName", "Unknown") if isinstance(participant, dict) else "Unknown"
                email = ""
            participants_info.append({
                "name": name,
                "email": email,
                "role": participant.get("type", "attendee") if isinstance(participant, dict) else "attendee"
            })
        
        prompt = f"""
        From the following meeting transcript and participant information, generate a structured Minutes of Meeting in JSON format.

        Meeting Details:
        - Title: {meeting_title}
        - Date: {meeting_date.strftime('%Y-%m-%d %H:%M')}
        - Participants: {json.dumps(participants_info, indent=2)}

        Transcript:
        {transcript_text}

        Please generate a JSON response with the following structure:
        {{
            "meeting_title": "{meeting_title}",
            "date": "{meeting_date.isoformat()}",
            "agenda": [
                "List of agenda items discussed"
            ],
            "key_decisions": [
                "Important decisions made during the meeting"
            ],
            "action_items": [
                {{
                    "task": "Description of the task",
                    "assigned_to": "email@example.com",
                    "due_date": "YYYY-MM-DD",
                    "priority": "high/medium/low"
                }}
            ],
            "follow_up_points": [
                "Items that need follow-up in future meetings"
            ]
        }}

        Instructions:
        1. Extract concrete action items with clear assignees
        2. Identify key decisions that were made
        3. List agenda items that were actually discussed
        4. Note any follow-up items for future meetings
        5. For action items, try to match assignees to participant emails
        6. If no due date is mentioned, set it to 7 days from the meeting date
        7. Prioritize action items based on urgency discussed in the meeting
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.settings["model"],
                messages=[
                    {"role": "system", "content": "You are an expert meeting assistant that generates structured minutes of meetings from transcripts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings["temperature"],
                presence_penalty=self.settings["presence_penalty"],
                frequency_penalty=self.settings["frequency_penalty"],
                top_p=self.settings["top_p"],
                # Limit tokens for structured JSON while respecting the overall cap
                max_tokens=min(2000, self.settings["max_tokens"]),
                extra_body=self.settings.get("extra_body"),
            )

            mom_content = response.choices[0].message.content
            
            # Parse JSON response
            try:
                mom_data = json.loads(mom_content)
                logger.info(f"Generated MOM for meeting: {meeting_title}")
                return mom_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse GPT response as JSON: {str(e)}")
                # Return a basic structure if JSON parsing fails
                return self._create_fallback_mom(meeting_title, meeting_date, participants_info)
                
        except Exception as e:
            logger.error(f"Error generating MOM: {str(e)}")
            return self._create_fallback_mom(meeting_title, meeting_date, participants_info)

    def _create_fallback_mom(self, meeting_title: str, meeting_date: datetime, 
                            participants: List[Dict]) -> Dict:
        """Create a basic MOM structure if AI generation fails"""
        return {
            "meeting_title": meeting_title,
            "date": meeting_date.isoformat(),
            "agenda": ["Meeting topics discussed"],
            "key_decisions": ["Decisions to be extracted manually"],
            "action_items": [],
            "follow_up_points": ["Follow-up items to be reviewed"]
        }

    async def summarize_transcript(self, transcript_text: str) -> str:
        """Generate a brief summary of the transcript"""
        prompt = f"""
        Please provide a brief 2-3 sentence summary of the following meeting transcript:

        {transcript_text[:3000]}  # Limit text to avoid token limits
    

        Summary should focus on:
        1. Main topics discussed
        2. Key outcomes or decisions
        3. Overall meeting purpose
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.settings["model"],
                messages=[
                    {"role": "system", "content": "You are a meeting summarization assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings["temperature"],
                presence_penalty=self.settings["presence_penalty"],
                frequency_penalty=self.settings["frequency_penalty"],
                top_p=self.settings["top_p"],
                max_tokens=min(200, self.settings["max_tokens"]),
                extra_body=self.settings.get("extra_body"),
            )

            summary = response.choices[0].message.content
            logger.info("Generated meeting summary")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return "Meeting summary could not be generated."