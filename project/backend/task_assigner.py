import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from ms_graph_service import MSGraphService
from database import get_db, HRData
import asyncio
import os

logger = logging.getLogger(__name__)

class TaskAssigner:
    def __init__(self):
        self.graph_service = MSGraphService()
        # Read default Planner configuration from environment
        self.default_plan_id = os.getenv("DEFAULT_PLANNER_PLAN_ID")  # Planner Plan ID
        self.default_bucket_id = os.getenv("DEFAULT_PLANNER_BUCKET_ID")  # Planner Bucket ID
        if not self.default_plan_id or not self.default_bucket_id:
            logger.warning(
                "Planner DEFAULT_PLANNER_PLAN_ID/DEFAULT_PLANNER_BUCKET_ID not set; will fall back to email notifications."
            )

    async def assign_tasks(self, access_token: str, action_items: List[Dict], 
                          meeting_title: str) -> List[Dict]:
        """Assign tasks from MOM to Microsoft Planner or send emails"""
        assigned_tasks = []
        
        # Get or create meeting-specific bucket if Planner is configured
        meeting_bucket_id = None
        if self.default_plan_id:
            try:
                meeting_bucket_id = await self.graph_service.get_or_create_meeting_bucket(
                    access_token=access_token,
                    plan_id=self.default_plan_id,
                    meeting_title=meeting_title
                )
                if meeting_bucket_id:
                    logger.info(f"Using meeting-specific bucket: {meeting_bucket_id} for '{meeting_title}'")
                else:
                    logger.warning(f"Failed to create/find bucket for meeting '{meeting_title}', falling back to default bucket")
                    meeting_bucket_id = self.default_bucket_id
            except Exception as e:
                logger.error(f"Error getting meeting bucket: {str(e)}, falling back to default bucket")
                meeting_bucket_id = self.default_bucket_id
        
        for action_item in action_items:
            task = action_item.get("task", "")
            assigned_to = action_item.get("assigned_to", "")
            due_date_str = action_item.get("due_date", "")
            priority = action_item.get("priority", "medium")
            
            if not task or not assigned_to:
                logger.warning(f"Skipping incomplete action item: {action_item}")
                continue
            
            # Parse due date
            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str)
                except ValueError:
                    logger.warning(f"Invalid due date format: {due_date_str}")
                    due_date = datetime.now() + timedelta(days=7)
            else:
                due_date = datetime.now() + timedelta(days=7)
            
            try:
                # Try to find user in Microsoft directory and create Planner task
                user_info = await self._find_user_by_email(access_token, assigned_to)
                
                if user_info and self.default_plan_id and meeting_bucket_id:
                    # Try creating task first (check if user is already a member)
                    try:
                        task_result = await self.graph_service.create_planner_task(
                            access_token=access_token,
                            plan_id=self.default_plan_id,
                            bucket_id=meeting_bucket_id,
                            task_title=f"[{meeting_title}] {task}",
                            assigned_user_id=user_info["id"],
                            due_date=due_date,
                            auto_add_member=False  # Try without adding first
                        )
                    except Exception as e:
                        # If task creation fails, try adding user to plan first
                        logger.info(f"Task creation failed, attempting to add user to plan: {str(e)}")
                        task_result = await self.graph_service.create_planner_task(
                            access_token=access_token,
                            plan_id=self.default_plan_id,
                            bucket_id=meeting_bucket_id,
                            task_title=f"[{meeting_title}] {task}",
                            assigned_user_id=user_info["id"],
                            due_date=due_date,
                            auto_add_member=True  # Now try with automatic member addition
                        )
                    
                    assigned_tasks.append({
                        "task": task,
                        "assigned_to": assigned_to,
                        "due_date": due_date.isoformat(),
                        "priority": priority,
                        "status": "assigned_to_planner",
                        "planner_task_id": task_result.get("id"),
                        "planner_bucket_id": meeting_bucket_id,
                        "meeting_bucket_created": meeting_bucket_id != self.default_bucket_id,
                        "assignee_name": user_info.get("displayName", assigned_to)
                    })
                    
                else:
                    # User not found in Planner or no plan configured, send email
                    email_sent = await self._send_task_email(
                        access_token=access_token,
                        to_email=assigned_to,
                        task=task,
                        meeting_title=meeting_title,
                        due_date=due_date,
                        priority=priority
                    )
                    
                    if email_sent:
                        assigned_tasks.append({
                            "task": task,
                            "assigned_to": assigned_to,
                            "due_date": due_date.isoformat(),
                            "priority": priority,
                            "status": "email_sent",
                            "assignee_name": user_info.get("displayName", assigned_to) if user_info else assigned_to
                        })
                    else:
                        assigned_tasks.append({
                            "task": task,
                            "assigned_to": assigned_to,
                            "due_date": due_date.isoformat(),
                            "priority": priority,
                            "status": "failed",
                            "error": "Failed to send email notification"
                        })
                
            except Exception as e:
                logger.error(f"Error assigning task '{task}' to {assigned_to}: {str(e)}")
                assigned_tasks.append({
                    "task": task,
                    "assigned_to": assigned_to,
                    "due_date": due_date.isoformat() if due_date else "",
                    "priority": priority,
                    "status": "failed",
                    "error": str(e)
                })
        
        logger.info(f"Processed {len(assigned_tasks)} task assignments")
        return assigned_tasks

    async def _find_user_by_email(self, access_token: str, email: str) -> Optional[Dict]:
        """Find user by email in Microsoft directory"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/users/{email}"
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.graph_service.http_timeout) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"Found user: {user_data.get('displayName', email)}")
                    return user_data
                else:
                    logger.warning(f"User not found: {email}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error finding user {email}: {str(e)}")
            return None

    async def _send_task_email(self, access_token: str, to_email: str, task: str,
                              meeting_title: str, due_date: datetime, priority: str) -> bool:
        """Send task assignment email"""
        subject = f"Action Item Assignment: {meeting_title}"
        
        priority_color = {
            "high": "#ff4444",
            "medium": "#ff8800", 
            "low": "#00cc44"
        }.get(priority, "#00cc44")
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2 style="color: #0078d4;">Task Assignment from Meeting</h2>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Meeting: {meeting_title}</h3>
                
                <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h4 style="color: #333;">Action Item Assigned to You:</h4>
                    <p style="font-size: 16px; font-weight: bold;">{task}</p>
                </div>
                
                <div style="margin: 15px 0;">
                    <p><strong>Due Date:</strong> {due_date.strftime('%B %d, %Y')}</p>
                    <p><strong>Priority:</strong> 
                       <span style="color: {priority_color}; font-weight: bold; text-transform: uppercase;">{priority}</span>
                    </p>
                </div>
            </div>
            
            <p>This task was automatically assigned from the Minutes of Meeting. 
               Please complete it by the due date and update the team on your progress.</p>
            
            <p style="color: #666; font-size: 12px;">
                This is an automated message from the MOM Automation Tool.
            </p>
        </body>
        </html>
        """
        
        try:
            result = await self.graph_service.send_email(
                access_token=access_token,
                to_email=to_email,
                subject=subject,
                body=body
            )
            
            logger.info(f"Task assignment email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send task email to {to_email}: {str(e)}")
            return False

    def calculate_task_metrics(self, assigned_tasks: List[Dict]) -> Dict:
        """Calculate task assignment metrics"""
        total_tasks = len(assigned_tasks)
        planner_tasks = len([t for t in assigned_tasks if t.get("status") == "assigned_to_planner"])
        email_tasks = len([t for t in assigned_tasks if t.get("status") == "email_sent"])
        failed_tasks = len([t for t in assigned_tasks if t.get("status") == "failed"])
        
        priority_counts = {}
        for task in assigned_tasks:
            priority = task.get("priority", "medium")
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        return {
            "total_tasks": total_tasks,
            "planner_tasks": planner_tasks,
            "email_tasks": email_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": (planner_tasks + email_tasks) / total_tasks * 100 if total_tasks > 0 else 0,
            "priority_distribution": priority_counts
        }