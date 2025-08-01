"""
Voice Activity Detection (VAD) service implementation.

This module provides VAD functionality using Silero VAD model,
following Clean Architecture principles with dependency injection.
"""

import asyncio
import time
import numpy as np
import torch
from typing import Dict, Any, Optional
import structlog
from pathlib import Path

from ..interfaces.services import IVADService, VADServiceError
from ..config import VADSettings


class SileroVADService(IVADService):
    """
    Silero VAD service implementation.
    
    Provides voice activity detection using the Silero VAD model
    with async/await support and structured logging.
    """
    
    def __init__(self, config: VADSettings):
        """
        Initialize the VAD service.
        
        Args:
            config: VAD configuration settings
        """
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Model and state
        self.model = None
        self.sample_rate = config.sample_rate
        self.confidence_threshold = config.confidence_threshold
        self.frame_duration_ms = config.frame_duration_ms
        
        # Calculate frame size in samples
        self.frame_size = int(
            self.sample_rate * self.frame_duration_ms / 1000
        )
        
        self.logger.info(
            "VAD service configured",
            model_name=config.model_name,
            sample_rate=self.sample_rate,
            confidence_threshold=self.confidence_threshold,
            frame_size=self.frame_size
        )
    
    async def initialize(self) -> None:
        """
        Initialize the VAD service and load models.
        
        Raises:
            VADServiceError: If initialization fails
        """
        try:
            self.logger.info("Initializing Silero VAD model")
            
            # Load Silero VAD model in executor to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, 
                self._load_silero_model
            )
            
            self.logger.info("Silero VAD model loaded successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize VAD service", error=str(e))
            raise VADServiceError(f"VAD initialization failed: {e}")
    
    def _load_silero_model(self):
        """Load Silero VAD model (sync operation)."""
        try:
            # Load the model from torch hub
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            
            model.eval()
            return model
            
        except Exception as e:
            raise VADServiceError(f"Failed to load Silero model: {e}")
    
    async def detect_speech(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000
    ) -> Dict[str, Any]:
        """
        Detect speech activity in audio data.
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate in Hz
            
        Returns:
            Dictionary containing:
                - is_speech: bool indicating if speech is detected
                - confidence: float confidence score (0-1)
                - speech_segments: List of [start, end] time segments
                
        Raises:
            VADServiceError: If detection fails
        """
        if self.model is None:
            raise VADServiceError("VAD model not initialized")
        
        start_time = time.time()
        
        try:
            # Convert bytes to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            audio_np = audio_np / 32768.0  # Normalize to [-1, 1]
            
            # Resample if necessary
            if sample_rate != self.sample_rate:
                audio_np = await self._resample_audio(audio_np, sample_rate, self.sample_rate)
            
            # Run VAD detection in executor
            loop = asyncio.get_event_loop()
            vad_result = await loop.run_in_executor(
                None,
                self._run_vad_detection,
                audio_np
            )
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.debug(
                "VAD detection completed",
                is_speech=vad_result["is_speech"],
                confidence=vad_result["confidence"],
                processing_time_ms=processing_time,
                audio_duration_ms=len(audio_np) / self.sample_rate * 1000
            )
            
            return vad_result
            
        except Exception as e:
            self.logger.error("VAD detection failed", error=str(e))
            raise VADServiceError(f"VAD detection failed: {e}")
    
    def _run_vad_detection(self, audio_np: np.ndarray) -> Dict[str, Any]:
        """
        Run VAD detection on audio array (sync operation).
        
        Args:
            audio_np: Audio data as numpy array
            
        Returns:
            VAD detection results
        """
        try:
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio_np)
            
            # Ensure we have minimum length for the model
            min_samples = 512  # Minimum samples for Silero VAD
            if len(audio_tensor) < min_samples:
                # Pad with zeros if too short
                padding = min_samples - len(audio_tensor)
                audio_tensor = torch.cat([
                    audio_tensor, 
                    torch.zeros(padding)
                ])
            
            # Run the model
            with torch.no_grad():
                confidence = self.model(audio_tensor, self.sample_rate).item()
            
            is_speech = confidence > self.confidence_threshold
            
            # Calculate speech segments
            speech_segments = []
            if is_speech:
                # For simplicity, treat the entire chunk as one segment
                # In a more sophisticated implementation, you could use
                # frame-by-frame analysis to find exact speech boundaries
                duration_seconds = len(audio_np) / self.sample_rate
                speech_segments = [[0.0, duration_seconds]]
            
            return {
                "is_speech": is_speech,
                "confidence": float(confidence),
                "speech_segments": speech_segments,
                "frame_count": 1,
                "audio_duration": len(audio_np) / self.sample_rate
            }
            
        except Exception as e:
            raise VADServiceError(f"VAD model inference failed: {e}")
    
    async def _resample_audio(
        self, 
        audio: np.ndarray, 
        orig_sr: int, 
        target_sr: int
    ) -> np.ndarray:
        """
        Resample audio to target sample rate.
        
        Args:
            audio: Input audio array
            orig_sr: Original sample rate
            target_sr: Target sample rate
            
        Returns:
            Resampled audio array
        """
        if orig_sr == target_sr:
            return audio
        
        try:
            # Simple linear interpolation resampling
            # For production, consider using scipy.signal.resample or librosa
            ratio = target_sr / orig_sr
            new_length = int(len(audio) * ratio)
            
            # Create new time indices
            old_indices = np.linspace(0, len(audio) - 1, len(audio))
            new_indices = np.linspace(0, len(audio) - 1, new_length)
            
            # Interpolate
            resampled = np.interp(new_indices, old_indices, audio)
            
            self.logger.debug(
                "Audio resampled",
                orig_sr=orig_sr,
                target_sr=target_sr,
                orig_length=len(audio),
                new_length=len(resampled)
            )
            
            return resampled.astype(np.float32)
            
        except Exception as e:
            raise VADServiceError(f"Audio resampling failed: {e}")
    
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        try:
            if self.model:
                # Clear model from memory
                del self.model
                self.model = None
                
                # Clear torch cache if using CUDA
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            self.logger.info("VAD service cleaned up")
            
        except Exception as e:
            self.logger.error("Error during VAD cleanup", error=str(e))
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Model information dictionary
        """
        return {
            "model_name": self.config.model_name,
            "sample_rate": self.sample_rate,
            "confidence_threshold": self.confidence_threshold,
            "frame_duration_ms": self.frame_duration_ms,
            "frame_size": self.frame_size,
            "is_initialized": self.model is not None,
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available()
        }


class MockVADService(IVADService):
    """
    Mock VAD service for testing and development.
    
    Provides deterministic VAD results for testing purposes
    without requiring actual model loading.
    """
    
    def __init__(self, config: VADSettings):
        """Initialize mock VAD service."""
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize mock service."""
        self.is_initialized = True
        self.logger.info("Mock VAD service initialized")
    
    async def detect_speech(
        self, 
        audio_data: bytes, 
        sample_rate: int = 16000
    ) -> Dict[str, Any]:
        """Mock speech detection."""
        if not self.is_initialized:
            raise VADServiceError("Mock VAD service not initialized")
        
        # Mock logic: detect speech based on audio length
        # Longer audio chunks are more likely to contain speech
        audio_length = len(audio_data)
        is_speech = audio_length > 1024  # Simple heuristic
        confidence = min(0.9, audio_length / 10000)  # Mock confidence
        
        duration = audio_length / (sample_rate * 2)  # Assuming 16-bit samples
        
        speech_segments = []
        if is_speech:
            speech_segments = [[0.0, duration]]
        
        self.logger.debug(
            "Mock VAD detection",
            is_speech=is_speech,
            confidence=confidence,
            audio_length=audio_length
        )
        
        return {
            "is_speech": is_speech,
            "confidence": confidence,
            "speech_segments": speech_segments,
            "frame_count": 1,
            "audio_duration": duration
        }
    
    async def cleanup(self) -> None:
        """Clean up mock service."""
        self.is_initialized = False
        self.logger.info("Mock VAD service cleaned up")