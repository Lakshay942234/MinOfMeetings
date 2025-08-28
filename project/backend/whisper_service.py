import whisper
import logging
import os
import tempfile
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
import torch
import ffmpeg
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class WhisperTranscriptionService:
    def __init__(self):
        """Initialize Whisper transcription service with configurable model"""
        # Model size options: tiny, base, small, medium, large
        self.model_name = os.getenv("WHISPER_MODEL", "base")
        self.device = os.getenv("WHISPER_DEVICE", "auto")  # auto, cpu, cuda
        self.language = os.getenv("WHISPER_LANGUAGE", None)  # None for auto-detect
        self.model = None
        self._model_loaded = False
        
        # Configure device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"WhisperTranscriptionService initialized with model={self.model_name}, device={self.device}")
    
    def _load_model(self):
        """Lazy load the Whisper model"""
        if not self._model_loaded:
            try:
                logger.info(f"Loading Whisper model: {self.model_name}")
                self.model = whisper.load_model(self.model_name, device=self.device)
                self._model_loaded = True
                logger.info("Whisper model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                raise
    
    async def transcribe_audio_file(self, audio_file_path: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Transcribe an audio file using Whisper
        
        Args:
            audio_file_path: Path to the audio file
            **kwargs: Additional options for Whisper (temperature, beam_size, etc.)
            
        Returns:
            Dictionary containing transcription results or None if failed
        """
        try:
            # Load model if not already loaded
            self._load_model()
            
            if not os.path.exists(audio_file_path):
                logger.error(f"Audio file not found: {audio_file_path}")
                return None
            
            logger.info(f"Starting transcription of: {audio_file_path}")
            
            # Prepare transcription options
            options = {
                "language": self.language,
                "task": "transcribe",  # or "translate" for translation to English
                "verbose": False,
                **kwargs
            }
            
            # Remove None values
            options = {k: v for k, v in options.items() if v is not None}
            
            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self.model.transcribe(audio_file_path, **options)
            )
            
            logger.info(f"Transcription completed. Text length: {len(result.get('text', ''))}")
            
            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language"),
                "segments": result.get("segments", []),
                "duration": self._get_audio_duration(audio_file_path)
            }
            
        except Exception as e:
            logger.error(f"Error transcribing audio file {audio_file_path}: {e}")
            return None
    
    async def transcribe_audio_bytes(self, audio_bytes: bytes, filename: str = "audio.wav", **kwargs) -> Optional[Dict[str, Any]]:
        """
        Transcribe audio from bytes data
        
        Args:
            audio_bytes: Raw audio data
            filename: Original filename (for format detection)
            **kwargs: Additional options for Whisper
            
        Returns:
            Dictionary containing transcription results or None if failed
        """
        temp_file = None
        try:
            # Create temporary file
            suffix = Path(filename).suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            # Transcribe the temporary file
            result = await self.transcribe_audio_file(temp_file_path, **kwargs)
            
            return result
            
        except Exception as e:
            logger.error(f"Error transcribing audio bytes: {e}")
            return None
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {e}")
    
    async def transcribe_url(self, audio_url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Download and transcribe audio from URL
        
        Args:
            audio_url: URL to audio file
            **kwargs: Additional options for Whisper
            
        Returns:
            Dictionary containing transcription results or None if failed
        """
        import httpx
        
        temp_file = None
        try:
            logger.info(f"Downloading audio from URL: {audio_url}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                
                # Determine file extension from URL or content type
                content_type = response.headers.get("content-type", "")
                if "audio/wav" in content_type:
                    suffix = ".wav"
                elif "audio/mp3" in content_type or "audio/mpeg" in content_type:
                    suffix = ".mp3"
                elif "audio/mp4" in content_type or "audio/m4a" in content_type:
                    suffix = ".m4a"
                else:
                    suffix = ".wav"  # Default
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
            
            # Transcribe the downloaded file
            result = await self.transcribe_audio_file(temp_file_path, **kwargs)
            
            return result
            
        except Exception as e:
            logger.error(f"Error transcribing audio from URL {audio_url}: {e}")
            return None
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {e}")
    
    def _get_audio_duration(self, audio_file_path: str) -> Optional[float]:
        """Get audio file duration in seconds"""
        try:
            probe = ffmpeg.probe(audio_file_path)
            duration = float(probe['streams'][0]['duration'])
            return duration
        except Exception as e:
            logger.warning(f"Could not get audio duration: {e}")
            return None
    
    async def convert_audio_format(self, input_path: str, output_path: str, target_format: str = "wav") -> bool:
        """
        Convert audio file to a different format using ffmpeg
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output file
            target_format: Target format (wav, mp3, etc.)
            
        Returns:
            True if conversion successful, False otherwise
        """
        try:
            logger.info(f"Converting {input_path} to {target_format}")
            
            # Run conversion in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: (
                    ffmpeg
                    .input(input_path)
                    .output(output_path, format=target_format, acodec='pcm_s16le', ac=1, ar='16000')
                    .overwrite_output()
                    .run(quiet=True)
                )
            )
            
            logger.info(f"Audio conversion completed: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting audio format: {e}")
            return False
    
    def get_supported_formats(self) -> list:
        """Get list of supported audio formats"""
        return [
            ".wav", ".mp3", ".mp4", ".m4a", ".flac", ".ogg", 
            ".wma", ".aac", ".opus", ".webm", ".mkv", ".avi"
        ]
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "language": self.language,
            "model_loaded": self._model_loaded,
            "supported_formats": self.get_supported_formats()
        }

# Global instance
whisper_service = WhisperTranscriptionService()
