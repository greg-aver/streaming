"""
Tests for Pydantic models in the speech-to-text service.

This module tests all data models for proper validation,
serialization, and business logic compliance.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.audio import (
    AudioChunkModel,
    ProcessingResultModel,
    WebSocketResponseModel
)


class TestAudioChunkModel:
    """Test suite for AudioChunkModel."""
    
    def test_valid_audio_chunk_creation(self):
        """Test creating a valid audio chunk."""
        chunk = AudioChunkModel(
            session_id="test_session_123",
            chunk_id=0,
            data=b"audio_data_bytes",
            sample_rate=16000,
            channels=1
        )
        
        assert chunk.session_id == "test_session_123"
        assert chunk.chunk_id == 0
        assert chunk.data == b"audio_data_bytes"
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1
        assert isinstance(chunk.timestamp, datetime)
    
    def test_audio_chunk_with_defaults(self):
        """Test audio chunk creation with default values."""
        chunk = AudioChunkModel(
            session_id="test_session",
            chunk_id=5,
            data=b"test_audio"
        )
        
        assert chunk.sample_rate == 16000  # Default
        assert chunk.channels == 1  # Default
        assert isinstance(chunk.timestamp, datetime)
    
    def test_invalid_session_id_validation(self):
        """Test session_id validation."""
        # Empty session_id should fail
        with pytest.raises(ValidationError) as exc_info:
            AudioChunkModel(
                session_id="",
                chunk_id=0,
                data=b"test"
            )
        
        # Too long session_id should fail
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="x" * 65,  # Max is 64
                chunk_id=0,
                data=b"test"
            )
    
    def test_invalid_chunk_id_validation(self):
        """Test chunk_id validation."""
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="test",
                chunk_id=-1,  # Should be >= 0
                data=b"test"
            )
    
    def test_empty_audio_data_validation(self):
        """Test audio data validation."""
        with pytest.raises(ValidationError) as exc_info:
            AudioChunkModel(
                session_id="test",
                chunk_id=0,
                data=b""  # Empty data should fail
            )
        
        error_msg = str(exc_info.value)
        assert "at least 1 byte" in error_msg
    
    def test_invalid_sample_rate_validation(self):
        """Test sample rate validation."""
        # Too low sample rate
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="test",
                chunk_id=0,
                data=b"test",
                sample_rate=7000  # Below 8000
            )
        
        # Too high sample rate  
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="test",
                chunk_id=0,
                data=b"test",
                sample_rate=50000  # Above 48000
            )
    
    def test_invalid_channels_validation(self):
        """Test channels validation."""
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="test",
                chunk_id=0,
                data=b"test",
                channels=0  # Should be >= 1
            )
        
        with pytest.raises(ValidationError):
            AudioChunkModel(
                session_id="test",
                chunk_id=0,
                data=b"test",
                channels=3  # Should be <= 2
            )


class TestProcessingResultModel:
    """Test suite for ProcessingResultModel."""
    
    def test_valid_vad_result(self):
        """Test creating a valid VAD processing result."""
        result = ProcessingResultModel(
            session_id="test_session",
            chunk_id=0,
            component="vad",
            result={
                "is_speech": True,
                "confidence": 0.95,
                "speech_segments": [[0.1, 2.3]]
            },
            processing_time_ms=15.2
        )
        
        assert result.component == "vad"
        assert result.result["is_speech"] is True
        assert result.result["confidence"] == 0.95
        assert result.success is True
        assert result.error is None
    
    def test_valid_asr_result(self):
        """Test creating a valid ASR processing result."""
        result = ProcessingResultModel(
            session_id="test_session",
            chunk_id=0,
            component="asr",
            result={
                "text": "Hello world",
                "confidence": 0.89,
                "language": "en"
            },
            processing_time_ms=125.7
        )
        
        assert result.component == "asr"
        assert result.result["text"] == "Hello world"
        assert result.result["confidence"] == 0.89
    
    def test_valid_diarization_result(self):
        """Test creating a valid diarization processing result."""
        result = ProcessingResultModel(
            session_id="test_session",
            chunk_id=0,
            component="diarization",
            result={
                "speakers": ["SPEAKER_00", "SPEAKER_01"],
                "segments": [
                    {"speaker": "SPEAKER_00", "start": 0.1, "end": 1.5},
                    {"speaker": "SPEAKER_01", "start": 1.6, "end": 3.2}
                ]
            },
            processing_time_ms=234.5
        )
        
        assert result.component == "diarization"
        assert len(result.result["speakers"]) == 2
        assert len(result.result["segments"]) == 2
    
    def test_invalid_component_validation(self):
        """Test component validation."""
        with pytest.raises(ValidationError):
            ProcessingResultModel(
                session_id="test",
                chunk_id=0,
                component="invalid_component",
                result={"test": "data"},
                processing_time_ms=10.0
            )
    
    def test_invalid_vad_result_structure(self):
        """Test VAD result structure validation."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessingResultModel(
                session_id="test",
                chunk_id=0,
                component="vad",
                result={"confidence": 0.95},  # Missing is_speech
                processing_time_ms=10.0
            )
        
        error_msg = str(exc_info.value)
        assert "VAD result must contain" in error_msg
    
    def test_invalid_asr_result_structure(self):
        """Test ASR result structure validation."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessingResultModel(
                session_id="test",
                chunk_id=0,
                component="asr",
                result={"text": "Hello"},  # Missing confidence
                processing_time_ms=10.0
            )
        
        error_msg = str(exc_info.value)
        assert "ASR result must contain" in error_msg
    
    def test_invalid_diarization_result_structure(self):
        """Test diarization result structure validation."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessingResultModel(
                session_id="test",
                chunk_id=0,
                component="diarization",
                result={"speakers": ["SPEAKER_00"]},  # Missing segments
                processing_time_ms=10.0
            )
        
        error_msg = str(exc_info.value)
        assert "Diarization result must contain" in error_msg
    
    def test_negative_processing_time_validation(self):
        """Test processing time validation."""
        with pytest.raises(ValidationError):
            ProcessingResultModel(
                session_id="test",
                chunk_id=0,
                component="vad",
                result={"is_speech": True, "confidence": 0.95},
                processing_time_ms=-5.0  # Should be >= 0
            )
    
    def test_failed_processing_result(self):
        """Test creating a failed processing result."""
        result = ProcessingResultModel(
            session_id="test",
            chunk_id=0,
            component="vad",
            result={"is_speech": False, "confidence": 0.0},
            processing_time_ms=5.0,
            success=False,
            error="Processing failed due to invalid audio format"
        )
        
        assert result.success is False
        assert result.error == "Processing failed due to invalid audio format"


