from datetime import datetime, timedelta, timezone
from database import SessionLocal, MeetingRaw, MOMStructured


def main():
    db = SessionLocal()
    try:
        meeting_id = "sample-meeting-1"
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        participants = [
            {"emailAddress": {"address": "lakshay.1@kochartech.com", "name": "Alice Johnson"}, "type": "required"},
            {"emailAddress": {"address": "lakshay.1@kochartech.com", "name": "Bob Smith"}, "type": "required"},
            {"emailAddress": {"address": "lakshay.1@kochartech.com", "name": "Carol Lee"}, "type": "optional"},
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

        # Upsert MeetingRaw
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        if not meeting:
            meeting = MeetingRaw(
                meeting_id=meeting_id,
                title="Project Kickoff - Sample",
                date=now_utc,
                transcript_text=transcript_text,
                participants_json=participants,
                duration_minutes=45,
            )
            db.add(meeting)
            db.commit()
        else:
            meeting.title = "Project Kickoff - Sample"
            meeting.date = now_utc
            meeting.transcript_text = transcript_text
            meeting.participants_json = participants
            meeting.duration_minutes = 45
            db.commit()

        # Upsert MOMStructured (simulating AI-generated MOM)
        mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
        mom_payload = dict(
            meeting_id=meeting_id,
            meeting_title="Project Kickoff - Sample",
            date=now_utc,
            agenda=[
                {"topic": "Introductions"},
                {"topic": "Scope & Objectives"},
                {"topic": "Timelines & Milestones"},
            ],
            key_decisions=[
                {"decision": "Stack: FastAPI backend, React + TS frontend"},
                {"decision": "Sprints: 2-week cadence"},
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
                {"note": "Confirm access to Microsoft Graph API"},
                {"note": "Schedule weekly standups"},
            ],
        )
        if not mom:
            mom = MOMStructured(**mom_payload)
            db.add(mom)
            db.commit()
        else:
            mom.meeting_title = mom_payload["meeting_title"]
            mom.date = mom_payload["date"]
            mom.agenda = mom_payload["agenda"]
            mom.key_decisions = mom_payload["key_decisions"]
            mom.action_items = mom_payload["action_items"]
            mom.follow_up_points = mom_payload["follow_up_points"]
            db.commit()

        print(f"Seed complete: meeting_id={meeting_id}, participants={len(participants)}, action_items={len(mom_payload['action_items'])}")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

