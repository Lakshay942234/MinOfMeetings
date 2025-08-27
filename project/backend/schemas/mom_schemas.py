from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ActionItemUpdate(BaseModel):
    task: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high)$")
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed|blocked)$")

class ActionItemCreate(BaseModel):
    task: str
    assigned_to: str
    due_date: Optional[datetime] = None
    priority: str = Field("medium", pattern="^(low|medium|high)$")
    status: str = Field("pending", pattern="^(pending|in_progress|completed|blocked)$")

class ActionItemResponse(BaseModel):
    id: int
    meeting_id: str
    task: str
    assigned_to: str
    due_date: Optional[datetime]
    priority: str
    status: str
    source: str
    external_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MOMUpdate(BaseModel):
    meeting_title: Optional[str] = None
    agenda: Optional[List[Dict[str, Any]]] = None
    key_decisions: Optional[List[Dict[str, Any]]] = None
    action_items: Optional[List[Dict[str, Any]]] = None
    follow_up_points: Optional[List[Dict[str, Any]]] = None

class MOMResponse(BaseModel):
    id: int
    meeting_id: str
    meeting_title: str
    date: datetime
    agenda: Optional[List[Dict[str, Any]]]
    key_decisions: Optional[List[Dict[str, Any]]]
    action_items: Optional[List[Dict[str, Any]]]
    follow_up_points: Optional[List[Dict[str, Any]]]
    created_at: datetime

    class Config:
        from_attributes = True
