"""
Automatic Speech Recognition (ASR) service implementation.

This module provides ASR functionality using Faster-Whisper model,
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

from ..interfaces.services import IASRService, ASRServiceError
from ..config import ASRSettings


class FasterWhisperASRService(IASRService):
    """
    Faster-Whisper ASR service implementation.
    
    Provides speech-to-text transcription using the Faster-Whisper model
    with async/await support and structured logging.
    """
    
    def __init__(self, config: ASRSettings):
        """
        Initialize the ASR service.
        
        Args:
            config: ASR configuration settings
        """
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Model and state
        self.model = None
        self.model_size = config.model_name
        self.language = config.language
        self.beam_size = config.beam_size
        self.best_of = config.best_of
        self.temperature = config.temperature
        self.compute_type = config.compute_type
        
        self.logger.info(
            "ASR service configured",
            model_size=self.model_size,
            language=self.language,
            compute_type=self.compute_type,
            beam_size=self.beam_size
        )
    
    async def initialize(self) -> None:
        """
        Initialize the ASR service and load models.
        
        Raises:
            ASRServiceError: If initialization fails
        """
        try:
            self.logger.info("Initializing Faster-Whisper ASR model")
            
            # Load Faster-Whisper model in executor to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, 
                self._load_whisper_model
            )
            
            self.logger.info("Faster-Whisper ASR model loaded successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize ASR service", error=str(e))
            raise ASRServiceError(f"ASR initialization failed: {e}")
    
    def _load_whisper_model(self):
        """Load Faster-Whisper model (sync operation)."""
        try:
            from faster_whisper import WhisperModel
            
            # Load the model
            model = WhisperModel(
                self.model_size,
                device="auto",  # Use CUDA if available, otherwise CPU
                compute_type=self.compute_type,
                download_root=self.config.model_path
            )
            
            return model
            
        except Exception as e:
            raise ASRServiceError(f"Failed to load Faster-Whisper model: {e}")
    
    async def transcribe(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe speech audio to text.
        
        Args:
            audio_data: Raw audio bytes containing speech
            sample_rate: Audio sample rate in Hz
            language: Optional language hint for transcription
            
        Returns:
            Dictionary containing:
                - text: str transcribed text
                - confidence: float confidence score (0-1)
                - segments: List of word-level segments with timing
                - language: str detected/used language
                
        Raises:
            ASRServiceError: If transcription fails
        """
        if self.model is None:
            raise ASRServiceError("ASR model not initialized")
        
        start_time = time.time()
        
        try:
            # Convert bytes to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            audio_np = audio_np / 32768.0  # Normalize to [-1, 1]
            
            # Use provided language or config default
            target_language = language or self.language
            
            # Run transcription in executor
            loop = asyncio.get_event_loop()
            transcription_result = await loop.run_in_executor(
                None,
                self._run_transcription,
                audio_np,
                sample_rate,
                target_language
            )
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.debug(
                "ASR transcription completed",
                text_length=len(transcription_result["text"]),
                language=transcription_result["language"],
                confidence=transcription_result["confidence"],
                processing_time_ms=processing_time,
                audio_duration_ms=len(audio_np) / sample_rate * 1000
            )
            
            return transcription_result
            
        except Exception as e:
            self.logger.error("ASR transcription failed", error=str(e))
            raise ASRServiceError(f"ASR transcription failed: {e}")
    
    def _run_transcription(
        self, 
        audio_np: np.ndarray, 
        sample_rate: int,
        language: Optional[str]
    ) -> Dict[str, Any]:
        """
        Run transcription on audio array (sync operation).
        
        Args:
            audio_np: Audio data as numpy array
            sample_rate: Audio sample rate
            language: Target language for transcription
            
        Returns:
            Transcription results
        """
        try:
            # Transcribe with Faster-Whisper
            segments, info = self.model.transcribe(
                audio_np,
                beam_size=self.beam_size,
                best_of=self.best_of,
                temperature=self.temperature,
                language=language
            )
            
            # Extract text and segment information
            full_text = ""
            segment_list = []
            total_confidence = 0.0
            segment_count = 0
            
            for segment in segments:
                segment_text = segment.text.strip()
                if segment_text:
                    full_text += segment_text + " "
                    
                    segment_data = {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment_text,
                        "confidence": getattr(segment, 'avg_logprob', 0.0)
                    }
                    
                    # Add word-level information if available
                    if hasattr(segment, 'words') and segment.words:
                        word_list = []
                        for word in segment.words:
                            word_data = {
                                "word": word.word,
                                "start": word.start,
                                "end": word.end,
                                "confidence": getattr(word, 'probability', 0.0)
                            }
                            word_list.append(word_data)
                        segment_data["words"] = word_list
                    
                    segment_list.append(segment_data)
                    total_confidence += segment_data["confidence"]
                    segment_count += 1
            
            # Calculate average confidence
            avg_confidence = total_confidence / segment_count if segment_count > 0 else 0.0
            
            # Convert log probabilities to confidence scores (0-1)
            confidence_score = max(0.0, min(1.0, (avg_confidence + 5.0) / 5.0))
            
            full_text = full_text.strip()
            
            return {
                "text": full_text,
                "confidence": confidence_score,
                "segments": segment_list,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "all_language_probs": info.all_language_probs
            }
            
        except Exception as e:
            raise ASRServiceError(f"Faster-Whisper transcription failed: {e}")
    
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        try:
            if self.model:
                # Clear model from memory
                del self.model
                self.model = None
            
            self.logger.info("ASR service cleaned up")
            
        except Exception as e:
            self.logger.error("Error during ASR cleanup", error=str(e))
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Model information dictionary
        """
        return {
            "model_size": self.model_size,
            "language": self.language,
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "temperature": self.temperature,
            "compute_type": self.compute_type,
            "is_initialized": self.model is not None
        }


class MockASRService(IASRService):
    """
    Mock ASR service for testing and development.
    
    Provides deterministic transcription results for testing purposes
    without requiring actual model loading.
    """
    
    def __init__(self, config: ASRSettings):
        """Initialize mock ASR service."""
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.is_initialized = False
        
        # Mock transcription templates
        self.mock_texts = [
            "Hello, this is a test transcription.",
            "The quick brown fox jumps over the lazy dog.",
            "Speech recognition is working correctly.",
            "This is a mock transcription result.",
            "Testing the automatic speech recognition system."
        ]
    
    async def initialize(self) -> None:
        """Initialize mock service."""
        self.is_initialized = True
        self.logger.info("Mock ASR service initialized")
    
    async def transcribe(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mock transcription."""
        if not self.is_initialized:
            raise ASRServiceError("Mock ASR service not initialized")
        
        # Mock logic: select text based on audio data hash
        audio_hash = hash(audio_data) % len(self.mock_texts)
        mock_text = self.mock_texts[audio_hash]
        
        # Mock confidence based on audio length
        audio_length = len(audio_data)
        confidence = min(0.95, 0.7 + (audio_length / 50000))
        
        # Create mock segments
        duration = audio_length / (sample_rate * 2)  # Assuming 16-bit samples
        words = mock_text.split()
        word_duration = duration / len(words) if words else 0
        
        segments = []
        current_time = 0.0
        
        for i, word in enumerate(words):
            word_start = current_time
            word_end = current_time + word_duration
            
            segments.append({
                "start": word_start,
                "end": word_end,
                "text": word,
                "confidence": confidence + (i * 0.01)  # Slight variation
            })
            
            current_time = word_end
        
        target_language = language or self.config.language or "en"
        
        self.logger.debug(
            "Mock ASR transcription",
            text=mock_text,
            confidence=confidence,
            language=target_language,
            audio_length=audio_length
        )
        
        return {
            "text": mock_text,
            "confidence": confidence,
            "segments": segments,
            "language": target_language,
            "language_probability": 0.99,
            "duration": duration,
            "all_language_probs": {target_language: 0.99}
        }
    
    async def cleanup(self) -> None:
        """Clean up mock service."""
        self.is_initialized = False
        self.logger.info("Mock ASR service cleaned up")