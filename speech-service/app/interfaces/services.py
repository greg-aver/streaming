"""
Service interfaces for audio processing components.

This module defines abstract interfaces for VAD, ASR, and Diarization services,
following Clean Architecture and SOLID principles.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from ..models.audio import AudioChunkModel, ProcessingResultModel


class IVADService(ABC):
    """
    Abstract interface for Voice Activity Detection service.
    
    Defines the contract for detecting speech segments in audio data.
    Implementations should handle different VAD algorithms (Silero, WebRTC, etc.).
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the VAD service and load models.
        
        Raises:
            VADServiceError: If initialization fails
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        pass


class IASRService(ABC):
    """
    Abstract interface for Automatic Speech Recognition service.
    
    Defines the contract for transcribing speech to text.
    Implementations should handle different ASR models (Whisper, etc.).
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the ASR service and load models.
        
        Raises:
            ASRServiceError: If initialization fails
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        pass


class IDiarizationService(ABC):
    """
    Abstract interface for Speaker Diarization service.
    
    Defines the contract for identifying and separating different speakers
    in audio. Implementations should handle different diarization models.
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the diarization service and load models.
        
        Raises:
            DiarizationServiceError: If initialization fails
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources and models."""
        pass


class IWorker(ABC):
    """
    Abstract interface for processing workers.
    
    Defines the contract for workers that process audio chunks
    and publish results via the event system.
    """
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the worker and set up event subscriptions.
        
        Raises:
            WorkerError: If worker startup fails
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the worker and clean up resources.
        
        Raises:
            WorkerError: If worker shutdown fails
        """
        pass
    
    @abstractmethod
    async def process_chunk(self, chunk: AudioChunkModel) -> ProcessingResultModel:
        """
        Process an audio chunk and return the result.
        
        Args:
            chunk: Audio chunk to process
            
        Returns:
            Processing result with component-specific data
            
        Raises:
            WorkerError: If processing fails
        """
        pass


class IAggregator(ABC):
    """
    Abstract interface for result aggregation service.
    
    Defines the contract for combining results from different
    processing components into final responses.
    """
    
    @abstractmethod
    async def add_result(self, result: ProcessingResultModel) -> None:
        """
        Add a processing result for aggregation.
        
        Args:
            result: Processing result from a worker component
            
        Raises:
            AggregatorError: If result addition fails
        """
        pass
    
    @abstractmethod
    async def get_aggregated_result(
        self, 
        session_id: str, 
        chunk_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get aggregated result for a specific chunk if available.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            
        Returns:
            Aggregated result dictionary or None if not ready
            
        Raises:
            AggregatorError: If retrieval fails
        """
        pass
    
    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """
        Clear all results for a specific session.
        
        Args:
            session_id: Session identifier to clear
        """
        pass


class IRepository(ABC):
    """
    Abstract interface for data storage repositories.
    
    Defines the contract for storing and retrieving processing
    results and session state.
    """
    
    @abstractmethod
    async def store_result(
        self, 
        session_id: str, 
        chunk_id: int, 
        component: str, 
        result: Dict[str, Any]
    ) -> None:
        """
        Store a processing result.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            component: Component name that generated the result
            result: Result data to store
        """
        pass
    
    @abstractmethod
    async def get_result(
        self, 
        session_id: str, 
        chunk_id: int, 
        component: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific processing result.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            component: Component name
            
        Returns:
            Result data or None if not found
        """
        pass
    
    @abstractmethod
    async def get_all_results(
        self, 
        session_id: str, 
        chunk_id: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all results for a specific chunk.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            
        Returns:
            Dictionary mapping component names to their results
        """
        pass
    
    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """
        Clear all data for a specific session.
        
        Args:
            session_id: Session identifier to clear
        """
        pass


# Exception classes for service interfaces
class ServiceError(Exception):
    """Base exception for service operations."""
    pass


class VADServiceError(ServiceError):
    """Exception raised by VAD service operations."""
    pass


class ASRServiceError(ServiceError):
    """Exception raised by ASR service operations."""
    pass


class DiarizationServiceError(ServiceError):
    """Exception raised by diarization service operations."""
    pass


class WorkerError(Exception):
    """Base exception for worker operations."""
    pass


class AggregatorError(Exception):
    """Exception raised by aggregator operations."""
    pass