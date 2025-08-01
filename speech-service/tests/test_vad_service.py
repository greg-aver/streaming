"""
Tests for VAD (Voice Activity Detection) services.

This module tests MockVADService functionality for development 
and testing purposes, ensuring proper interface compliance.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio

from app.services.vad_service import MockVADService
from app.interfaces.services import VADServiceError
from app.config import VADSettings


class TestMockVADService:
    """Test suite for MockVADService."""
    
    @pytest.fixture
    def vad_config(self):
        """Create VAD configuration for testing."""
        return VADSettings(
            model_name="mock_vad",
            confidence_threshold=0.5,
            frame_duration_ms=30,
            sample_rate=16000
        )
    
    @pytest.fixture
    def mock_vad_service(self, vad_config):
        """Create MockVADService instance for testing."""
        return MockVADService(vad_config)
    
    @pytest.mark.asyncio
    async def test_mock_vad_service_initialization(self, mock_vad_service):
        """Test MockVADService initialization."""
        # Initially not initialized
        assert not mock_vad_service.is_initialized
        
        # Initialize service
        await mock_vad_service.initialize()
        
        # Should be initialized now
        assert mock_vad_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_vad_detect_speech_with_long_audio(self, mock_vad_service):
        """Test speech detection with long audio (should detect speech)."""
        await mock_vad_service.initialize()
        
        # Create long audio data (>1024 bytes)
        long_audio_data = b'\x00' * 2000
        
        result = await mock_vad_service.detect_speech(
            audio_data=long_audio_data,
            sample_rate=16000
        )
        
        # Long audio should be detected as speech
        assert result["is_speech"] is True
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["speech_segments"], list)
        assert len(result["speech_segments"]) > 0
        assert result["frame_count"] == 1
        assert isinstance(result["audio_duration"], float)
        
        # Speech segments should have start and end times
        segment = result["speech_segments"][0]
        assert len(segment) == 2
        assert segment[0] == 0.0  # Start time
        assert segment[1] > 0.0   # End time
    
    @pytest.mark.asyncio
    async def test_mock_vad_detect_speech_with_short_audio(self, mock_vad_service):
        """Test speech detection with short audio (should not detect speech)."""
        await mock_vad_service.initialize()
        
        # Create short audio data (<=1024 bytes)
        short_audio_data = b'\x00' * 500
        
        result = await mock_vad_service.detect_speech(
            audio_data=short_audio_data,
            sample_rate=16000
        )
        
        # Short audio should not be detected as speech
        assert result["is_speech"] is False
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["speech_segments"] == []  # No speech segments
        assert result["frame_count"] == 1
        assert isinstance(result["audio_duration"], float)
    
    @pytest.mark.asyncio
    async def test_mock_vad_detect_speech_different_sample_rates(self, mock_vad_service):
        """Test speech detection with different sample rates."""
        await mock_vad_service.initialize()
        
        audio_data = b'\x00' * 2000
        
        # Test with different sample rates
        for sample_rate in [8000, 16000, 22050, 44100]:
            result = await mock_vad_service.detect_speech(
                audio_data=audio_data,
                sample_rate=sample_rate
            )
            
            assert isinstance(result["is_speech"], bool)
            assert isinstance(result["confidence"], float)
            assert isinstance(result["audio_duration"], float)
            
            # Audio duration should vary with sample rate
            # (same data length but different sample rate = different duration)
            expected_duration = len(audio_data) / (sample_rate * 2)  # 16-bit samples
            assert abs(result["audio_duration"] - expected_duration) < 0.001
    
    @pytest.mark.asyncio
    async def test_mock_vad_confidence_scaling(self, mock_vad_service):
        """Test that confidence scales with audio length."""
        await mock_vad_service.initialize()
        
        # Test with progressively longer audio
        audio_lengths = [1500, 3000, 6000, 12000]
        confidences = []
        
        for length in audio_lengths:
            audio_data = b'\x00' * length
            result = await mock_vad_service.detect_speech(audio_data)
            confidences.append(result["confidence"])
        
        # Confidence should generally increase with audio length
        # (though capped at some maximum)
        for i in range(1, len(confidences)):
            # Allow for the confidence cap at 0.9
            assert confidences[i] >= confidences[i-1] or confidences[i] == 0.9
    
    @pytest.mark.asyncio
    async def test_mock_vad_detect_speech_not_initialized(self, mock_vad_service):
        """Test speech detection fails when service not initialized."""
        # Don't initialize the service
        audio_data = b'\x00' * 1000
        
        with pytest.raises(VADServiceError) as exc_info:
            await mock_vad_service.detect_speech(audio_data)
        
        assert "not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_mock_vad_cleanup(self, mock_vad_service):
        """Test MockVADService cleanup."""
        # Initialize first
        await mock_vad_service.initialize()
        assert mock_vad_service.is_initialized
        
        # Cleanup
        await mock_vad_service.cleanup()
        
        # Should be cleaned up
        assert not mock_vad_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_vad_empty_audio_data(self, mock_vad_service):
        """Test detection with empty audio data."""
        await mock_vad_service.initialize()
        
        result = await mock_vad_service.detect_speech(b'')
        
        # Empty audio should not be speech
        assert result["is_speech"] is False
        assert result["confidence"] == 0.0
        assert result["speech_segments"] == []
        assert result["audio_duration"] == 0.0
    
    @pytest.mark.asyncio
    async def test_mock_vad_boundary_audio_length(self, mock_vad_service):
        """Test detection at the boundary audio length (1024 bytes)."""
        await mock_vad_service.initialize()
        
        # Test exactly at boundary
        boundary_audio = b'\x00' * 1024
        result = await mock_vad_service.detect_speech(boundary_audio)
        assert result["is_speech"] is False  # Should be False (not > 1024)
        
        # Test just over boundary
        over_boundary_audio = b'\x00' * 1025
        result = await mock_vad_service.detect_speech(over_boundary_audio)
        assert result["is_speech"] is True  # Should be True (> 1024)
    
    @pytest.mark.asyncio
    async def test_mock_vad_service_logging(self, mock_vad_service):
        """Test that MockVADService produces appropriate log messages."""
        with patch('structlog.get_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            
            # Create new service to test logging
            vad_config = VADSettings()
            service = MockVADService(vad_config)
            
            # Test initialization logging
            await service.initialize()
            mock_logger.info.assert_called_with("Mock VAD service initialized")
            
            # Test detection logging
            audio_data = b'\x00' * 2000
            await service.detect_speech(audio_data)
            
            # Should have logged debug message
            mock_logger.debug.assert_called()
            debug_call_args = mock_logger.debug.call_args
            assert "Mock VAD detection" in debug_call_args[0][0]
            
            # Test cleanup logging
            await service.cleanup()
            mock_logger.info.assert_called_with("Mock VAD service cleaned up")
    
    def test_mock_vad_config_properties(self, mock_vad_service, vad_config):
        """Test that MockVADService stores config properly."""
        assert mock_vad_service.config == vad_config
        assert mock_vad_service.config.model_name == "mock_vad"
        assert mock_vad_service.config.confidence_threshold == 0.5
        assert mock_vad_service.config.frame_duration_ms == 30
        assert mock_vad_service.config.sample_rate == 16000
    
    @pytest.mark.asyncio
    async def test_mock_vad_result_structure_compliance(self, mock_vad_service):
        """Test that VAD results comply with interface specification."""
        await mock_vad_service.initialize()
        
        audio_data = b'\x00' * 2000
        result = await mock_vad_service.detect_speech(audio_data)
        
        # Check all required fields are present
        required_fields = {
            "is_speech", "confidence", "speech_segments", 
            "frame_count", "audio_duration"
        }
        assert all(field in result for field in required_fields)
        
        # Check field types
        assert isinstance(result["is_speech"], bool)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["speech_segments"], list)
        assert isinstance(result["frame_count"], int)
        assert isinstance(result["audio_duration"], float)
        
        # Check value ranges
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["frame_count"] >= 0
        assert result["audio_duration"] >= 0.0
        
        # Check speech segments structure
        for segment in result["speech_segments"]:
            assert isinstance(segment, list)
            assert len(segment) == 2
            assert isinstance(segment[0], float)  # start time
            assert isinstance(segment[1], float)  # end time
            assert segment[0] <= segment[1]      # start <= end