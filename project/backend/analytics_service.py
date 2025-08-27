import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from database import MOMAnalytics, MOMStructured, MeetingRaw, HRData

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self):
        pass

    def calculate_meeting_cost(self, db: Session, participants_list: List[str], 
                              duration_minutes: int) -> float:
        """Calculate meeting cost based on participant salaries and duration"""
        total_cost = 0.0
        duration_hours = duration_minutes / 60
        
        for participant_email in participants_list:
            hr_data = db.query(HRData).filter(
                HRData.user_email == participant_email
            ).first()
            
            if hr_data and hr_data.hourly_salary:
                participant_cost = hr_data.hourly_salary * duration_hours
                total_cost += participant_cost
            else:
                # Use default hourly rate if not found in HR data
                default_rate = 50.0  # $50/hour default
                total_cost += default_rate * duration_hours
                
                logger.warning(f"No HR data found for {participant_email}, using default rate")
        
        return round(total_cost, 2)

    def store_meeting_analytics(self, db: Session, meeting_data: Dict) -> Dict:
        """Store analytics data for a meeting"""
        participants_list = []
        participants_count = 0
        department = "Unknown"
        
        # Extract participant information
        if meeting_data.get("participants_json"):
            participants = meeting_data["participants_json"]
            if isinstance(participants, list):
                participants_list = [
                    p.get("emailAddress", {}).get("address", "") 
                    for p in participants if p.get("emailAddress", {}).get("address")
                ]
                participants_count = len(participants_list)
                
                # Determine department from participants (use organizer's department)
                organizer_email = None
                for p in participants:
                    if p.get("type") == "organizer":
                        organizer_email = p.get("emailAddress", {}).get("address")
                        break
                
                if organizer_email:
                    hr_data = db.query(HRData).filter(
                        HRData.user_email == organizer_email
                    ).first()
                    if hr_data:
                        department = hr_data.department or "Unknown"
        
        # Calculate meeting cost
        duration_minutes = meeting_data.get("duration_minutes", 0)
        total_cost = self.calculate_meeting_cost(db, participants_list, duration_minutes)
        
        # Create analytics record
        analytics_record = MOMAnalytics(
            meeting_id=meeting_data["meeting_id"],
            date=meeting_data["date"],
            duration_minutes=duration_minutes,
            participants_count=participants_count,
            participants_list=participants_list,
            total_cost=total_cost,
            department=department
        )
        
        db.add(analytics_record)
        db.commit()
        
        logger.info(f"Stored analytics for meeting {meeting_data['meeting_id']}")
        
        return {
            "meeting_id": meeting_data["meeting_id"],
            "participants_count": participants_count,
            "duration_minutes": duration_minutes,
            "total_cost": total_cost,
            "department": department
        }

    def get_meetings_per_user(self, db: Session, start_date: datetime, 
                             end_date: datetime, department: Optional[str] = None) -> List[Dict]:
        """Get meeting statistics per user"""
        query = db.query(
            func.json_array_elements_text(MOMAnalytics.participants_list).label('participant'),
            func.count(MOMAnalytics.id).label('meeting_count'),
            func.sum(MOMAnalytics.duration_minutes).label('total_minutes'),
            func.sum(MOMAnalytics.total_cost).label('total_cost')
        ).filter(
            and_(
                MOMAnalytics.date >= start_date,
                MOMAnalytics.date <= end_date
            )
        )
        
        if department:
            query = query.filter(MOMAnalytics.department == department)
        
        query = query.group_by('participant').order_by(func.count(MOMAnalytics.id).desc())
        
        results = query.all()
        
        user_stats = []
        for result in results:
            # Get user display name from HR data
            hr_data = db.query(HRData).filter(HRData.user_email == result.participant).first()
            display_name = hr_data.display_name if hr_data else result.participant
            
            user_stats.append({
                "email": result.participant,
                "display_name": display_name,
                "meeting_count": result.meeting_count,
                "total_minutes": result.total_minutes or 0,
                "total_hours": round((result.total_minutes or 0) / 60, 1),
                "total_cost": round(result.total_cost or 0, 2)
            })
        
        return user_stats

    def get_department_analytics(self, db: Session, start_date: datetime, 
                                end_date: datetime) -> List[Dict]:
        """Get meeting analytics by department"""
        results = db.query(
            MOMAnalytics.department,
            func.count(MOMAnalytics.id).label('meeting_count'),
            func.sum(MOMAnalytics.duration_minutes).label('total_minutes'),
            func.sum(MOMAnalytics.total_cost).label('total_cost'),
            func.avg(MOMAnalytics.participants_count).label('avg_participants'),
            func.avg(MOMAnalytics.duration_minutes).label('avg_duration')
        ).filter(
            and_(
                MOMAnalytics.date >= start_date,
                MOMAnalytics.date <= end_date
            )
        ).group_by(MOMAnalytics.department).all()
        
        department_stats = []
        for result in results:
            department_stats.append({
                "department": result.department or "Unknown",
                "meeting_count": result.meeting_count,
                "total_minutes": result.total_minutes or 0,
                "total_hours": round((result.total_minutes or 0) / 60, 1),
                "total_cost": round(result.total_cost or 0, 2),
                "avg_participants": round(result.avg_participants or 0, 1),
                "avg_duration_minutes": round(result.avg_duration or 0, 1)
            })
        
        return sorted(department_stats, key=lambda x: x["total_cost"], reverse=True)

    def get_meeting_trends(self, db: Session, start_date: datetime, 
                          end_date: datetime, group_by: str = "day") -> List[Dict]:
        """Get meeting trends over time"""
        if group_by == "day":
            date_trunc = func.date_trunc('day', MOMAnalytics.date)
        elif group_by == "week":
            date_trunc = func.date_trunc('week', MOMAnalytics.date)
        elif group_by == "month":
            date_trunc = func.date_trunc('month', MOMAnalytics.date)
        else:
            date_trunc = func.date_trunc('day', MOMAnalytics.date)
        
        results = db.query(
            date_trunc.label('period'),
            func.count(MOMAnalytics.id).label('meeting_count'),
            func.sum(MOMAnalytics.duration_minutes).label('total_minutes'),
            func.sum(MOMAnalytics.total_cost).label('total_cost'),
            func.avg(MOMAnalytics.participants_count).label('avg_participants')
        ).filter(
            and_(
                MOMAnalytics.date >= start_date,
                MOMAnalytics.date <= end_date
            )
        ).group_by('period').order_by('period').all()
        
        trends = []
        for result in results:
            trends.append({
                "period": result.period.isoformat(),
                "meeting_count": result.meeting_count,
                "total_minutes": result.total_minutes or 0,
                "total_hours": round((result.total_minutes or 0) / 60, 1),
                "total_cost": round(result.total_cost or 0, 2),
                "avg_participants": round(result.avg_participants or 0, 1)
            })
        
        return trends

    def get_summary_statistics(self, db: Session, start_date: datetime, 
                              end_date: datetime) -> Dict:
        """Get overall summary statistics"""
        # Total meetings and time
        totals = db.query(
            func.count(MOMAnalytics.id).label('total_meetings'),
            func.sum(MOMAnalytics.duration_minutes).label('total_minutes'),
            func.sum(MOMAnalytics.total_cost).label('total_cost'),
            func.avg(MOMAnalytics.participants_count).label('avg_participants'),
            func.avg(MOMAnalytics.duration_minutes).label('avg_duration')
        ).filter(
            and_(
                MOMAnalytics.date >= start_date,
                MOMAnalytics.date <= end_date
            )
        ).first()
        
        # Unique participants - use subquery to avoid aggregate function with set-returning function
        from sqlalchemy import text
        unique_participants_query = text("""
            SELECT COUNT(DISTINCT participant) 
            FROM mom_analytics, 
            LATERAL json_array_elements_text(participants_list) AS participant
            WHERE date >= :start_date AND date <= :end_date
        """)
        unique_participants = db.execute(
            unique_participants_query, 
            {"start_date": start_date, "end_date": end_date}
        ).scalar()
        
        # Department count
        department_count = db.query(
            func.count(func.distinct(MOMAnalytics.department))
        ).filter(
            and_(
                MOMAnalytics.date >= start_date,
                MOMAnalytics.date <= end_date,
                MOMAnalytics.department.isnot(None),
                MOMAnalytics.department != "Unknown"
            )
        ).scalar()
        
        return {
            "total_meetings": totals.total_meetings or 0,
            "total_minutes": totals.total_minutes or 0,
            "total_hours": round((totals.total_minutes or 0) / 60, 1),
            "total_cost": round(totals.total_cost or 0, 2),
            "avg_participants": round(totals.avg_participants or 0, 1),
            "avg_duration_minutes": round(totals.avg_duration or 0, 1),
            "unique_participants": unique_participants or 0,
            "departments_involved": department_count or 0
        }

    def get_action_items_analytics(self, db: Session, start_date: datetime, 
                                  end_date: datetime) -> Dict:
        """Get analytics on action items from MOMs"""
        moms = db.query(MOMStructured).filter(
            and_(
                MOMStructured.date >= start_date,
                MOMStructured.date <= end_date
            )
        ).all()
        
        total_action_items = 0
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        assignee_counts = {}
        
        for mom in moms:
            if mom.action_items:
                action_items = mom.action_items if isinstance(mom.action_items, list) else []
                total_action_items += len(action_items)
                
                for item in action_items:
                    # Count by priority
                    priority = item.get("priority", "medium")
                    if priority in priority_counts:
                        priority_counts[priority] += 1
                    
                    # Count by assignee
                    assignee = item.get("assigned_to", "Unassigned")
                    assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1
        
        return {
            "total_action_items": total_action_items,
            "priority_distribution": priority_counts,
            "top_assignees": sorted(
                assignee_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10],
            "meetings_with_action_items": len([m for m in moms if m.action_items])
        }