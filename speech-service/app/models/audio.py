"""
Audio-related Pydantic models for the speech-to-text service.

This module contains data models for audio processing pipeline,
following Clean Architecture principles with strict type validation.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
import uuid
from datetime import datetime


class AudioChunkModel(BaseModel):
    """
    Represents an audio chunk received from WebSocket client.
    
    This is the primary input model for the audio processing pipeline.
    Each chunk is uniquely identified within a session and contains
    raw audio data for processing.
    
    Attributes:
        session_id: Unique identifier for the WebSocket session
        chunk_id: Sequential identifier for the chunk within session
        data: Raw audio bytes data
        timestamp: When the chunk was received
        sample_rate: Audio sample rate in Hz (optional)
        channels: Number of audio channels (optional)
    """
    
    session_id: str = Field(
        ..., 
        description="Unique session identifier",
        min_length=1,
        max_length=64
    )
    
    chunk_id: int = Field(
        ..., 
        description="Sequential chunk identifier within session",
        ge=0
    )
    
    data: bytes = Field(
        ..., 
        description="Raw audio data bytes",
        min_length=1
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when chunk was received"
    )
    
    sample_rate: Optional[int] = Field(
        default=16000,
        description="Audio sample rate in Hz",
        ge=8000,
        le=48000
    )
    
    channels: Optional[int] = Field(
        default=1,
        description="Number of audio channels",
        ge=1,
        le=2
    )
    
    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v):
        """Validate session_id format."""
        if not v or not isinstance(v, str):
            raise ValueError("session_id must be a non-empty string")
        return v
    
    @field_validator('data')
    @classmethod
    def validate_audio_data(cls, v):
        """Validate audio data is not empty."""
        if not v or len(v) == 0:
            raise ValueError("Audio data cannot be empty")
        return v
    
    model_config = ConfigDict(
        json_encoders={
            bytes: lambda v: len(v),  # Don't serialize raw bytes in JSON
            datetime: lambda v: v.isoformat()
        },
        json_schema_extra={
            "example": {
                "session_id": "ws_session_12345",
                "chunk_id": 0,
                "data": b"audio_bytes_here",
                "timestamp": "2023-12-01T12:00:00Z",
                "sample_rate": 16000,
                "channels": 1
            }
        }
    )


class ProcessingResultModel(BaseModel):
    """
    Represents the result from any processing component.
    
    This is a generic result model that can hold output from
    VAD, ASR, or Diarization workers. The component field
    identifies which processor generated the result.
    
    Attributes:
        session_id: Session identifier from original audio chunk
        chunk_id: Chunk identifier from original audio chunk  
        component: Name of the processing component
        result: Component-specific result data
        processing_time_ms: Time taken to process in milliseconds
        timestamp: When processing was completed
        success: Whether processing was successful
        error: Error message if processing failed
    """
    
    session_id: str = Field(
        ...,
        description="Session identifier from original audio chunk",
        min_length=1,
        max_length=64
    )
    
    chunk_id: int = Field(
        ...,
        description="Chunk identifier from original audio chunk",
        ge=0
    )
    
    component: str = Field(
        ...,
        description="Name of the processing component",
        pattern=r"^(vad|asr|diarization)$"
    )
    
    result: Dict[str, Any] = Field(
        ...,
        description="Component-specific result data"
    )
    
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds",
        ge=0
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when processing completed"
    )
    
    success: bool = Field(
        default=True,
        description="Whether processing was successful"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if processing failed"
    )
    
    @field_validator('result')
    @classmethod
    def validate_result_structure(cls, v, info):
        """Validate result structure based on component type."""
        if info.data is None:
            return v
        component = info.data.get('component')
        
        if component == 'vad':
            required_fields = {'is_speech', 'confidence'}
            if not all(field in v for field in required_fields):
                raise ValueError(f"VAD result must contain: {required_fields}")
                
        elif component == 'asr':
            required_fields = {'text', 'confidence'}
            if not all(field in v for field in required_fields):
                raise ValueError(f"ASR result must contain: {required_fields}")
                
        elif component == 'diarization':
            required_fields = {'speakers', 'segments'}
            if not all(field in v for field in required_fields):
                raise ValueError(f"Diarization result must contain: {required_fields}")
        
        return v
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        },
        json_schema_extra={
            "example": {
                "session_id": "ws_session_12345",
                "chunk_id": 0,
                "component": "vad",
                "result": {
                    "is_speech": True,
                    "confidence": 0.95,
                    "speech_segments": [[0.1, 2.3]]
                },
                "processing_time_ms": 15.2,
                "timestamp": "2023-12-01T12:00:00Z",
                "success": True,
                "error": None
            }
        }
    )


class WebSocketResponseModel(BaseModel):
    """
    Final response model sent back to WebSocket client.
    
    This aggregates results from all processing components
    (VAD, ASR, Diarization) into a single response message.
    
    Attributes:
        session_id: Session identifier
        chunk_id: Chunk identifier
        vad: Voice Activity Detection results
        transcript: Speech recognition text
        speakers: Speaker diarization results
        processing_complete: Whether all processing is finished
        total_processing_time_ms: Total time for all processing
    """
    
    session_id: str = Field(
        ...,
        description="Session identifier"
    )
    
    chunk_id: int = Field(
        ...,
        description="Chunk identifier"
    )
    
    vad: Dict[str, Any] = Field(
        ...,
        description="Voice Activity Detection results"
    )
    
    transcript: Optional[str] = Field(
        default=None,
        description="Transcribed text from speech recognition"
    )
    
    speakers: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Speaker diarization results"
    )
    
    processing_complete: bool = Field(
        default=True,
        description="Whether all processing components have finished"
    )
    
    total_processing_time_ms: float = Field(
        ...,
        description="Total processing time across all components",
        ge=0
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when response was created"
    )
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        },
        json_schema_extra={
            "example": {
                "session_id": "ws_session_12345",
                "chunk_id": 0,
                "vad": {
                    "is_speech": True,
                    "confidence": 0.95
                },
                "transcript": "Hello world this is a test",
                "speakers": {
                    "speaker_count": 1,
                    "segments": [
                        {
                            "speaker": "SPEAKER_00",
                            "start": 0.1,
                            "end": 2.3,
                            "text": "Hello world this is a test"
                        }
                    ]
                },
                "processing_complete": True,
                "total_processing_time_ms": 245.7,
                "timestamp": "2023-12-01T12:00:01Z"
            }
        }
    )