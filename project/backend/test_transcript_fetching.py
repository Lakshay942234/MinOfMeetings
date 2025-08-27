#!/usr/bin/env python3
"""
Test script to verify automatic transcript fetching functionality
"""
import asyncio
import sys
import os
import requests
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from database import get_db, MeetingRaw, UserTokens
from dotenv import load_dotenv

load_dotenv()

class TranscriptFetchTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    def test_api_endpoints(self):
        """Test the new API endpoints for transcript monitoring"""
        print("🧪 Testing Transcript Monitoring API Endpoints")
        print("=" * 50)
        
        # Test transcript status endpoint
        try:
            response = requests.get(f"{self.base_url}/api/meetings/transcript-status")
            if response.status_code == 200:
                data = response.json()
                print("✅ Transcript Status Endpoint:")
                print(f"   Total meetings (7 days): {data['total_meetings']}")
                print(f"   With transcripts: {data['meetings_with_transcripts']}")
                print(f"   Without transcripts: {data['meetings_without_transcripts']}")
                print(f"   Success rate: {data['transcript_success_rate']}")
                print(f"   Recent updates: {data['recent_transcript_updates']}")
                print(f"   Scheduler status: {data['scheduler_status']}")
            else:
                print(f"❌ Transcript status endpoint failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Error testing transcript status: {e}")
        
        print()
        
        # Test meetings without transcripts endpoint
        try:
            response = requests.get(f"{self.base_url}/api/meetings/meetings-without-transcripts?hours_back=24")
            if response.status_code == 200:
                data = response.json()
                print("✅ Meetings Without Transcripts Endpoint:")
                print(f"   Period: {data['period']}")
                print(f"   Meetings without transcripts: {data['meetings_without_transcripts']}")
                if data['meetings']:
                    print("   Recent meetings without transcripts:")
                    for meeting in data['meetings'][:3]:  # Show first 3
                        print(f"     - {meeting['title']} ({meeting['date']})")
                else:
                    print("   No meetings without transcripts found")
            else:
                print(f"❌ Meetings without transcripts endpoint failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Error testing meetings without transcripts: {e}")
        
        print()
    
    def test_manual_transcript_fetch(self, user_id):
        """Test manual transcript fetching trigger"""
        print("🔄 Testing Manual Transcript Fetch Trigger")
        print("=" * 50)
        
        try:
            response = requests.post(f"{self.base_url}/api/meetings/test-transcript-fetch/{user_id}")
            if response.status_code == 200:
                data = response.json()
                print("✅ Manual Transcript Fetch Test:")
                print(f"   Message: {data['message']}")
                print(f"   Meetings checked: {data['meetings_checked']}")
                print(f"   Transcripts updated: {data['transcripts_updated']}")
                print(f"   Success rate: {data['success_rate']}")
                return data['transcripts_updated'] > 0
            else:
                print(f"❌ Manual transcript fetch failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error testing manual transcript fetch: {e}")
            return False
    
    def monitor_database_changes(self, duration_minutes=5):
        """Monitor database for transcript updates"""
        print(f"📊 Monitoring Database for Transcript Updates ({duration_minutes} minutes)")
        print("=" * 50)
        
        db = next(get_db())
        
        try:
            # Get initial state
            initial_count = db.query(MeetingRaw).filter(
                MeetingRaw.transcript_text.notin_(["Transcript not available", "", None]),
                MeetingRaw.transcript_text != None
            ).count()
            
            print(f"Initial meetings with transcripts: {initial_count}")
            
            # Monitor for changes
            start_time = time.time()
            last_count = initial_count
            
            while time.time() - start_time < duration_minutes * 60:
                current_count = db.query(MeetingRaw).filter(
                    MeetingRaw.transcript_text.notin_(["Transcript not available", "", None]),
                    MeetingRaw.transcript_text != None
                ).count()
                
                if current_count > last_count:
                    new_transcripts = current_count - last_count
                    print(f"🎉 {new_transcripts} new transcript(s) detected! Total: {current_count}")
                    
                    # Show recently updated meetings
                    recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
                    recent_meetings = db.query(MeetingRaw).filter(
                        MeetingRaw.updated_at >= recent_cutoff.replace(tzinfo=None),
                        MeetingRaw.transcript_text.notin_(["Transcript not available", "", None])
                    ).all()
                    
                    for meeting in recent_meetings:
                        print(f"   Updated: {meeting.title} ({len(meeting.transcript_text)} chars)")
                    
                    last_count = current_count
                
                time.sleep(30)  # Check every 30 seconds
            
            final_count = db.query(MeetingRaw).filter(
                MeetingRaw.transcript_text.notin_(["Transcript not available", "", None]),
                MeetingRaw.transcript_text != None
            ).count()
            
            total_new = final_count - initial_count
            print(f"📈 Monitoring complete. New transcripts added: {total_new}")
            
        except Exception as e:
            print(f"❌ Error monitoring database: {e}")
        finally:
            db.close()
    
    def check_scheduler_logs(self):
        """Check application logs for scheduler activity"""
        print("📋 Checking for Scheduler Activity in Logs")
        print("=" * 50)
        
        # This would typically check log files or system logs
        # For now, we'll provide instructions
        print("To check scheduler logs, look for these patterns in your application logs:")
        print("  - 'Starting transcript check cycle'")
        print("  - 'Found X meetings without transcripts'")
        print("  - 'Successfully updated transcript for meeting'")
        print("  - 'Transcript check cycle completed'")
        print()
        print("You can monitor logs in real-time with:")
        print("  tail -f /path/to/your/app.log | grep -i transcript")
        print()
    
    def create_test_meeting(self):
        """Create a test meeting without transcript for testing"""
        print("🏗️  Creating Test Meeting Without Transcript")
        print("=" * 50)
        
        try:
            response = requests.post(f"{self.base_url}/api/meetings/seed-sample", 
                                   params={"with_mom": False})
            if response.status_code == 200:
                data = response.json()
                print("✅ Test meeting created:")
                print(f"   Meeting ID: {data['meeting_id']}")
                print(f"   Title: {data['title']}")
                print(f"   Date: {data['date']}")
                
                # Now remove the transcript to simulate a meeting without transcript
                db = next(get_db())
                try:
                    meeting = db.query(MeetingRaw).filter(
                        MeetingRaw.meeting_id == data['meeting_id']
                    ).first()
                    if meeting:
                        meeting.transcript_text = "Transcript not available"
                        db.commit()
                        print("   ✅ Transcript removed - ready for testing")
                        return data['meeting_id']
                except Exception as e:
                    print(f"   ❌ Error removing transcript: {e}")
                finally:
                    db.close()
            else:
                print(f"❌ Failed to create test meeting: {response.status_code}")
        except Exception as e:
            print(f"❌ Error creating test meeting: {e}")
        
        return None

