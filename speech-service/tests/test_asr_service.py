"""
Tests for ASR (Automatic Speech Recognition) services.

This module tests MockASRService functionality for development 
and testing purposes, ensuring proper interface compliance.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio

from app.services.asr_service import MockASRService
from app.interfaces.services import ASRServiceError
from app.config import ASRSettings


class TestMockASRService:
    """Test suite for MockASRService."""
    
    @pytest.fixture
    def asr_config(self):
        """Create ASR configuration for testing."""
        return ASRSettings(
            model_name="base",
            language="en",
            beam_size=5,
            best_of=3,
            temperature=0.0,
            compute_type="float16"
        )
    
    @pytest.fixture
    def mock_asr_service(self, asr_config):
        """Create MockASRService instance for testing."""
        return MockASRService(asr_config)
    
    @pytest.mark.asyncio
    async def test_mock_asr_service_initialization(self, mock_asr_service):
        """Test MockASRService initialization."""
        # Initially not initialized
        assert not mock_asr_service.is_initialized
        
        # Initialize service
        await mock_asr_service.initialize()
        
        # Should be initialized now
        assert mock_asr_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_asr_transcribe_basic(self, mock_asr_service):
        """Test basic transcription functionality."""
        await mock_asr_service.initialize()
        
        # Create test audio data
        audio_data = b'\x00' * 1000
        
        result = await mock_asr_service.transcribe(
            audio_data=audio_data,
            sample_rate=16000
        )
        
        # Check required fields
        assert "text" in result
        assert "confidence" in result
        assert "segments" in result
        assert "language" in result
        assert "language_probability" in result
        assert "duration" in result
        assert "all_language_probs" in result
        
        # Check field types and values
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 0
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["segments"], list)
        assert isinstance(result["language"], str)
        assert isinstance(result["language_probability"], float)
        assert isinstance(result["duration"], float)
        assert isinstance(result["all_language_probs"], dict)
    
    @pytest.mark.asyncio
    async def test_mock_asr_deterministic_transcription(self, mock_asr_service):
        """Test that same audio data produces same transcription."""
        await mock_asr_service.initialize()
        
        audio_data = b'\x01\x02\x03' * 1000
        
        # Transcribe the same data multiple times
        result1 = await mock_asr_service.transcribe(audio_data)
        result2 = await mock_asr_service.transcribe(audio_data)
        result3 = await mock_asr_service.transcribe(audio_data)
        
        # Results should be identical
        assert result1["text"] == result2["text"] == result3["text"]
        assert result1["confidence"] == result2["confidence"] == result3["confidence"]
        assert result1["language"] == result2["language"] == result3["language"]
    
    @pytest.mark.asyncio
    async def test_mock_asr_different_audio_different_results(self, mock_asr_service):
        """Test that different audio data produces different transcriptions."""
        await mock_asr_service.initialize()
        
        # Different audio data should produce different results
        audio_data1 = b'\x01' * 1000
        audio_data2 = b'\x02' * 1000
        audio_data3 = b'\x03' * 1000
        
        result1 = await mock_asr_service.transcribe(audio_data1)
        result2 = await mock_asr_service.transcribe(audio_data2)
        result3 = await mock_asr_service.transcribe(audio_data3)
        
        # Should get different texts (though not guaranteed due to hash collisions)
        texts = [result1["text"], result2["text"], result3["text"]]
        # At least some should be different
        assert len(set(texts)) > 1, "Expected different transcriptions for different audio"
    
    @pytest.mark.asyncio
    async def test_mock_asr_confidence_scaling(self, mock_asr_service):
        """Test that confidence scales with audio length."""
        await mock_asr_service.initialize()
        
        # Test with progressively longer audio
        audio_lengths = [500, 1000, 2000, 10000, 100000]
        confidences = []
        
        for length in audio_lengths:
            audio_data = b'\x00' * length
            result = await mock_asr_service.transcribe(audio_data)
            confidences.append(result["confidence"])
        
        # Confidence should generally increase with audio length (up to cap)
        for i in range(1, len(confidences)):
            # Allow for the confidence cap at 0.95
            assert confidences[i] >= confidences[i-1] or confidences[i] == 0.95
    
    @pytest.mark.asyncio
    async def test_mock_asr_language_parameter(self, mock_asr_service):
        """Test transcription with different language parameters."""
        await mock_asr_service.initialize()
        
        audio_data = b'\x00' * 1000
        
        # Test with different languages
        languages = ["en", "es", "fr", "de", "ru"]
        
        for lang in languages:
            result = await mock_asr_service.transcribe(
                audio_data=audio_data,
                language=lang
            )
            
            assert result["language"] == lang
            assert lang in result["all_language_probs"]
            assert result["all_language_probs"][lang] == 0.99
    
    @pytest.mark.asyncio
    async def test_mock_asr_language_default_from_config(self, mock_asr_service):
        """Test that default language comes from config."""
        await mock_asr_service.initialize()
        
        audio_data = b'\x00' * 1000
        
        # Don't specify language - should use config default
        result = await mock_asr_service.transcribe(audio_data)
        
        assert result["language"] == mock_asr_service.config.language
    
    @pytest.mark.asyncio
    async def test_mock_asr_segments_structure(self, mock_asr_service):
        """Test that segments have correct structure."""
        await mock_asr_service.initialize()
        
        audio_data = b'\x00' * 2000
        
        result = await mock_asr_service.transcribe(audio_data)
        
        # Check segments structure
        segments = result["segments"]
        assert isinstance(segments, list)
        assert len(segments) > 0
        
        # Check each segment
        for segment in segments:
            assert "start" in segment
            assert "end" in segment
            assert "text" in segment
            assert "confidence" in segment
            
            assert isinstance(segment["start"], float)
            assert isinstance(segment["end"], float)
            assert isinstance(segment["text"], str)
            assert isinstance(segment["confidence"], float)
            
            # Time consistency
            assert segment["start"] <= segment["end"]
            assert 0.0 <= segment["confidence"] <= 1.0
            assert len(segment["text"]) > 0
        
        # Check time sequence
        for i in range(1, len(segments)):
            assert segments[i]["start"] >= segments[i-1]["end"]
    
    @pytest.mark.asyncio
    async def test_mock_asr_text_word_count_matches_segments(self, mock_asr_service):
        """Test that text word count matches number of segments."""
        await mock_asr_service.initialize()
        
        audio_data = b'\x00' * 1000
        
        result = await mock_asr_service.transcribe(audio_data)
        
        text_words = result["text"].split()
        segments = result["segments"]
        
        # Each segment should correspond to one word
        assert len(text_words) == len(segments)
        
        # Check that segment texts match text words
        for i, segment in enumerate(segments):
            assert segment["text"] == text_words[i]
    
    @pytest.mark.asyncio
    async def test_mock_asr_duration_calculation(self, mock_asr_service):
        """Test duration calculation based on audio length and sample rate."""
        await mock_asr_service.initialize()
        
        # Test with different sample rates
        audio_data = b'\x00' * 16000  # 16000 bytes
        
        sample_rates = [8000, 16000, 22050, 44100]
        
        for sample_rate in sample_rates:
            result = await mock_asr_service.transcribe(
                audio_data=audio_data,
                sample_rate=sample_rate
            )
            
            # Expected duration: bytes / (sample_rate * 2) for 16-bit audio
            expected_duration = len(audio_data) / (sample_rate * 2)
            assert abs(result["duration"] - expected_duration) < 0.001
    
    @pytest.mark.asyncio
    async def test_mock_asr_transcribe_not_initialized(self, mock_asr_service):
        """Test transcription fails when service not initialized."""
        # Don't initialize the service
        audio_data = b'\x00' * 1000
        
        with pytest.raises(ASRServiceError) as exc_info:
            await mock_asr_service.transcribe(audio_data)
        
        assert "not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_mock_asr_cleanup(self, mock_asr_service):
        """Test MockASRService cleanup."""
        # Initialize first
        await mock_asr_service.initialize()
        assert mock_asr_service.is_initialized
        
        # Cleanup
        await mock_asr_service.cleanup()
        
        # Should be cleaned up
        assert not mock_asr_service.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_asr_empty_audio_data(self, mock_asr_service):
        """Test transcription with empty audio data."""
        await mock_asr_service.initialize()
        
        result = await mock_asr_service.transcribe(b'')
        
        # Should still return valid structure
        assert isinstance(result["text"], str)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["segments"], list)
        assert result["duration"] == 0.0
    
    @pytest.mark.asyncio
    async def test_mock_asr_mock_texts_coverage(self, mock_asr_service):
        """Test that different audio data can access all mock texts."""
        await mock_asr_service.initialize()
        
        # Try many different audio patterns to hit different mock texts
        texts_seen = set()
        
        for i in range(50):  # Try 50 different patterns
            audio_data = bytes([i % 256] * (1000 + i))
            result = await mock_asr_service.transcribe(audio_data)
            texts_seen.add(result["text"])
        
        # Should have seen multiple different mock texts
        assert len(texts_seen) > 1, "Should see multiple different mock texts"
        
        # All seen texts should be from the mock_texts list
        for text in texts_seen:
            assert text in mock_asr_service.mock_texts
    
    @pytest.mark.asyncio
    async def test_mock_asr_service_logging(self, mock_asr_service):
        """Test that MockASRService produces appropriate log messages."""
        with patch('structlog.get_logger') as mock_logger_factory:
            mock_logger = AsyncMock()
            mock_logger_factory.return_value = mock_logger
            
            # Create new service to test logging
            asr_config = ASRSettings()
            service = MockASRService(asr_config)
            
            # Test initialization logging
            await service.initialize()
            mock_logger.info.assert_called_with("Mock ASR service initialized")
            
            # Test transcription logging
            audio_data = b'\x00' * 1000
            await service.transcribe(audio_data)
            
            # Should have logged debug message
            mock_logger.debug.assert_called()
            debug_call_args = mock_logger.debug.call_args
            assert "Mock ASR transcription" in debug_call_args[0][0]
            
            # Test cleanup logging
            await service.cleanup()
            mock_logger.info.assert_called_with("Mock ASR service cleaned up")
    
    def test_mock_asr_config_properties(self, mock_asr_service, asr_config):
        """Test that MockASRService stores config properly."""
        assert mock_asr_service.config == asr_config
        assert mock_asr_service.config.model_name == "base"
        assert mock_asr_service.config.language == "en"
        assert mock_asr_service.config.beam_size == 5
        assert mock_asr_service.config.best_of == 3
        assert mock_asr_service.config.temperature == 0.0
        assert mock_asr_service.config.compute_type == "float16"
    
    def test_mock_asr_mock_texts_list(self, mock_asr_service):
        """Test that mock texts list is properly defined."""
        assert hasattr(mock_asr_service, 'mock_texts')
        assert isinstance(mock_asr_service.mock_texts, list)
        assert len(mock_asr_service.mock_texts) > 0
        
        # All mock texts should be non-empty strings
        for text in mock_asr_service.mock_texts:
            assert isinstance(text, str)
            assert len(text) > 0
            assert len(text.split()) > 0  # Should contain words