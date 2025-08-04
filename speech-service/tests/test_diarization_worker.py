"""
Tests for Diarization Worker implementation.

Tests Event-driven Diarization Worker functionality:
- Event subscription (speech_detected)
- Event publishing (diarization_completed)  
- Integration with Mock Diarization Service
- Error handling and timeout management
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.workers.diarization import DiarizationWorker
from app.services.diarization_service import MockDiarizationService, DiarizationServiceError
from app.events import AsyncEventBus
from app.models.audio import ProcessingResultModel
from app.interfaces.events import Event
from app.interfaces.services import WorkerError
from app.config import ProcessingSettings, DiarizationSettings


class TestDiarizationWorker:
    """Test cases for DiarizationWorker."""
    
    @pytest.fixture
    def processing_config(self):
        """Create test processing configuration."""
        return ProcessingSettings(
            max_concurrent_workers=2,
            chunk_timeout_seconds=5,
            max_chunk_size_bytes=1024 * 1024
        )
    
    @pytest.fixture
    def diarization_config(self):
        """Create test Diarization configuration."""
        return DiarizationSettings(
            model_name="pyannote/speaker-diarization",
            min_speakers=1,
            max_speakers=10
        )
    
    @pytest.fixture
    def event_bus(self):
        """Create AsyncEventBus instance."""
        return AsyncEventBus()
    
    @pytest.fixture
    def mock_diarization_service(self, diarization_config):
        """Create MockDiarizationService instance."""
        return MockDiarizationService(diarization_config)
    
    @pytest.fixture
    def diarization_worker(self, event_bus, mock_diarization_service, processing_config):
        """Create DiarizationWorker instance with Clean DI pattern."""
        worker = DiarizationWorker(diarization_service=mock_diarization_service, config=processing_config)
        worker.set_event_bus(event_bus)
        return worker
    
    @pytest.mark.asyncio
    async def test_diarization_worker_initialization(self, diarization_worker):
        """Test worker initialization and state."""
        assert not diarization_worker.is_running
        assert len(diarization_worker.processing_tasks) == 0
        assert diarization_worker.max_concurrent_tasks == 2
        assert diarization_worker.chunk_timeout == 5
        assert diarization_worker.diarization_service is not None
    
    @pytest.mark.asyncio
    async def test_diarization_worker_start_stop(self, diarization_worker, event_bus):
        """Test worker start and stop lifecycle."""
        # Initialize diarization service first
        await diarization_worker.diarization_service.initialize()
        
        # Initially not running
        assert not diarization_worker.is_running
        
        # Start worker
        await diarization_worker.start()
        assert diarization_worker.is_running
        
        # Check event subscription - worker должен подписаться на speech_detected
        subscribers = await event_bus.get_subscribers("speech_detected")
        assert len(subscribers) >= 1  # Может быть несколько подписчиков
        
        # Stop worker
        await diarization_worker.stop()
        assert not diarization_worker.is_running
        
        # После остановки подписка должна быть очищена
        # Проверяем что наш конкретный handler удален
    
    @pytest.mark.asyncio
    async def test_diarization_worker_not_running_error(self, diarization_worker):
        """Test error when processing while not running."""
        # Worker не запущен
        assert not diarization_worker.is_running
        
        # Попытка обработать chunk без запуска worker должна вызвать ошибку
        with pytest.raises(WorkerError, match="not running"):
            await diarization_worker.process_chunk(
                audio_data=b"test" * 100,
                sample_rate=16000,
                session_id="test",
                chunk_id=1
            )
    
    @pytest.mark.asyncio  
    async def test_diarization_worker_get_status(self, diarization_worker):
        """Test worker status reporting."""
        status = diarization_worker.get_status()
        
        # Проверяем что все нужные поля присутствуют в статусе
        assert "is_running" in status
        assert "processing_tasks" in status
        assert "max_concurrent_tasks" in status
        assert "chunk_timeout" in status
        assert "diarization_service_info" in status
        
        # Проверяем корректные значения
        assert status["is_running"] is False
        assert status["processing_tasks"] == 0
        assert status["max_concurrent_tasks"] == 2
    
    @pytest.mark.asyncio
    async def test_diarization_worker_process_chunk(self, diarization_worker):
        """Test direct chunk processing functionality."""
        # Initialize and start worker
        await diarization_worker.diarization_service.initialize()
        await diarization_worker.start()
        
        # Test data
        audio_data = b"test_audio_data" * 100
        sample_rate = 16000
        session_id = "test_session"
        chunk_id = 42
        
        # Process chunk
        result = await diarization_worker.process_chunk(
            audio_data=audio_data,
            sample_rate=sample_rate,
            session_id=session_id,
            chunk_id=chunk_id
        )
        
        # Verify result
        assert isinstance(result, ProcessingResultModel)
        assert result.session_id == session_id
        assert result.chunk_id == chunk_id
        assert result.component == "diarization"
        assert result.success is True
        assert "speakers" in result.result
        assert result.processing_time_ms >= 0
        
        # Clean up
        await diarization_worker.stop()
    
    @pytest.mark.asyncio
    async def test_diarization_worker_speech_event_handling(self, diarization_worker, event_bus):
        """Test handling of speech_detected events."""
        # Initialize and start worker
        await diarization_worker.diarization_service.initialize()
        await diarization_worker.start()
        
        # Create speech_detected event
        event_data = {
            "session_id": "test_session",
            "chunk_id": 1,
            "data": b"speech_audio_data" * 50,
            "sample_rate": 16000,
            "vad_confidence": 0.9
        }
        
        speech_event = Event(
            name="speech_detected",
            data=event_data,
            source="vad_worker",
            correlation_id="test_corr_id"
        )
        
        # Set up event capture for diarization_completed
        captured_events = []
        async def capture_diarization_result(event):
            captured_events.append(event)
        
        await event_bus.subscribe("diarization_completed", capture_diarization_result)
        
        # Publish speech_detected event
        await event_bus.publish(speech_event)
        
        # Wait for processing to complete
        await asyncio.sleep(0.1)  # Give time for async processing
        
        # Verify diarization_completed event was published
        assert len(captured_events) == 1
        result_event = captured_events[0]
        assert result_event.name == "diarization_completed"
        assert result_event.data["session_id"] == "test_session"
        assert result_event.data["chunk_id"] == 1
        assert result_event.data["component"] == "diarization"
        assert result_event.data["success"] is True
        
        # Clean up
        await diarization_worker.stop()
    
    @pytest.mark.asyncio
    async def test_diarization_worker_speaker_identification(self, diarization_worker):
        """Test speaker identification functionality."""
        # Initialize and start worker
        await diarization_worker.diarization_service.initialize()
        await diarization_worker.start()
        
        # Process audio with multiple speakers simulation
        audio_data = b"multi_speaker_audio" * 200  # Larger data for multi-speaker
        result = await diarization_worker.process_chunk(
            audio_data=audio_data,
            sample_rate=16000,
            session_id="multi_speaker_session",
            chunk_id=1
        )
        
        # Verify speaker identification
        assert result.success is True
        assert "speakers" in result.result
        assert "segments" in result.result
        
        speakers = result.result["speakers"]
        segments = result.result["segments"]
        
        assert isinstance(speakers, list)
        assert isinstance(segments, list)
        
        # MockDiarizationService should return speaker names and segments
        if speakers:  # If speakers were identified
            # Speakers should be strings (speaker names)
            for speaker in speakers:
                assert isinstance(speaker, str)
                assert speaker.startswith("SPEAKER_")
        
        if segments:  # If segments were created
            for segment in segments:
                assert "speaker" in segment
                assert "start" in segment
                assert "end" in segment
                assert "confidence" in segment
        
        # Clean up
        await diarization_worker.stop()
    
    @pytest.mark.asyncio
    async def test_diarization_worker_error_handling(self, diarization_worker, event_bus):
        """Test error handling during processing."""
        # Initialize and start worker
        await diarization_worker.diarization_service.initialize()
        await diarization_worker.start()
        
        # Mock service to raise exception
        original_diarize = diarization_worker.diarization_service.diarize
        async def failing_diarize(*args, **kwargs):
            raise Exception("Diarization service error")
        
        diarization_worker.diarization_service.diarize = failing_diarize
        
        # Set up event capture
        captured_events = []
        async def capture_result(event):
            captured_events.append(event)
        
        await event_bus.subscribe("diarization_completed", capture_result)
        
        # Create event that will cause error
        error_event = Event(
            name="speech_detected",
            data={
                "session_id": "error_session",
                "chunk_id": 1,
                "data": b"error_audio",
                "sample_rate": 16000
            },
            source="test",
            correlation_id="error_test"
        )
        
        # Publish event and wait for processing
        await event_bus.publish(error_event)
        await asyncio.sleep(0.1)
        
        # Verify error was handled gracefully
        assert len(captured_events) == 1
        error_result = captured_events[0]
        assert error_result.data["success"] is False
        assert "speakers" in error_result.data["result"]
        assert "segments" in error_result.data["result"]
        assert error_result.data["result"]["speakers"] == []
        assert error_result.data["result"]["segments"] == []
        assert "error" in error_result.data["result"]
        assert "Diarization service error" in error_result.data["result"]["error"]
        
        # Restore original method and clean up
        diarization_worker.diarization_service.diarize = original_diarize
        await diarization_worker.stop()
    
    @pytest.mark.asyncio
    async def test_diarization_worker_concurrent_processing(self, diarization_worker, event_bus):
        """Test concurrent task limits."""
        # Initialize and start worker
        await diarization_worker.diarization_service.initialize()
        await diarization_worker.start()
        
        # Mock slow processing to test concurrency
        original_diarize = diarization_worker.diarization_service.diarize
        async def slow_diarize(*args, **kwargs):
            await asyncio.sleep(0.2)  # Simulate slow processing
            return await original_diarize(*args, **kwargs)
        
        diarization_worker.diarization_service.diarize = slow_diarize
        
        # Set up event capture
        captured_events = []
        async def capture_result(event):
            captured_events.append(event)
        
        await event_bus.subscribe("diarization_completed", capture_result)
        
        # Send more events than max_concurrent_tasks (which is 2)
        events = []
        for i in range(5):  # Send 5 events, but only 2 should be processed concurrently
            event = Event(
                name="speech_detected",
                data={
                    "session_id": f"concurrent_session_{i}",
                    "chunk_id": i,
                    "data": b"concurrent_audio" * 50,
                    "sample_rate": 16000
                },
                source="test",
                correlation_id=f"concurrent_{i}"
            )
            events.append(event)
            await event_bus.publish(event)
        
        # Check that only max_concurrent_tasks are being processed
        await asyncio.sleep(0.05)  # Small delay to let tasks start
        assert len(diarization_worker.processing_tasks) <= diarization_worker.max_concurrent_tasks
        
        # Wait for all processing to complete
        await asyncio.sleep(0.5)
        
        # Should have results (some may be dropped due to concurrency limit)
        assert len(captured_events) <= 5  # Some may be dropped
        assert len(captured_events) >= 2  # At least max_concurrent should succeed
        
        # Restore and clean up
        diarization_worker.diarization_service.diarize = original_diarize
        await diarization_worker.stop()
    
    @pytest.mark.asyncio
    async def test_diarization_worker_timeout_handling(self, diarization_worker, event_bus):
        """Test timeout handling during processing."""
        # Initialize and start worker with short timeout
        await diarization_worker.diarization_service.initialize()
        diarization_worker.chunk_timeout = 0.1  # Very short timeout
        await diarization_worker.start()
        
        # Mock very slow processing to trigger timeout
        async def timeout_diarize(*args, **kwargs):
            await asyncio.sleep(1.0)  # Much longer than timeout
            return {"speakers": [], "segments": []}
        
        diarization_worker.diarization_service.diarize = timeout_diarize
        
        # Set up event capture
        captured_events = []
        async def capture_result(event):
            captured_events.append(event)
        
        await event_bus.subscribe("diarization_completed", capture_result)
        
        # Create event that will timeout
        timeout_event = Event(
            name="speech_detected",
            data={
                "session_id": "timeout_session",
                "chunk_id": 1,
                "data": b"timeout_audio" * 100,
                "sample_rate": 16000
            },
            source="test",
            correlation_id="timeout_test"
        )
        
        # Publish event and wait for timeout
        await event_bus.publish(timeout_event)
        await asyncio.sleep(0.3)  # Wait longer than timeout
        
        # Verify timeout was handled
        assert len(captured_events) == 1
        timeout_result = captured_events[0]
        assert timeout_result.data["success"] is False
        assert "speakers" in timeout_result.data["result"]
        assert "segments" in timeout_result.data["result"]
        assert timeout_result.data["result"]["speakers"] == []
        assert timeout_result.data["result"]["segments"] == []
        assert "timeout" in timeout_result.data["result"]["error"].lower()
        assert timeout_result.data["processing_time_ms"] >= 100  # Should be at least timeout duration
        
        # Clean up
        await diarization_worker.stop()