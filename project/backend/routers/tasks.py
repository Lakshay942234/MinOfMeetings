from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from database import get_db, MOMStructured, MeetingRaw, HRData, TaskItem
from task_assigner import TaskAssigner
from routers.auth import async_get_valid_token
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

task_assigner = TaskAssigner()

class AssignTasksRequest(BaseModel):
    user_id: Optional[str] = None
    class Config:
        extra = "ignore"

class UpdateStatusRequest(BaseModel):
    status: Literal["pending", "in_progress", "completed", "blocked"]

@router.post("/assign/{meeting_id}")
async def assign_tasks(
    meeting_id: str,
    user_id: Optional[str] = Query(default=None, description="User ID owning Graph tokens"),
    assign_to_all: bool = Query(default=False, description="Assign each action item to ALL meeting participants"),
    payload: Optional[AssignTasksRequest] = Body(default=None),
    db: Session = Depends(get_db)
):
    """Assign tasks from MOM action items"""
    try:
        # Resolve user_id from query or JSON body
        if not user_id and payload and payload.user_id:
            user_id = payload.user_id
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Missing user_id. Provide as ?user_id=... or JSON body {\"user_id\": \"...\"}."
            )

        # Get valid access token (async-safe)
        access_token = await async_get_valid_token(user_id, db)
        
        # Get MOM data
        mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
        
        if not mom:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MOM not found for this meeting"
            )
        
        if not mom.action_items:
            return {
                "message": "No action items found in MOM",
                "assigned_tasks": []
            }
        
        # Build participants map for enrichment and optional assign_to_all
        meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
        participants_map = {}
        participants_emails = []
        if meeting and isinstance(meeting.participants_json, list):
            for p in meeting.participants_json:
                email = None
                name = None
                if isinstance(p, dict):
                    email_addr = (p.get("emailAddress") or {}) if isinstance(p.get("emailAddress"), dict) else {}
                    email = email_addr.get("address")
                    name = email_addr.get("name")
                elif isinstance(p, str):
                    email = p
                if email:
                    participants_emails.append(email)
                if email and name:
                    participants_map[email.lower()] = name

        # Prepare action items (optionally replicate for all participants)
        original_items = mom.action_items if isinstance(mom.action_items, list) else []
        action_items = []
        if assign_to_all and participants_emails:
            for item in original_items:
                base_task = item.get("task") if isinstance(item, dict) else None
                if not base_task:
                    continue
                for email in participants_emails:
                    cloned = dict(item)
                    cloned["assigned_to"] = email
                    action_items.append(cloned)
        else:
            action_items = original_items

        # Assign tasks
        assigned_tasks = await task_assigner.assign_tasks(
            access_token=access_token,
            action_items=action_items,
            meeting_title=mom.meeting_title
        )
        # Enrich assignee names using meeting participants and HR data

        for t in assigned_tasks:
            email = (t.get("assigned_to") or "").lower()
            current_name = t.get("assignee_name")
            # If name missing or equals email, try to resolve
            if email and (not current_name or current_name.lower() == email):
                name = participants_map.get(email)
                if not name:
                    hr = db.query(HRData).filter(HRData.user_email == email).first()
                    if hr and hr.display_name:
                        name = hr.display_name
                if name:
                    t["assignee_name"] = name

        # Persist assigned tasks into TaskItem table (upsert by meeting_id + task + assigned_to)
        for t in assigned_tasks:
            try:
                task_text = t.get("task")
                assigned_to = t.get("assigned_to")
                if not task_text or not assigned_to:
                    continue
                due_date_str = t.get("due_date")
                due_dt = None
                if due_date_str:
                    try:
                        due_dt = datetime.fromisoformat(due_date_str)
                    except Exception:
                        due_dt = None
                status_src = t.get("status")
                source = "planner" if status_src == "assigned_to_planner" else ("email" if status_src == "email_sent" else "local")
                external_id = t.get("planner_task_id")

                existing = db.query(TaskItem).filter(
                    TaskItem.meeting_id == meeting_id,
                    TaskItem.task == task_text,
                    TaskItem.assigned_to == assigned_to
                ).first()
                if existing:
                    existing.due_date = due_dt
                    existing.priority = t.get("priority", existing.priority or "medium")
                    existing.source = source
                    existing.external_id = external_id
                else:
                    new_task = TaskItem(
                        meeting_id=meeting_id,
                        task=task_text,
                        assigned_to=assigned_to,
                        due_date=due_dt,
                        priority=t.get("priority", "medium"),
                        status="pending",
                        source=source,
                        external_id=external_id
                    )
                    db.add(new_task)
            except Exception as e:
                logger.warning(f"Failed to persist task: {e}")

        db.commit()

        # Calculate metrics
        metrics = task_assigner.calculate_task_metrics(assigned_tasks)
        
        logger.info(f"Assigned {len(assigned_tasks)} tasks for meeting {meeting_id}")
        
        return {
            "message": f"Processed {len(assigned_tasks)} task assignments",
            "assigned_tasks": assigned_tasks,
            "metrics": metrics
        }
        
    except HTTPException as he:
        logger.error(f"Error assigning tasks (HTTP): {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Error assigning tasks: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign tasks: {str(e)}"
        )