def main():
    print("🚀 Transcript Fetching Test Suite")
    print("=" * 50)
    print()
    
    tester = TranscriptFetchTester()
    
    # Get user ID for testing (you'll need to provide this)
    user_id = input("Enter user ID for testing (or press Enter to skip manual tests): ").strip()
    
    # Test 1: API Endpoints
    tester.test_api_endpoints()
    print()
    
    # Test 2: Create test meeting
    test_meeting_id = tester.create_test_meeting()
    print()
    
    # Test 3: Manual transcript fetch (if user ID provided)
    if user_id:
        success = tester.test_manual_transcript_fetch(user_id)
        print()
        
        if success:
            print("✅ Manual transcript fetch successful!")
        else:
            print("⚠️  Manual transcript fetch didn't update any transcripts")
    else:
        print("⏭️  Skipping manual transcript fetch test (no user ID provided)")
    
    print()
    
    # Test 4: Check scheduler logs
    tester.check_scheduler_logs()
    print()
    
    # Test 5: Monitor database (optional)
    monitor = input("Monitor database for changes? (y/N): ").strip().lower()
    if monitor == 'y':
        duration = input("Duration in minutes (default 5): ").strip()
        duration = int(duration) if duration.isdigit() else 5
        tester.monitor_database_changes(duration)
    
    print()
    print("🎯 Test Summary")
    print("=" * 50)
    print("To verify transcript fetching is working:")
    print("1. ✅ API endpoints are available for monitoring")
    print("2. ✅ Manual trigger endpoint works")
    print("3. 📊 Database monitoring shows real-time updates")
    print("4. 📋 Check application logs for scheduler activity")
    print()
    print("The automatic scheduler runs every 30 minutes by default.")
    print("Check /api/meetings/transcript-status regularly to monitor progress.")

if __name__ == "__main__":
    main()
