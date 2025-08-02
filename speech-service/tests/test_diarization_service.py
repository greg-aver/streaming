"""
Tests for Mock Diarization Service implementation.

This module tests the MockDiarizationService functionality including:
- Service initialization and cleanup
- Speaker diarization with deterministic results
- Multiple speakers detection
- Segment generation and timing
- Speaker statistics calculation
- Configuration handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.services.diarization_service import MockDiarizationService
from app.interfaces.services import DiarizationServiceError
from app.config import DiarizationSettings


class TestMockDiarizationService:
    """Test cases for MockDiarizationService."""
    
    @pytest.fixture
    def diarization_config(self):
        """Create test diarization configuration."""
        return DiarizationSettings(
            model_name="pyannote/speaker-diarization-3.1",
            min_speakers=1,
            max_speakers=5,
            clustering_method="centroid"
        )
    
    @pytest.fixture
    def mock_diarization_service(self, diarization_config):
        """Create MockDiarizationService instance."""
        return MockDiarizationService(diarization_config)
    
    @pytest.mark.asyncio
    async def test_mock_diarization_service_initialization(self, mock_diarization_service):
        """Test service initialization."""
        # Initially not initialized
        assert not mock_diarization_service.is_initialized
        
        # Initialize service
        await mock_diarization_service.initialize()
        
        # Should be initialized now
        assert mock_diarization_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_diarization_basic(self, mock_diarization_service):
        """Test basic diarization functionality."""
        await mock_diarization_service.initialize()
        
        # Test with sample audio data
        audio_data = b"x" * 32000  # 1 second at 16kHz 16-bit
        sample_rate = 16000
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Verify structure
        assert "speakers" in result
        assert "segments" in result
        assert "speaker_count" in result
        assert "total_speech_time" in result
        assert "speaker_stats" in result
        
        # Verify data types
        assert isinstance(result["speakers"], list)
        assert isinstance(result["segments"], list)
        assert isinstance(result["speaker_count"], int)
        assert isinstance(result["total_speech_time"], float)
        assert isinstance(result["speaker_stats"], dict)
        
        # Basic validation
        assert result["speaker_count"] > 0
        assert len(result["speakers"]) == result["speaker_count"]
        assert len(result["segments"]) >= result["speaker_count"]
    
    @pytest.mark.asyncio
    async def test_mock_diarization_deterministic(self, mock_diarization_service):
        """Test that diarization results are deterministic for same input."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 16000  # 0.5 seconds
        sample_rate = 16000
        
        # Run diarization twice with same input
        result1 = await mock_diarization_service.diarize(audio_data, sample_rate)
        result2 = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Results should be identical
        assert result1["speaker_count"] == result2["speaker_count"]
        assert result1["speakers"] == result2["speakers"]
        assert len(result1["segments"]) == len(result2["segments"])
        assert result1["total_speech_time"] == result2["total_speech_time"]
    
    @pytest.mark.asyncio
    async def test_mock_diarization_different_audio_lengths(self, mock_diarization_service):
        """Test diarization with different audio lengths produces different results."""
        await mock_diarization_service.initialize()
        
        # Short audio
        short_audio = b"x" * 16000  # 0.5 seconds
        short_result = await mock_diarization_service.diarize(short_audio, 16000)
        
        # Long audio
        long_audio = b"x" * 160000  # 5 seconds
        long_result = await mock_diarization_service.diarize(long_audio, 16000)
        
        # Longer audio should potentially have more speakers
        assert long_result["speaker_count"] >= short_result["speaker_count"]
        assert long_result["total_speech_time"] > short_result["total_speech_time"]
        assert len(long_result["segments"]) >= len(short_result["segments"])
    
    @pytest.mark.asyncio
    async def test_mock_diarization_num_speakers_parameter(self, mock_diarization_service):
        """Test explicit num_speakers parameter."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000
        sample_rate = 16000
        
        # Test with explicit speaker count
        result = await mock_diarization_service.diarize(
            audio_data, sample_rate, num_speakers=3
        )
        
        assert result["speaker_count"] == 3
        assert len(result["speakers"]) == 3
        
        # Should have segments for each speaker
        speakers_in_segments = set(s["speaker"] for s in result["segments"])
        assert len(speakers_in_segments) == 3
    
    @pytest.mark.asyncio
    async def test_mock_diarization_speaker_limits(self, mock_diarization_service):
        """Test speaker count limits from configuration."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000
        sample_rate = 16000
        
        # Test with num_speakers > max_speakers
        result = await mock_diarization_service.diarize(
            audio_data, sample_rate, num_speakers=10  # Config max is 5
        )
        
        assert result["speaker_count"] <= mock_diarization_service.config.max_speakers
        
        # Test with very long audio (should respect max_speakers)
        very_long_audio = b"x" * 1000000  # Very long audio
        result_long = await mock_diarization_service.diarize(very_long_audio, sample_rate)
        
        assert result_long["speaker_count"] <= mock_diarization_service.config.max_speakers
        assert result_long["speaker_count"] >= mock_diarization_service.config.min_speakers
    
    @pytest.mark.asyncio
    async def test_mock_diarization_segments_structure(self, mock_diarization_service):
        """Test structure of diarization segments."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000
        sample_rate = 16000
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Check segment structure
        for segment in result["segments"]:
            assert "speaker" in segment
            assert "start" in segment
            assert "end" in segment
            assert "duration" in segment
            assert "confidence" in segment
            
            # Validate data types
            assert isinstance(segment["speaker"], str)
            assert isinstance(segment["start"], float)
            assert isinstance(segment["end"], float)
            assert isinstance(segment["duration"], float)
            assert isinstance(segment["confidence"], float)
            
            # Validate logical consistency
            assert segment["end"] > segment["start"]
            assert segment["duration"] == segment["end"] - segment["start"]
            assert 0.0 <= segment["confidence"] <= 1.0
            assert segment["speaker"] in result["speakers"]
    
    @pytest.mark.asyncio
    async def test_mock_diarization_speaker_stats(self, mock_diarization_service):
        """Test speaker statistics calculation."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000
        sample_rate = 16000
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Check speaker stats structure
        for speaker in result["speakers"]:
            assert speaker in result["speaker_stats"]
            stats = result["speaker_stats"][speaker]
            
            assert "total_speaking_time" in stats
            assert "segment_count" in stats
            assert "average_segment_duration" in stats
            assert "speaking_percentage" in stats
            
            # Validate data types
            assert isinstance(stats["total_speaking_time"], float)
            assert isinstance(stats["segment_count"], int)
            assert isinstance(stats["average_segment_duration"], float)
            assert isinstance(stats["speaking_percentage"], float)
            
            # Validate logical consistency
            assert stats["total_speaking_time"] > 0
            assert stats["segment_count"] > 0
            assert stats["speaking_percentage"] > 0
            assert stats["speaking_percentage"] <= 100
            
            # Verify average calculation
            expected_avg = stats["total_speaking_time"] / stats["segment_count"]
            assert abs(stats["average_segment_duration"] - expected_avg) < 0.001
        
        # Verify total speaking percentages sum to ~100%
        total_percentage = sum(
            stats["speaking_percentage"] 
            for stats in result["speaker_stats"].values()
        )
        assert abs(total_percentage - 100.0) < 0.01  # Allow small rounding errors
    
    @pytest.mark.asyncio
    async def test_mock_diarization_segments_timing(self, mock_diarization_service):
        """Test segment timing consistency."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000  # 1 second
        sample_rate = 16000
        expected_duration = len(audio_data) / (sample_rate * 2)  # 16-bit samples
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Segments should be sorted by start time
        segments = result["segments"]
        for i in range(len(segments) - 1):
            assert segments[i]["start"] <= segments[i + 1]["start"]
        
        # Total duration should match expected
        total_segment_time = sum(s["duration"] for s in segments)
        assert abs(total_segment_time - expected_duration) < 0.001
        
        # Last segment should end at approximately the audio duration
        if segments:
            last_segment = segments[-1]
            assert abs(last_segment["end"] - expected_duration) < 0.1
    
    @pytest.mark.asyncio
    async def test_mock_diarization_not_initialized(self, mock_diarization_service):
        """Test diarization without initialization raises error."""
        audio_data = b"x" * 16000
        
        with pytest.raises(DiarizationServiceError, match="not initialized"):
            await mock_diarization_service.diarize(audio_data, 16000)
    
    @pytest.mark.asyncio
    async def test_mock_diarization_cleanup(self, mock_diarization_service):
        """Test service cleanup."""
        await mock_diarization_service.initialize()
        assert mock_diarization_service.is_initialized
        
        await mock_diarization_service.cleanup()
        assert not mock_diarization_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_diarization_empty_audio_data(self, mock_diarization_service):
        """Test diarization with empty audio data."""
        await mock_diarization_service.initialize()
        
        # Empty audio data
        audio_data = b""
        sample_rate = 16000
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Should still return valid structure
        assert result["speaker_count"] >= mock_diarization_service.config.min_speakers
        assert len(result["speakers"]) == result["speaker_count"]
        assert len(result["segments"]) >= 0
        assert result["total_speech_time"] >= 0
    
    @pytest.mark.asyncio
    async def test_mock_diarization_speaker_naming(self, mock_diarization_service):
        """Test speaker naming convention."""
        await mock_diarization_service.initialize()
        
        audio_data = b"x" * 32000
        sample_rate = 16000
        
        result = await mock_diarization_service.diarize(audio_data, sample_rate)
        
        # Check speaker naming format
        for i, speaker in enumerate(result["speakers"]):
            expected_name = f"SPEAKER_{i:02d}"
            assert speaker == expected_name
        
        # Speakers should be sorted
        assert result["speakers"] == sorted(result["speakers"])
    
    @pytest.mark.asyncio
    async def test_mock_diarization_service_logging(self, mock_diarization_service):
        """Test service logging functionality."""
        # Mock the logger to verify logging calls
        mock_logger = MagicMock()
        mock_diarization_service.logger = mock_logger
        
        await mock_diarization_service.initialize()
        mock_logger.info.assert_called_with("Mock diarization service initialized")
        
        audio_data = b"x" * 32000
        await mock_diarization_service.diarize(audio_data, 16000)
        mock_logger.debug.assert_called()
        
        await mock_diarization_service.cleanup()
        mock_logger.info.assert_called_with("Mock diarization service cleaned up")
    
    @pytest.mark.asyncio
    async def test_mock_diarization_config_properties(self, mock_diarization_service):
        """Test configuration properties access."""
        config = mock_diarization_service.config
        
        assert hasattr(config, 'model_name')
        assert hasattr(config, 'min_speakers')
        assert hasattr(config, 'max_speakers')
        assert hasattr(config, 'clustering_method')
        
        assert config.min_speakers > 0
        assert config.max_speakers >= config.min_speakers
        assert isinstance(config.model_name, str)
        assert isinstance(config.clustering_method, str)