class TestWebSocketResponseModel:
    """Test suite for WebSocketResponseModel."""
    
    def test_valid_websocket_response(self):
        """Test creating a valid WebSocket response."""
        response = WebSocketResponseModel(
            session_id="test_session",
            chunk_id=0,
            vad={
                "is_speech": True,
                "confidence": 0.95
            },
            transcript="Hello world this is a test",
            speakers={
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
            total_processing_time_ms=245.7
        )
        
        assert response.session_id == "test_session"
        assert response.chunk_id == 0
        assert response.vad["is_speech"] is True
        assert response.transcript == "Hello world this is a test"
        assert response.speakers["speaker_count"] == 1
        assert response.processing_complete is True
        assert response.total_processing_time_ms == 245.7
    
    def test_websocket_response_with_defaults(self):
        """Test WebSocket response with default values."""
        response = WebSocketResponseModel(
            session_id="test",
            chunk_id=5,
            vad={"is_speech": False, "confidence": 0.1},
            total_processing_time_ms=50.0
        )
        
        assert response.transcript is None  # Default
        assert response.speakers is None  # Default
        assert response.processing_complete is True  # Default
        assert isinstance(response.timestamp, datetime)
    
    def test_negative_processing_time_validation(self):
        """Test total processing time validation."""
        with pytest.raises(ValidationError):
            WebSocketResponseModel(
                session_id="test",
                chunk_id=0,
                vad={"is_speech": True, "confidence": 0.95},
                total_processing_time_ms=-10.0  # Should be >= 0
            )
    
    def test_partial_processing_response(self):
        """Test response with partial processing results."""
        response = WebSocketResponseModel(
            session_id="test",
            chunk_id=0,
            vad={"is_speech": True, "confidence": 0.95},
            total_processing_time_ms=100.0,
            processing_complete=False  # Still processing
        )
        
        assert response.processing_complete is False
        assert response.transcript is None
        assert response.speakers is None