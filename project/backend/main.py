from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import uvicorn
import logging
import asyncio
from contextlib import asynccontextmanager

from database import engine, Base
from routers import auth, meetings, analytics, tasks, mom_edit, transcription
from ms_graph_service import MSGraphService
from transcript_scheduler import start_automatic_transcript_fetching, stop_automatic_transcript_fetching

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    
    # Start automatic transcript fetching in background
    transcript_task = None
    try:
        transcript_task = asyncio.create_task(start_automatic_transcript_fetching())
        logger.info("Automatic transcript fetching started")
    except Exception as e:
        logger.error(f"Failed to start transcript scheduler: {str(e)}")
    
    yield
    
    # Cleanup on shutdown
    try:
        stop_automatic_transcript_fetching()
        if transcript_task and not transcript_task.done():
            transcript_task.cancel()
            try:
                await transcript_task
            except asyncio.CancelledError:
                pass
        logger.info("Transcript scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping transcript scheduler: {str(e)}")
    
    logger.info("Application shutdown")

app = FastAPI(
    title="Microsoft Teams MOM Automation Tool",
    description="Automated Minutes of Meeting generation and task assignment for Microsoft Teams",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["Meetings"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(mom_edit.router, prefix="/api/mom", tags=["MOM Editing"])
app.include_router(transcription.router, tags=["Transcription"])

@app.get("/")
async def root():
    return {"message": "Microsoft Teams MOM Automation Tool API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "MOM Automation Tool"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )