# OpenAI Whisper Configuration

This document describes the environment variables for configuring OpenAI Whisper transcription in the MinOfMeetings application.

## Required Dependencies

The following packages have been added to `requirements.txt`:
- `openai-whisper==20231117` - OpenAI Whisper for speech-to-text
- `torch==2.1.0` - PyTorch for ML operations
- `torchaudio==2.1.0` - Audio processing for PyTorch
- `ffmpeg-python==0.2.0` - Audio format conversion

## Environment Variables

Add these variables to your `.env` file:

### Whisper Service Configuration

```bash
# Whisper model size (tiny, base, small, medium, large)
# Larger models are more accurate but slower and require more memory
WHISPER_MODEL=small

# Device to use for Whisper (auto, cpu, cuda)
# 'auto' will use CUDA if available, otherwise CPU
WHISPER_DEVICE=auto

# Default language for transcription (optional)
# Leave empty for auto-detection, or use language codes like 'en', 'es', 'fr'
WHISPER_LANGUAGE=

# Enable Whisper as PRIMARY transcription method (recommended for Hindi and multilingual support)
USE_WHISPER_FALLBACK=true

# Enable Teams transcript as fallback when Whisper fails (disabled by default since Teams doesn't handle Hindi well)
USE_TEAMS_TRANSCRIPT_FALLBACK=false

# Enable local file fallback if Teams recording download fails
USE_LOCAL_FILE_FALLBACK=true

# Directories to search for meeting audio files (comma-separated)
# Example: /path/to/recordings,/another/path/recordings
MEETING_AUDIO_DIRECTORIES=
```

### Model Size Guide

- **tiny**: Fastest, least accurate, ~39 MB
- **base**: Good balance, ~74 MB (recommended for most use cases)
- **small**: Better accuracy, ~244 MB
- **medium**: High accuracy, ~769 MB
- **large**: Best accuracy, ~1550 MB

### Device Configuration

- **auto**: Automatically detects and uses CUDA if available, falls back to CPU
- **cpu**: Force CPU usage (slower but works on any machine)
- **cuda**: Force GPU usage (requires NVIDIA GPU with CUDA support)

## API Endpoints

The following new endpoints are available for Whisper transcription:

### Upload Audio File
```
POST /api/transcription/upload
```
Upload an audio file for transcription. Supports most audio/video formats.

### Transcribe from URL
```
POST /api/transcription/url
```
Transcribe audio from a publicly accessible URL.

### Transcribe from Teams Recording
```
POST /api/transcription/meeting/{meeting_id}/transcribe-from-teams
```
**NEW**: Directly download and transcribe Teams meeting recordings using Whisper.

### Service Status
```
GET /api/transcription/status
```
Get current Whisper service status and configuration.

### Retranscribe Meeting
```
POST /api/transcription/meeting/{meeting_id}/retranscribe
```
Retranscribe a specific meeting using Whisper from local files.

## Audio File Organization

For automatic transcription fallback, organize your audio files in directories specified by `MEETING_AUDIO_DIRECTORIES`. The system will search for files using these patterns:

1. Meeting ID (exact match)
2. Meeting title with spaces replaced by underscores
3. Date and time format: `YYYYMMDD_HHMM_MeetingTitle`
4. Date and time only: `YYYYMMDD_HHMM`

Supported audio formats:
- .wav, .mp3, .mp4, .m4a, .flac, .ogg, .wma, .aac, .opus, .webm, .mkv, .avi

## Installation Notes

1. Install system dependencies:
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install ffmpeg
   
   # macOS
   brew install ffmpeg
   
   # Windows
   # Download ffmpeg from https://ffmpeg.org/download.html
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. For GPU acceleration (optional):
   - Install CUDA toolkit
   - Ensure PyTorch is installed with CUDA support

## Usage Examples

### Whisper-First Transcription (Recommended for Hindi)
The system now uses **Whisper as the PRIMARY transcription method** with excellent multilingual support:

1. **Primary**: Downloads Teams recording and transcribes with Whisper (supports Hindi, English, and 90+ languages)
2. **Optional Fallback**: Microsoft Graph API transcript fetching (disabled by default, poor Hindi support)
3. **Final Fallback**: Local audio file transcription (if Teams recording unavailable)

This happens automatically when:
- `USE_WHISPER_FALLBACK=true` (Whisper as primary method)
- `USE_TEAMS_TRANSCRIPT_FALLBACK=false` (Teams transcripts disabled)
- User has proper Microsoft Graph permissions for recordings

### Manual Upload
```python
import requests

files = {'file': open('meeting.mp3', 'rb')}
data = {'meeting_id': 'meeting-123', 'language': 'en'}
response = requests.post('http://localhost:8000/api/transcription/upload', files=files, data=data)
```

### Direct Teams Recording Download and Transcription (Hindi Support)
```python
import requests

# Directly download and transcribe Teams recording with Hindi language detection
response = requests.post(
    'http://localhost:8000/api/transcription/meeting/meeting-123/transcribe-from-teams',
    json={'language': 'hi'}  # 'hi' for Hindi, or leave empty for auto-detection
)
```

## Troubleshooting

### Common Issues

1. **"No module named 'whisper'"**
   - Run: `pip install openai-whisper`

2. **"CUDA out of memory"**
   - Use a smaller model (tiny/base) or switch to CPU
   - Set `WHISPER_DEVICE=cpu`

3. **"ffmpeg not found"**
   - Install ffmpeg system package
   - Ensure ffmpeg is in system PATH

4. **Slow transcription**
   - Use GPU if available (`WHISPER_DEVICE=cuda`)
   - Use smaller model size
   - Reduce audio file size/duration

### Performance Tips

- Use GPU acceleration for faster transcription
- Choose appropriate model size for your accuracy/speed needs
- Convert audio to WAV format for best compatibility
- Keep audio files under 500MB for upload endpoint
