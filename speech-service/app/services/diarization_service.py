"""
Speaker Diarization service implementation.

This module provides speaker diarization functionality using pyannote.audio,
following Clean Architecture principles with dependency injection.
"""

import asyncio
import time
import numpy as np
import tempfile
import os
from typing import Dict, Any, Optional, List
import structlog
from pathlib import Path
import io

from ..interfaces.services import IDiarizationService, DiarizationServiceError
from ..config import DiarizationSettings


class PyAnnoteDiarizationService(IDiarizationService):
    """
    PyAnnote.audio diarization service implementation.
    
    Provides speaker diarization using pyannote.audio pipeline
    with async/await support and structured logging.
    """
    
    def __init__(self, config: DiarizationSettings):
        """
        Initialize the diarization service.
        
        Args:
            config: Diarization configuration settings
        """
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Model and state
        self.pipeline = None
        self.model_name = config.model_name
        self.auth_token = config.auth_token
        self.min_speakers = config.min_speakers
        self.max_speakers = config.max_speakers
        self.clustering_method = config.clustering_method
        
        self.logger.info(
            "Diarization service configured",
            model_name=self.model_name,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
            clustering_method=self.clustering_method
        )
    
    async def initialize(self) -> None:
        """
        Initialize the diarization service and load models.
        
        Raises:
            DiarizationServiceError: If initialization fails
        """
        try:
            self.logger.info("Initializing PyAnnote diarization pipeline")
            
            # Load PyAnnote pipeline in executor to avoid blocking
            loop = asyncio.get_event_loop()
            self.pipeline = await loop.run_in_executor(
                None, 
                self._load_pyannote_pipeline
            )
            
            self.logger.info("PyAnnote diarization pipeline loaded successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize diarization service", error=str(e))
            raise DiarizationServiceError(f"Diarization initialization failed: {e}")
    
    def _load_pyannote_pipeline(self):
        """Load PyAnnote diarization pipeline (sync operation)."""
        try:
            from pyannote.audio import Pipeline
            
            # Load the pipeline
            pipeline = Pipeline.from_pretrained(
                self.model_name,
                use_auth_token=self.auth_token
            )
            
            return pipeline
            
        except Exception as e:
            raise DiarizationServiceError(f"Failed to load PyAnnote pipeline: {e}")
    
    async def diarize(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000,
        num_speakers: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform speaker diarization on audio data.
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate in Hz  
            num_speakers: Optional hint for number of speakers
            
        Returns:
            Dictionary containing:
                - speakers: List of unique speaker identifiers
                - segments: List of segments with speaker, start, end times
                - speaker_count: int total number of detected speakers
                
        Raises:
            DiarizationServiceError: If diarization fails
        """
        if self.pipeline is None:
            raise DiarizationServiceError("Diarization pipeline not initialized")
        
        start_time = time.time()
        
        try:
            # Create temporary audio file for pyannote processing
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                
                # Convert bytes to audio file
                await self._write_audio_file(audio_data, sample_rate, temp_path)
                
                # Run diarization in executor
                loop = asyncio.get_event_loop()
                diarization_result = await loop.run_in_executor(
                    None,
                    self._run_diarization,
                    temp_path,
                    num_speakers
                )
                
                # Clean up temporary file
                os.unlink(temp_path)
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.debug(
                "Diarization completed",
                speaker_count=diarization_result["speaker_count"],
                segment_count=len(diarization_result["segments"]),
                processing_time_ms=processing_time,
                audio_duration_ms=len(audio_data) / (sample_rate * 2) * 1000
            )
            
            return diarization_result
            
        except Exception as e:
            self.logger.error("Diarization failed", error=str(e))
            raise DiarizationServiceError(f"Diarization failed: {e}")
    
    async def _write_audio_file(
        self, 
        audio_data: bytes, 
        sample_rate: int, 
        file_path: str
    ) -> None:
        """
        Write audio bytes to WAV file.
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
            file_path: Output file path
        """
        try:
            import wave
            
            # Convert bytes to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            
            # Write WAV file
            with wave.open(file_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_np.tobytes())
                
        except Exception as e:
            raise DiarizationServiceError(f"Failed to write audio file: {e}")
    
    def _run_diarization(
        self, 
        audio_file_path: str, 
        num_speakers: Optional[int]
    ) -> Dict[str, Any]:
        """
        Run diarization on audio file (sync operation).
        
        Args:
            audio_file_path: Path to audio file
            num_speakers: Optional number of speakers hint
            
        Returns:
            Diarization results
        """
        try:
            # Set up diarization parameters
            params = {}
            
            if num_speakers:
                params["num_speakers"] = num_speakers
            else:
                params["min_speakers"] = self.min_speakers
                params["max_speakers"] = self.max_speakers
            
            # Run diarization
            diarization = self.pipeline(audio_file_path, **params)
            
            # Extract results
            speakers = set()
            segments = []
            
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers.add(speaker)
                
                segment_data = {
                    "speaker": speaker,
                    "start": turn.start,
                    "end": turn.end,
                    "duration": turn.end - turn.start,
                    "confidence": 1.0  # PyAnnote doesn't provide per-segment confidence
                }
                
                segments.append(segment_data)
            
            # Sort segments by start time
            segments.sort(key=lambda x: x["start"])
            
            speakers_list = sorted(list(speakers))
            
            return {
                "speakers": speakers_list,
                "segments": segments,
                "speaker_count": len(speakers_list),
                "total_speech_time": sum(s["duration"] for s in segments),
                "speaker_stats": self._calculate_speaker_stats(segments, speakers_list)
            }
            
        except Exception as e:
            raise DiarizationServiceError(f"PyAnnote diarization failed: {e}")
    
    def _calculate_speaker_stats(
        self, 
        segments: List[Dict[str, Any]], 
        speakers: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate speaking time statistics for each speaker.
        
        Args:
            segments: List of segment dictionaries
            speakers: List of speaker identifiers
            
        Returns:
            Dictionary with speaker statistics
        """
        stats = {}
        
        for speaker in speakers:
            speaker_segments = [s for s in segments if s["speaker"] == speaker]
            total_time = sum(s["duration"] for s in speaker_segments)
            segment_count = len(speaker_segments)
            avg_segment_duration = total_time / segment_count if segment_count > 0 else 0
            
            stats[speaker] = {
                "total_speaking_time": total_time,
                "segment_count": segment_count,
                "average_segment_duration": avg_segment_duration,
                "speaking_percentage": 0.0  # Will be calculated later if needed
            }
        
        # Calculate speaking percentages
        total_speaking_time = sum(stats[s]["total_speaking_time"] for s in speakers)
        if total_speaking_time > 0:
            for speaker in speakers:
                stats[speaker]["speaking_percentage"] = (
                    stats[speaker]["total_speaking_time"] / total_speaking_time * 100
                )
        
        return stats
    
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        try:
            if self.pipeline:
                # Clear pipeline from memory
                del self.pipeline
                self.pipeline = None
            
            self.logger.info("Diarization service cleaned up")
            
        except Exception as e:
            self.logger.error("Error during diarization cleanup", error=str(e))
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Model information dictionary
        """
        return {
            "model_name": self.model_name,
            "min_speakers": self.min_speakers,
            "max_speakers": self.max_speakers,
            "clustering_method": self.clustering_method,
            "is_initialized": self.pipeline is not None,
            "auth_token_provided": self.auth_token is not None
        }


class MockDiarizationService(IDiarizationService):
    """
    Mock diarization service for testing and development.
    
    Provides deterministic diarization results for testing purposes
    without requiring actual model loading.
    """
    
    def __init__(self, config: DiarizationSettings):
        """Initialize mock diarization service."""
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize mock service."""
        self.is_initialized = True
        self.logger.info("Mock diarization service initialized")
    
    async def diarize(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000,
        num_speakers: Optional[int] = None
    ) -> Dict[str, Any]:
        """Mock diarization."""
        if not self.is_initialized:
            raise DiarizationServiceError("Mock diarization service not initialized")
        
        # Mock logic: generate speakers based on audio length
        audio_length = len(audio_data)
        duration = audio_length / (sample_rate * 2)  # Assuming 16-bit samples
        
        # Determine number of speakers
        if num_speakers:
            speaker_count = min(num_speakers, self.config.max_speakers)
        else:
            # Mock: more speakers for longer audio
            speaker_count = min(2 + (audio_length // 50000), self.config.max_speakers)
            speaker_count = max(speaker_count, self.config.min_speakers)
        
        # Create mock speakers
        speakers = [f"SPEAKER_{i:02d}" for i in range(speaker_count)]
        
        # Create mock segments
        segments = []
        segment_duration = duration / (speaker_count * 2)  # Each speaker gets multiple segments
        current_time = 0.0
        
        for i in range(speaker_count * 2):  # 2 segments per speaker
            speaker = speakers[i % speaker_count]
            start_time = current_time
            end_time = current_time + segment_duration
            
            segments.append({
                "speaker": speaker,
                "start": start_time,
                "end": end_time,
                "duration": segment_duration,
                "confidence": 0.95 - (i * 0.02)  # Slight confidence variation
            })
            
            current_time = end_time
        
        # Calculate speaker stats
        speaker_stats = {}
        for speaker in speakers:
            speaker_segments = [s for s in segments if s["speaker"] == speaker]
            total_time = sum(s["duration"] for s in speaker_segments)
            
            speaker_stats[speaker] = {
                "total_speaking_time": total_time,
                "segment_count": len(speaker_segments),
                "average_segment_duration": total_time / len(speaker_segments),
                "speaking_percentage": (total_time / duration) * 100
            }
        
        self.logger.debug(
            "Mock diarization",
            speaker_count=speaker_count,
            segment_count=len(segments),
            duration=duration,
            audio_length=audio_length
        )
        
        return {
            "speakers": speakers,
            "segments": segments,
            "speaker_count": speaker_count,
            "total_speech_time": duration,
            "speaker_stats": speaker_stats
        }
    
    async def cleanup(self) -> None:
        """Clean up mock service."""
        self.is_initialized = False
        self.logger.info("Mock diarization service cleaned up")