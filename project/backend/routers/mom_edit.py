from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db, MOMStructured, TaskItem
from schemas.mom_schemas import (
    MOMUpdate, MOMResponse, 
    ActionItemCreate, ActionItemUpdate, ActionItemResponse
)
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/mom/{meeting_id}", response_model=MOMResponse)
async def get_mom(meeting_id: str, db: Session = Depends(get_db)):
    """Get MOM for a specific meeting"""
    mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
    if not mom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MOM not found for meeting {meeting_id}"
        )
    return mom

@router.put("/mom/{meeting_id}", response_model=MOMResponse)
async def update_mom(
    meeting_id: str, 
    mom_update: MOMUpdate, 
    db: Session = Depends(get_db)
):
    """Update MOM for a specific meeting"""
    mom = db.query(MOMStructured).filter(MOMStructured.meeting_id == meeting_id).first()
    if not mom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MOM not found for meeting {meeting_id}"
        )
    
    # Update only provided fields
    update_data = mom_update.dict(exclude_unset=True)
    logger.debug(f"Raw MOM update payload for {meeting_id}: {update_data}")

    # Normalize list fields to a consistent [{"text": str}] shape
    def _normalize_points(value):
        if value is None:
            return None
        if isinstance(value, list):
            normalized = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content") or ""
                    normalized.append({"text": text})
                elif isinstance(item, str):
                    normalized.append({"text": item})
                else:
                    normalized.append({"text": str(item)})
            return normalized
        return value

    for fld in ["agenda", "key_decisions", "follow_up_points"]:
        if fld in update_data:
            update_data[fld] = _normalize_points(update_data.get(fld))

    # Action items for display may come from TaskItem table; avoid overwriting JSON unless explicitly desired
    if "action_items" in update_data:
        logger.warning("Ignoring 'action_items' in MOM update; action items are managed via dedicated endpoints")
        update_data.pop("action_items", None)

    for field, value in update_data.items():
        setattr(mom, field, value)
    
    try:
        db.commit()
        db.refresh(mom)
        logger.info(f"Updated MOM for meeting {meeting_id}")
        return mom
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating MOM for meeting {meeting_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update MOM"
        )

@router.get("/action-items/{meeting_id}", response_model=List[ActionItemResponse])
async def get_action_items(meeting_id: str, db: Session = Depends(get_db)):
    """Get all action items for a specific meeting"""
    action_items = db.query(TaskItem).filter(TaskItem.meeting_id == meeting_id).all()
    return action_items

@router.post("/action-items/{meeting_id}", response_model=ActionItemResponse)
async def create_action_item(
    meeting_id: str,
    action_item: ActionItemCreate,
    db: Session = Depends(get_db)
):
    """Create a new action item for a meeting"""
    new_item = TaskItem(
        meeting_id=meeting_id,
        **action_item.dict()
    )
    
    try:
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        logger.info(f"Created action item {new_item.id} for meeting {meeting_id}")
        return new_item
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating action item for meeting {meeting_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create action item"
        )

@router.put("/action-items/{item_id}", response_model=ActionItemResponse)
async def update_action_item(
    item_id: int,
    action_item_update: ActionItemUpdate,
    db: Session = Depends(get_db)
):
    """Update a specific action item"""
    action_item = db.query(TaskItem).filter(TaskItem.id == item_id).first()
    if not action_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {item_id} not found"
        )
    
    # Update only provided fields
    update_data = action_item_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action_item, field, value)
    
    try:
        db.commit()
        db.refresh(action_item)
        logger.info(f"Updated action item {item_id}")
        return action_item
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating action item {item_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update action item"
        )

@router.delete("/action-items/{item_id}")
async def delete_action_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a specific action item"""
    action_item = db.query(TaskItem).filter(TaskItem.id == item_id).first()
    if not action_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {item_id} not found"
        )
    
    try:
        db.delete(action_item)
        db.commit()
        logger.info(f"Deleted action item {item_id}")
        return {"message": f"Action item {item_id} deleted successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting action item {item_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete action item"
        )

@router.get("/action-items/user/{user_email}", response_model=List[ActionItemResponse])
async def get_user_action_items(user_email: str, db: Session = Depends(get_db)):
    """Get all action items assigned to a specific user"""
    action_items = db.query(TaskItem).filter(TaskItem.assigned_to == user_email).all()
    return action_items

@router.put("/action-items/{item_id}/status")
async def update_action_item_status(
    item_id: int,
    status: str,
    db: Session = Depends(get_db)
):
    """Quick update for action item status"""
    if status not in ["pending", "in_progress", "completed", "blocked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Must be one of: pending, in_progress, completed, blocked"
        )
    
    action_item = db.query(TaskItem).filter(TaskItem.id == item_id).first()
    if not action_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {item_id} not found"
        )
    
    try:
        action_item.status = status
        db.commit()
        logger.info(f"Updated action item {item_id} status to {status}")
        return {"message": f"Action item {item_id} status updated to {status}"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating action item {item_id} status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update action item status"
        )
