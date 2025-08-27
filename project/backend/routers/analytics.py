from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from database import get_db
from analytics_service import AnalyticsService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

analytics_service = AnalyticsService()

@router.get("/summary")
async def get_analytics_summary(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get overall analytics summary"""
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date_obj = datetime.now()
    else:
        end_date_obj = datetime.fromisoformat(end_date)
    
    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.fromisoformat(start_date)
    
    try:
        summary = analytics_service.get_summary_statistics(db, start_date_obj, end_date_obj)
        
        return {
            "period": {
                "start_date": start_date_obj.isoformat(),
                "end_date": end_date_obj.isoformat()
            },
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics summary: {str(e)}"
        )

@router.get("/meetings-per-user")
async def get_meetings_per_user(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get meeting statistics per user"""
    # Default to last 30 days
    if not end_date:
        end_date_obj = datetime.now()
    else:
        end_date_obj = datetime.fromisoformat(end_date)
    
    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.fromisoformat(start_date)
    
    try:
        user_stats = analytics_service.get_meetings_per_user(
            db, start_date_obj, end_date_obj, department
        )
        
        return {
            "period": {
                "start_date": start_date_obj.isoformat(),
                "end_date": end_date_obj.isoformat()
            },
            "department_filter": department,
            "users": user_stats
        }
        
    except Exception as e:
        logger.error(f"Error getting meetings per user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user statistics: {str(e)}"
        )

@router.get("/department-analytics")
async def get_department_analytics(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get analytics by department"""
    # Default to last 30 days
    if not end_date:
        end_date_obj = datetime.now()
    else:
        end_date_obj = datetime.fromisoformat(end_date)
    
    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.fromisoformat(start_date)
    
    try:
        department_stats = analytics_service.get_department_analytics(
            db, start_date_obj, end_date_obj
        )
        
        return {
            "period": {
                "start_date": start_date_obj.isoformat(),
                "end_date": end_date_obj.isoformat()
            },
            "departments": department_stats
        }
        
    except Exception as e:
        logger.error(f"Error getting department analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get department analytics: {str(e)}"
        )

@router.get("/trends")
async def get_meeting_trends(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    group_by: str = Query(default="day", regex="^(day|week|month)$"),
    db: Session = Depends(get_db)
):
    """Get meeting trends over time"""
    # Default to last 30 days
    if not end_date:
        end_date_obj = datetime.now()
    else:
        end_date_obj = datetime.fromisoformat(end_date)
    
    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.fromisoformat(start_date)
    
    try:
        trends = analytics_service.get_meeting_trends(
            db, start_date_obj, end_date_obj, group_by
        )
        
        return {
            "period": {
                "start_date": start_date_obj.isoformat(),
                "end_date": end_date_obj.isoformat()
            },
            "group_by": group_by,
            "trends": trends
        }
        
    except Exception as e:
        logger.error(f"Error getting meeting trends: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get meeting trends: {str(e)}"
        )

@router.get("/action-items")
async def get_action_items_analytics(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get analytics on action items from MOMs"""
    # Default to last 30 days
    if not end_date:
        end_date_obj = datetime.now()
    else:
        end_date_obj = datetime.fromisoformat(end_date)
    
    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.fromisoformat(start_date)
    
    try:
        action_items_stats = analytics_service.get_action_items_analytics(
            db, start_date_obj, end_date_obj
        )
        
        return {
            "period": {
                "start_date": start_date_obj.isoformat(),
                "end_date": end_date_obj.isoformat()
            },
            "action_items": action_items_stats
        }
        
    except Exception as e:
        logger.error(f"Error getting action items analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get action items analytics: {str(e)}"
        )

from fastapi import HTTPException, status