@router.get("/by-meeting/{meeting_id}")
async def list_tasks_by_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """List persisted tasks for a meeting, enriched with assignee name if available"""
    tasks = db.query(TaskItem).filter(TaskItem.meeting_id == meeting_id).order_by(TaskItem.created_at.desc()).all()

    # Build participants map for names
    meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
    participants_map = {}
    if meeting and isinstance(meeting.participants_json, list):
        for p in meeting.participants_json:
            email = None
            name = None
            if isinstance(p, dict):
                email_addr = (p.get("emailAddress") or {}) if isinstance(p.get("emailAddress"), dict) else {}
                email = email_addr.get("address")
                name = email_addr.get("name")
            elif isinstance(p, str):
                email = p
            if email and name:
                participants_map[email.lower()] = name

    result = []
    for t in tasks:
        assignee_name = None
        if t.assigned_to:
            assignee_name = participants_map.get((t.assigned_to or "").lower())
            if not assignee_name:
                hr = db.query(HRData).filter(HRData.user_email == (t.assigned_to or "").lower()).first()
                if hr and hr.display_name:
                    assignee_name = hr.display_name
        result.append({
            "id": t.id,
            "meeting_id": t.meeting_id,
            "task": t.task,
            "assigned_to": t.assigned_to,
            "assignee_name": assignee_name or t.assigned_to,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority,
            "status": t.status,
            "source": t.source,
            "external_id": t.external_id
        })

    return {"tasks": result, "count": len(result)}

@router.put("/status/{task_id}")
async def update_task_status(task_id: int, body: UpdateStatusRequest, db: Session = Depends(get_db)):
    """Update the status of a task. Any participant can change their task status."""
    t = db.query(TaskItem).filter(TaskItem.id == task_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    t.status = body.status
    db.commit()
    db.refresh(t)
    return {"id": t.id, "status": t.status}

@router.get("/action-items/{meeting_id}")
async def get_action_items(meeting_id: str, db: Session = Depends(get_db)):
    """Get action items for a specific meeting"""
    mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
    
    if not mom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOM not found for this meeting"
        )
    
    action_items = mom.action_items or []

    # Build participants email->name map from meeting and HRData fallback
    meeting = db.query(MeetingRaw).filter(MeetingRaw.meeting_id == meeting_id).first()
    participants_map = {}
    if meeting and isinstance(meeting.participants_json, list):
        for p in meeting.participants_json:
            email = None
            name = None
            if isinstance(p, dict):
                email_addr = (p.get("emailAddress") or {}) if isinstance(p.get("emailAddress"), dict) else {}
                email = email_addr.get("address")
                name = email_addr.get("name")
            elif isinstance(p, str):
                email = p
            if email and name:
                participants_map[email.lower()] = name

    enriched_items = []
    for item in action_items if isinstance(action_items, list) else []:
        assigned_to = (item.get("assigned_to") or "").lower() if isinstance(item, dict) else ""
        assignee_name = None
        if assigned_to:
            assignee_name = participants_map.get(assigned_to)
            if not assignee_name:
                hr = db.query(HRData).filter(HRData.user_email == assigned_to).first()
                if hr and hr.display_name:
                    assignee_name = hr.display_name
        if isinstance(item, dict):
            enriched = dict(item)
            enriched["assignee_name"] = assignee_name or item.get("assigned_to")
            enriched_items.append(enriched)

    return {
        "meeting_id": meeting_id,
        "meeting_title": mom.meeting_title,
        "action_items": enriched_items,
        "total_items": len(enriched_items)
    }

@router.get("/metrics")
async def get_task_metrics(db: Session = Depends(get_db)):
    """Get overall task assignment metrics"""
    try:
        # Get all MOMs with action items
        moms_with_tasks = db.query(MOMStructured).filter(
            MOMStructured.action_items.isnot(None)
        ).all()
        
        total_meetings_with_tasks = len(moms_with_tasks)
        total_action_items = 0
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        assignee_counts = {}
        
        for mom in moms_with_tasks:
            if isinstance(mom.action_items, list):
                total_action_items += len(mom.action_items)
                
                for item in mom.action_items:
                    # Count priorities
                    priority = item.get("priority", "medium")
                    if priority in priority_counts:
                        priority_counts[priority] += 1
                    
                    # Count assignees
                    assignee = item.get("assigned_to", "Unassigned")
                    assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1
        
        # Get top assignees
        top_assignees = sorted(
            assignee_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return {
            "total_meetings_with_tasks": total_meetings_with_tasks,
            "total_action_items": total_action_items,
            "priority_distribution": priority_counts,
            "top_assignees": [
                {"assignee": assignee, "task_count": count}
                for assignee, count in top_assignees
            ],
            "unique_assignees": len(assignee_counts)
        }
        
    except Exception as e:
        logger.error(f"Error getting task metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task metrics: {str(e)}"
        )