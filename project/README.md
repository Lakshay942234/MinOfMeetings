# Microsoft Teams MOM Automation Tool

A comprehensive full-stack application that integrates with Microsoft Teams to automate Minutes of Meeting (MOM) generation and task assignment using AI and Microsoft Graph API.

## 🚀 Features

### Core Functionality
- **Automatic Meeting Data Capture**: Sync Microsoft Teams meetings with transcript extraction
- **AI-Powered MOM Generation**: Generate structured Minutes of Meeting using GPT API
- **Task Assignment**: Automatically assign action items via Microsoft Planner or email
- **Analytics Dashboard**: Track meeting costs, productivity metrics, and insights
- **Microsoft OAuth2 Integration**: Secure authentication with proper token management

### Key Capabilities
- Real-time meeting synchronization from Microsoft Teams
- Advanced AI processing for extracting key decisions and action items
- Automated task assignment with priority management
- Comprehensive analytics with interactive charts
- Responsive design for all device sizes
- Production-ready architecture with proper error handling

## 🏗️ Architecture

### Backend (Python FastAPI)
- **FastAPI** web framework with async support
- **SQLAlchemy** ORM with PostgreSQL database
- **Microsoft Graph API** integration for Teams data
- **OpenAI API** for AI-powered MOM generation
- Modular architecture with separate service layers

### Frontend (React + TypeScript)
- **React 18** with TypeScript for type safety
- **Tailwind CSS** for styling with Microsoft Fluent design
- **Recharts** for interactive analytics visualizations
- **React Router** for navigation
- Context API for state management

### Database Schema
```sql
-- Core tables
meetings_raw: Raw meeting data from Teams
mom_structured: AI-generated structured MOMs
mom_analytics: Meeting metrics and costs
hr_data: Employee salary information
user_tokens: OAuth token storage
```

## 🔧 Setup Instructions

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL database
- Microsoft 365 tenant with admin access
- OpenAI API key

### 1. Microsoft App Registration
1. Go to [Azure App Registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. Click "New registration"
3. Configure:
   - **Name**: MOM Automation Tool
   - **Redirect URI**: `http://localhost:8000/api/auth/callback`
   - **API permissions**: 
     - `Calendars.Read`
     - `OnlineMeetings.Read.All`
     - `Calls.AccessMedia.All`
     - `TeamsTab.Read.All`
     - `Tasks.ReadWrite`
     - `User.Read.All`
     - `Mail.Send`
4. Generate client secret
5. Note down Client ID, Client Secret, and Tenant ID

### 2. Backend Setup

```bash
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
```

### 3. Frontend Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

### 4. Database Setup

```sql
-- Create database
CREATE DATABASE mom_automation;

-- Create user (optional)
CREATE USER mom_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE mom_automation TO mom_user;
```

## 📋 Usage Guide

### 1. Authentication
1. Open the application in your browser
2. Click "Sign in with Microsoft"
3. Complete OAuth2 flow
4. You'll be redirected to the dashboard

### 2. Sync Meetings
1. From the Dashboard, click "Sync Meetings"
2. The system will fetch your recent Teams meetings
3. Meetings appear in the Meetings page

### 3. Generate MOMs
1. Go to the Meetings page
2. Select a meeting from the list
3. Click "Generate MOM" 
4. AI will process the transcript and create structured minutes
5. Export the MOM as needed

### 4. Assign Tasks
1. After generating a MOM, go to the Tasks page
2. Select the meeting with action items
3. Click "Assign Tasks"
4. Tasks will be created in Microsoft Planner or sent via email

### 5. View Analytics
1. Navigate to the Analytics page
2. View meeting trends, costs, and productivity metrics
3. Filter by date range and department
4. Export reports as needed

## 🔌 API Endpoints

### Authentication
- `GET /api/auth/login` - Get Microsoft OAuth URL
- `GET /api/auth/callback` - Handle OAuth callback
- `POST /api/auth/refresh` - Refresh access token

### Meetings
- `POST /api/meetings/sync/{user_id}` - Sync meetings from Teams
- `GET /api/meetings` - List meetings
- `GET /api/meetings/{meeting_id}` - Get meeting details
- `POST /api/meetings/generate-mom/{meeting_id}` - Generate MOM

### Analytics
- `GET /api/analytics/summary` - Get summary statistics
- `GET /api/analytics/meetings-per-user` - User activity stats
- `GET /api/analytics/department-analytics` - Department metrics
- `GET /api/analytics/trends` - Meeting trends over time

### Tasks
- `POST /api/tasks/assign/{meeting_id}` - Assign tasks from MOM
- `GET /api/tasks/action-items/{meeting_id}` - Get action items
- `GET /api/tasks/metrics` - Task assignment metrics

## 🔐 Security Features

- **OAuth2 Authentication**: Secure Microsoft integration
- **Token Management**: Automatic token refresh
- **Data Encryption**: Secure storage of sensitive information
- **CORS Protection**: Proper cross-origin resource sharing
- **Input Validation**: Comprehensive request validation
- **Rate Limiting**: API abuse prevention

## 📊 Microsoft Graph API Integration

### Meeting Data Capture
```python
# Fetch meetings from Calendar API
GET https://graph.microsoft.com/v1.0/me/calendarview

# Get online meeting details
GET https://graph.microsoft.com/v1.0/me/onlineMeetings/{meetingId}

# Fetch transcripts (Teams Premium)
GET https://graph.microsoft.com/beta/communications/callRecords/{callRecordId}/transcripts
```

### Task Assignment
```python
# Create Planner task
POST https://graph.microsoft.com/v1.0/planner/tasks

# Send email notification
POST https://graph.microsoft.com/v1.0/me/sendMail
```

## 🤖 AI Integration

The system uses OpenAI's GPT-4 to process meeting transcripts and generate structured MOMs:

```python
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
```

## 🚀 Deployment

### Production Environment Variables
```bash
DATABASE_URL=postgresql://user:pass@prod-db:5432/mom_automation
MICROSOFT_CLIENT_ID=prod_client_id
MICROSOFT_CLIENT_SECRET=prod_client_secret
MICROSOFT_TENANT_ID=your_tenant_id
OPENAI_API_KEY=prod_openai_key
SECRET_KEY=production_secret_key
DEBUG=false
LOG_LEVEL=INFO
```

### Docker Deployment
```dockerfile
# Dockerfile example for backend
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest tests/

# Frontend tests
npm test

# Integration tests
pytest tests/integration/
```

## 📈 Monitoring and Logging

- Comprehensive logging for all API calls and errors
- Performance monitoring for AI processing
- Meeting sync success/failure tracking
- Task assignment delivery confirmation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with proper tests
4. Submit a pull request
5. Ensure all CI checks pass

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the documentation
2. Search existing issues
3. Create a new issue with detailed information
4. Contact the development team

## 🔄 Roadmap

- [ ] Microsoft Teams bot integration
- [ ] Advanced analytics with ML insights
- [ ] Multi-language support
- [ ] Mobile application
- [ ] Integration with other meeting platforms
- [ ] Advanced task management features
- [ ] Real-time collaboration tools