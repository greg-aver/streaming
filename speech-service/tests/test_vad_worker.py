"""
Tests for VAD Worker implementation.

This module tests the VADWorker Event-driven functionality including:
- Event subscription and publishing
- Integration with Mock VAD Service
- Audio chunk processing workflow
- Error handling and timeout management
- Concurrent task management
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from app.workers.vad import VADWorker
from app.services.vad_service import MockVADService
from app.events import AsyncEventBus
from app.models.audio import AudioChunkModel, ProcessingResultModel
from app.interfaces.events import Event
from app.interfaces.services import WorkerError
from app.services.vad_service import VADServiceError
from app.config import ProcessingSettings, VADSettings


class TestVADWorker:
    """Test cases for VADWorker."""
    
    @pytest.fixture
    def processing_config(self):
        """Create test processing configuration."""
        return ProcessingSettings(
            max_concurrent_workers=2,
            chunk_timeout_seconds=5,  # int, not float
            max_chunk_size_bytes=1024 * 1024  # 1MB
        )
    
    @pytest.fixture
    def vad_config(self):
        """Create test VAD configuration."""
        return VADSettings(
            model_name="silero_vad",
            confidence_threshold=0.5,
            frame_duration_ms=30,
            sample_rate=16000
        )
    
    @pytest.fixture
    def event_bus(self):
        """Create AsyncEventBus instance."""
        return AsyncEventBus()
    
    @pytest.fixture
    def mock_vad_service(self, vad_config):
        """Create MockVADService instance."""
        return MockVADService(vad_config)
    
    @pytest.fixture
    def vad_worker(self, event_bus, mock_vad_service, processing_config):
        """Create VADWorker instance with Clean DI pattern."""
        worker = VADWorker(vad_service=mock_vad_service, config=processing_config)
        worker.set_event_bus(event_bus)
        return worker
    
    @pytest.mark.asyncio
    async def test_vad_worker_initialization(self, vad_worker):
        """Test worker initialization and state."""
        assert not vad_worker.is_running
        assert len(vad_worker.processing_tasks) == 0
        assert vad_worker.max_concurrent_tasks == 2
        assert vad_worker.chunk_timeout == 5
        assert vad_worker.vad_service is not None
    
    @pytest.mark.asyncio
    async def test_vad_worker_start_stop(self, vad_worker, event_bus):
        """Test worker start and stop lifecycle."""
        # Initialize VAD service first
        await vad_worker.vad_service.initialize()
        
        # Initially not running
        assert not vad_worker.is_running
        
        # Start worker
        await vad_worker.start()
        assert vad_worker.is_running
        
        # Check event subscription
        subscribers = await event_bus.get_subscribers("audio_chunk_received")
        assert len(subscribers) == 1
        
        # Stop worker
        await vad_worker.stop()
        assert not vad_worker.is_running
        
        # Check cleanup
        subscribers = await event_bus.get_subscribers("audio_chunk_received")
        assert len(subscribers) == 0
    
    @pytest.mark.asyncio
    async def test_vad_worker_process_chunk(self, vad_worker):
        """Test direct chunk processing."""
        await vad_worker.start()
        
        # Create test audio chunk
        chunk = AudioChunkModel(
            session_id="test_session",
            chunk_id=1,
            data=b"x" * 32000,  # 1 second at 16kHz 16-bit
            sample_rate=16000
        )
        
        # Process chunk
        result = await vad_worker.process_chunk(chunk)
        
        # Verify result
        assert isinstance(result, ProcessingResultModel)
        assert result.session_id == "test_session"
        assert result.chunk_id == 1
        assert result.component == "vad"
        assert result.success is True
        assert "is_speech" in result.result
        assert "confidence" in result.result
        assert result.processing_time_ms >= 0  # Mock может работать мгновенно
    
    @pytest.mark.asyncio
    async def test_vad_worker_event_handling(self, vad_worker, event_bus):
        """Test event-driven audio chunk processing."""
        await vad_worker.start()
        
        # Create list to capture published events
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        # Subscribe to result events
        await event_bus.subscribe("vad_completed", capture_event)
        await event_bus.subscribe("speech_detected", capture_event)
        
        # Create and publish audio chunk event
        audio_event = Event(
            name="audio_chunk_received",
            data={
                "session_id": "test_session",
                "chunk_id": 1,
                "data": b"x" * 32000,  # Should trigger speech detection in mock
            },
            source="test",
            correlation_id="test_correlation"
        )
        
        # Publish event and wait for processing
        await event_bus.publish(audio_event)
        await asyncio.sleep(0.1)  # Give time for processing
        
        # Wait for any pending tasks
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Verify events were published
        assert len(published_events) >= 1  # At least vad_completed
        
        # Check vad_completed event
        vad_completed_events = [e for e in published_events if e.name == "vad_completed"]
        assert len(vad_completed_events) == 1
        
        vad_event = vad_completed_events[0]
        assert vad_event.data["session_id"] == "test_session"
        assert vad_event.data["chunk_id"] == 1
        assert vad_event.data["component"] == "vad"
        assert vad_event.correlation_id == "test_correlation"
        
        # Check if speech was detected (mock should detect speech for 32KB data)
        speech_detected_events = [e for e in published_events if e.name == "speech_detected"]
        if len(speech_detected_events) > 0:
            speech_event = speech_detected_events[0]
            assert speech_event.data["session_id"] == "test_session"
            assert speech_event.data["chunk_id"] == 1
            assert "vad_confidence" in speech_event.data
    
    @pytest.mark.asyncio
    async def test_vad_worker_speech_detection_flow(self, vad_worker, event_bus):
        """Test complete speech detection workflow."""
        await vad_worker.start()
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("vad_completed", capture_event)
        await event_bus.subscribe("speech_detected", capture_event)
        
        # Create audio chunk that should trigger speech detection
        large_audio_event = Event(
            name="audio_chunk_received",
            data={
                "session_id": "speech_session",
                "chunk_id": 5,
                "data": b"speech_data" * 5000,  # Large chunk to trigger speech
            },
            source="test",
            correlation_id="speech_test"
        )
        
        await event_bus.publish(large_audio_event)
        await asyncio.sleep(0.1)
        
        # Wait for processing
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Should have both vad_completed and speech_detected
        assert len(published_events) == 2
        
        event_names = [e.name for e in published_events]
        assert "vad_completed" in event_names
        assert "speech_detected" in event_names
    
    @pytest.mark.asyncio
    async def test_vad_worker_no_speech_detection(self, vad_worker, event_bus):
        """Test workflow when no speech is detected."""
        await vad_worker.start()
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("vad_completed", capture_event)
        await event_bus.subscribe("speech_detected", capture_event)
        
        # Create small audio chunk that won't trigger speech detection
        small_audio_event = Event(
            name="audio_chunk_received",
            data={
                "session_id": "no_speech_session",
                "chunk_id": 1,
                "data": b"x" * 100,  # Too small for mock to detect speech
            },
            source="test",
            correlation_id="no_speech_test"
        )
        
        await event_bus.publish(small_audio_event)
        await asyncio.sleep(0.1)
        
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Should only have vad_completed, no speech_detected
        assert len(published_events) == 1
        assert published_events[0].name == "vad_completed"
        assert published_events[0].data["success"] is True
    
    @pytest.mark.asyncio
    async def test_vad_worker_concurrent_processing(self, vad_worker, event_bus):
        """Test concurrent chunk processing within limits."""
        await vad_worker.start()
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("vad_completed", capture_event)
        
        # Create multiple audio events
        events = []
        for i in range(3):  # More than max_concurrent_tasks (2)
            event = Event(
                name="audio_chunk_received",
                data={
                    "session_id": f"session_{i}",
                    "chunk_id": i,
                    "data": b"x" * 16000,
                },
                source="test",
                correlation_id=f"test_{i}"
            )
            events.append(event)
        
        # Publish all events quickly
        for event in events:
            await event_bus.publish(event)
        
        await asyncio.sleep(0.2)  # Give time for processing
        
        # Wait for all tasks
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Should have processed some events (limited by max_concurrent_tasks)
        # Some might be dropped due to concurrency limits
        assert len(published_events) >= 1
        assert len(published_events) <= 3
    
    @pytest.mark.asyncio
    async def test_vad_worker_error_handling(self, vad_worker, event_bus):
        """Test error handling in VAD processing."""
        # Initialize VAD service first
        await vad_worker.vad_service.initialize()
        await vad_worker.start()
        
        # Mock VAD service to raise error
        vad_worker.vad_service.detect_speech = AsyncMock(
            side_effect=VADServiceError("Test VAD error")
        )
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("vad_completed", capture_event)
        
        # Create audio event
        error_event = Event(
            name="audio_chunk_received",
            data={
                "session_id": "error_session",
                "chunk_id": 1,
                "data": b"x" * 16000,
            },
            source="test",
            correlation_id="error_test"
        )
        
        await event_bus.publish(error_event)
        await asyncio.sleep(0.1)
        
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Should have published error result
        assert len(published_events) == 1
        error_result = published_events[0]
        assert error_result.name == "vad_completed"
        assert error_result.data["success"] is False
        assert "error" in error_result.data["result"]  # error в result, не в data
    
    @pytest.mark.asyncio
    async def test_vad_worker_not_running_error(self, vad_worker):
        """Test error when processing chunk while not running."""
        # Don't start worker
        assert not vad_worker.is_running
        
        chunk = AudioChunkModel(
            session_id="test",
            chunk_id=1,
            data=b"x" * 1000
        )
        
        with pytest.raises(WorkerError, match="not running"):
            await vad_worker.process_chunk(chunk)
    
    @pytest.mark.asyncio
    async def test_vad_worker_timeout_handling(self, vad_worker, event_bus):
        """Test timeout handling for long-running VAD operations."""
        # Set very short timeout
        vad_worker.chunk_timeout = 0.01  # 10ms
        
        await vad_worker.start()
        
        # Mock slow VAD service
        async def slow_detect_speech(*args, **kwargs):
            await asyncio.sleep(0.1)  # Longer than timeout
            return {"is_speech": True, "confidence": 0.8}
        
        vad_worker.vad_service.detect_speech = slow_detect_speech
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("vad_completed", capture_event)
        
        # Create audio event
        timeout_event = Event(
            name="audio_chunk_received",
            data={
                "session_id": "timeout_session",
                "chunk_id": 1,
                "data": b"x" * 16000,
            },
            source="test",
            correlation_id="timeout_test"
        )
        
        await event_bus.publish(timeout_event)
        await asyncio.sleep(0.2)  # Wait for timeout
        
        if vad_worker.processing_tasks:
            await asyncio.gather(*vad_worker.processing_tasks, return_exceptions=True)
        
        # Should have timeout error
        assert len(published_events) == 1
        timeout_result = published_events[0]
        assert timeout_result.name == "vad_completed"
        assert timeout_result.data["success"] is False
        assert "timeout" in timeout_result.data["result"]["error"].lower()
    
    @pytest.mark.asyncio
    async def test_vad_worker_get_status(self, vad_worker):
        """Test worker status reporting."""
        status = vad_worker.get_status()
        
        assert "is_running" in status
        assert "processing_tasks" in status
        assert "max_concurrent_tasks" in status
        assert "chunk_timeout" in status
        assert "vad_service_info" in status
        
        assert status["is_running"] is False
        assert status["processing_tasks"] == 0
        assert status["max_concurrent_tasks"] == 2
    
    @pytest.mark.asyncio
    async def test_vad_worker_cleanup_on_stop(self, vad_worker, event_bus):
        """Test proper cleanup when stopping worker."""
        # Initialize VAD service first
        await vad_worker.vad_service.initialize()
        await vad_worker.start()
        
        # Create some processing tasks
        async def dummy_task():
            await asyncio.sleep(0.1)
        
        task1 = asyncio.create_task(dummy_task())
        task2 = asyncio.create_task(dummy_task())
        vad_worker.processing_tasks.add(task1)
        vad_worker.processing_tasks.add(task2)
        
        # Stop worker (should wait for tasks)
        await vad_worker.stop()
        
        # Tasks should be completed
        assert task1.done()
        assert task2.done()
        # Note: processing_tasks may still contain finished tasks, that's OK