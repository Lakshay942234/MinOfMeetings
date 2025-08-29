#!/usr/bin/env python3
"""
Database migration script to add transcription status tracking columns
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add transcription status columns to meetings_raw table"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database URL
    database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/mom_automation")
    
    if not database_url or database_url == "postgresql://user:password@localhost/mom_automation":
        logger.error("DATABASE_URL not properly configured in .env file")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                # Check if columns already exist
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'meetings_raw' 
                    AND column_name IN ('transcription_status', 'transcription_method', 'mom_generated')
                """))
                
                existing_columns = [row[0] for row in result]
                logger.info(f"Existing columns: {existing_columns}")
                
                # Add transcription_status column if it doesn't exist
                if 'transcription_status' not in existing_columns:
                    logger.info("Adding transcription_status column...")
                    conn.execute(text("""
                        ALTER TABLE meetings_raw 
                        ADD COLUMN transcription_status VARCHAR DEFAULT 'pending'
                    """))
                    
                    # Update existing records based on transcript_text
                    conn.execute(text("""
                        UPDATE meetings_raw 
                        SET transcription_status = CASE 
                            WHEN transcript_text IS NULL OR transcript_text = '' OR transcript_text = 'Transcript not available' 
                            THEN 'pending'
                            ELSE 'completed'
                        END
                    """))
                    logger.info("✓ Added transcription_status column")
                else:
                    logger.info("transcription_status column already exists")
                
                # Add transcription_method column if it doesn't exist
                if 'transcription_method' not in existing_columns:
                    logger.info("Adding transcription_method column...")
                    conn.execute(text("""
                        ALTER TABLE meetings_raw 
                        ADD COLUMN transcription_method VARCHAR
                    """))
                    
                    # Set method based on existing transcript content
                    conn.execute(text("""
                        UPDATE meetings_raw 
                        SET transcription_method = CASE 
                            WHEN transcript_text LIKE '%[Transcribed using OpenAI Whisper from Teams recording%' THEN 'whisper_teams'
                            WHEN transcript_text LIKE '%[Transcribed using OpenAI Whisper from local file%' THEN 'whisper_local'
                            WHEN transcript_text LIKE '%[Transcribed using OpenAI Whisper%' THEN 'whisper'
                            WHEN transcript_text IS NOT NULL AND transcript_text != '' AND transcript_text != 'Transcript not available' THEN 'teams'
                            ELSE NULL
                        END
                    """))
                    logger.info("✓ Added transcription_method column")
                else:
                    logger.info("transcription_method column already exists")
                
                # Add mom_generated column if it doesn't exist
                if 'mom_generated' not in existing_columns:
                    logger.info("Adding mom_generated column...")
                    conn.execute(text("""
                        ALTER TABLE meetings_raw 
                        ADD COLUMN mom_generated BOOLEAN DEFAULT FALSE
                    """))
                    
                    # Update based on existing MOM records
                    conn.execute(text("""
                        UPDATE meetings_raw 
                        SET mom_generated = TRUE 
                        WHERE meeting_id IN (
                            SELECT DISTINCT meeting_id FROM mom_structured
                        )
                    """))
                    logger.info("✓ Added mom_generated column")
                else:
                    logger.info("mom_generated column already exists")
                
                # Commit transaction
                trans.commit()
                logger.info("✅ Migration completed successfully!")
                
                # Show summary
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_meetings,
                        COUNT(CASE WHEN transcription_status = 'pending' THEN 1 END) as pending,
                        COUNT(CASE WHEN transcription_status = 'processing' THEN 1 END) as processing,
                        COUNT(CASE WHEN transcription_status = 'completed' THEN 1 END) as completed,
                        COUNT(CASE WHEN transcription_status = 'failed' THEN 1 END) as failed,
                        COUNT(CASE WHEN mom_generated = TRUE THEN 1 END) as with_mom
                    FROM meetings_raw
                """))
                
                stats = result.fetchone()
                if stats:
                    logger.info(f"""
Migration Summary:
- Total meetings: {stats[0]}
- Pending transcription: {stats[1]}
- Processing: {stats[2]}
- Completed: {stats[3]}
- Failed: {stats[4]}
- With MOM: {stats[5]}
                    """)
                
                return True
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Migration failed, rolling back: {str(e)}")
                return False
                
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
