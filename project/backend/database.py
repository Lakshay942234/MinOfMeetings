from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, JSON, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/mom_automation")

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class MeetingRaw(Base):
    __tablename__ = "meetings_raw"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, unique=True, index=True)
    title = Column(String)
    date = Column(DateTime)
    transcript_text = Column(Text)
    participants_json = Column(JSON)
    duration_minutes = Column(Integer)
    transcription_status = Column(String, default="pending")  # pending, processing, completed, failed
    transcription_method = Column(String, nullable=True)  # whisper, teams, local_file
    mom_generated = Column(Boolean, default=False)  # Track if MOM has been generated
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class MOMStructured(Base):
    __tablename__ = "mom_structured"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    meeting_title = Column(String)
    date = Column(DateTime)
    agenda = Column(JSON)
    key_decisions = Column(JSON)
    action_items = Column(JSON)
    follow_up_points = Column(JSON)
    created_at = Column(DateTime, default=func.now())

class MOMAnalytics(Base):
    __tablename__ = "mom_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    date = Column(DateTime)
    duration_minutes = Column(Integer)
    participants_count = Column(Integer)
    participants_list = Column(JSON)
    total_cost = Column(Float)
    department = Column(String)
    created_at = Column(DateTime, default=func.now())

class HRData(Base):
    __tablename__ = "hr_data"
    
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, unique=True, index=True)
    department = Column(String)
    hourly_salary = Column(Float)
    display_name = Column(String)

class UserTokens(Base):
    __tablename__ = "user_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class TaskItem(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    task = Column(Text)
    assigned_to = Column(String, index=True)
    due_date = Column(DateTime, nullable=True)
    priority = Column(String, default="medium")
    status = Column(String, default="pending")  # pending, in_progress, completed, blocked
    source = Column(String, default="local")  # local, planner, email
    external_id = Column(String, nullable=True)  # e.g., planner task id
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# Dependency to get database session
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()