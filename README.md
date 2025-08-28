Microsoft Teams MOM Automation Tool
A comprehensive full-stack application that integrates with Microsoft Teams to automate Minutes of Meeting (MOM) generation and task assignment using AI and Microsoft Graph API.

🚀 Features
Core Functionality
Automatic Meeting Data Capture: Sync Microsoft Teams meetings with transcript extraction
AI-Powered MOM Generation: Generate structured Minutes of Meeting using GPT API
Task Assignment: Automatically assign action items via Microsoft Planner or email
Analytics Dashboard: Track meeting costs, productivity metrics, and insights
Microsoft OAuth2 Integration: Secure authentication with proper token management
Key Capabilities
Real-time meeting synchronization from Microsoft Teams
Advanced AI processing for extracting key decisions and action items
Automated task assignment with priority management
Comprehensive analytics with interactive charts
Responsive design for all device sizes
Production-ready architecture with proper error handling
🏗️ Architecture
Backend (Python FastAPI)
FastAPI web framework with async support
SQLAlchemy ORM with PostgreSQL database
Microsoft Graph API integration for Teams data
OpenAI API for AI-powered MOM generation
Modular architecture with separate service layers
Frontend (React + TypeScript)
React 18 with TypeScript for type safety
Tailwind CSS for styling with Microsoft Fluent design
Recharts for interactive analytics visualizations
React Router for navigation
Context API for state management
Database Schema
-- Core tables
meetings_raw: Raw meeting data from Teams
mom_structured: AI-generated structured MOMs
mom_analytics: Meeting metrics and costs
hr_data: Employee salary information
user_tokens: OAuth token storage
🔧 Setup Instructions
Prerequisites
Python 3.9+
Node.js 18+
PostgreSQL database
Microsoft 365 tenant with admin access
OpenAI API key
1. Microsoft App Registration
Go to Azure App Registrations
Click "New registration"
Configure:
Name: MOM Automation Tool
Redirect URI: http://localhost:8000/api/auth/callback
API permissions:
Calendars.Read
OnlineMeetings.Read.All
Calls.AccessMedia.All
TeamsTab.Read.All
Tasks.ReadWrite
User.Read.All
Mail.Send
Generate client secret
Note down Client ID, Client Secret, and Tenant ID
2. Backend Setup
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp backend/.env.example backend/.env
# Edit .env with your credentials:
# - DATABASE_URL
# - MICROSOFT_CLIENT_ID
# - MICROSOFT_CLIENT_SECRET
# - MICROSOFT_TENANT_ID
# - OPENAI_API_KEY

# Run database migrations
cd backend
alembic upgrade head

# Start the backend server
python main.py
3. Frontend Setup
# Install dependencies
npm install

# Start development server
npm run dev
4. Database Setup
-- Create database
CREATE DATABASE mom_automation;

-- Create user (optional)
CREATE USER mom_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE mom_automation TO mom_user;
📋 Usage Guide
1. Authentication
Open the application in your browser
Click "Sign in with Microsoft"
Complete OAuth2 flow
You'll be redirected to the dashboard
2. Sync Meetings
From the Dashboard, click "Sync Meetings"
The system will fetch your recent Teams meetings
Meetings appear in the Meetings page
3. Generate MOMs
Go to the Meetings page
Select a meeting from the list
Click "Generate MOM"
AI will process the transcript and create structured minutes
Export the MOM as needed
4. Assign Tasks
After generating a MOM, go to the Tasks page
Select the meeting with action items
Click "Assign Tasks"
Tasks will be created in Microsoft Planner or sent via email
5. View Analytics
Navigate to the Analytics page
View meeting trends, costs, and productivity metrics
Filter by date range and department
Export reports as needed
🔌 API Endpoints
Authentication
GET /api/auth/login - Get Microsoft OAuth URL
GET /api/auth/callback - Handle OAuth callback
POST /api/auth/refresh - Refresh access token
Meetings
POST /api/meetings/sync/{user_id} - Sync meetings from Teams
GET /api/meetings - List meetings
GET /api/meetings/{meeting_id} - Get meeting details
POST /api/meetings/generate-mom/{meeting_id} - Generate MOM
Analytics
GET /api/analytics/summary - Get summary statistics
GET /api/analytics/meetings-per-user - User activity stats
GET /api/analytics/department-analytics - Department metrics
GET /api/analytics/trends - Meeting trends over time
Tasks
POST /api/tasks/assign/{meeting_id} - Assign tasks from MOM
GET /api/tasks/action-items/{meeting_id} - Get action items
GET /api/tasks/metrics - Task assignment metrics
🔐 Security Features
OAuth2 Authentication: Secure Microsoft integration
Token Management: Automatic token refresh
Data Encryption: Secure storage of sensitive information
CORS Protection: Proper cross-origin resource sharing
Input Validation: Comprehensive request validation
Rate Limiting: API abuse prevention
📊 Microsoft Graph API Integration
Meeting Data Capture
# Fetch meetings from Calendar API
GET https://graph.microsoft.com/v1.0/me/calendarview

# Get online meeting details
GET https://graph.microsoft.com/v1.0/me/onlineMeetings/{meetingId}

# Fetch transcripts (Teams Premium)
GET https://graph.microsoft.com/beta/communications/callRecords/{callRecordId}/transcripts
Task Assignment
# Create Planner task
POST https://graph.microsoft.com/v1.0/planner/tasks

# Send email notification
POST https://graph.microsoft.com/v1.0/me/sendMail
🤖 AI Integration
The system uses OpenAI's GPT-4 to process meeting transcripts and generate structured MOMs:

# Example prompt for MOM generation
prompt = f"""
From the following meeting transcript, generate a structured JSON with:
- meeting_title
- date  
- agenda (list)
- key_decisions (list)
- action_items (list with task, assigned_to, due_date, priority)
- follow_up_points (list)

Transcript: {transcript_text}
Participants: {participants}
"""
🚀 Deployment
Production Environment Variables
DATABASE_URL=postgresql://user:pass@prod-db:5432/mom_automation
MICROSOFT_CLIENT_ID=prod_client_id
MICROSOFT_CLIENT_SECRET=prod_client_secret
MICROSOFT_TENANT_ID=your_tenant_id
OPENAI_API_KEY=prod_openai_key
SECRET_KEY=production_secret_key
DEBUG=false
LOG_LEVEL=INFO
Docker Deployment
# Dockerfile example for backend
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
🧪 Testing
# Backend tests
cd backend
pytest tests/

# Frontend tests
npm test

# Integration tests
pytest tests/integration/
📈 Monitoring and Logging
Comprehensive logging for all API calls and errors
Performance monitoring for AI processing
Meeting sync success/failure tracking
Task assignment delivery confirmation
🤝 Contributing
Fork the repository
Create a feature branch
Make changes with proper tests
Submit a pull request
Ensure all CI checks pass
📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

🆘 Support
For issues and questions:

Check the documentation
Search existing issues
Create a new issue with detailed information
Contact the development team
🔄 Roadmap
 Microsoft Teams bot integration
 Advanced analytics with ML insights
 Multi-language support
 Mobile application
 Integration with other meeting platforms
 Advanced task management features
 Real-time collaboration tools
