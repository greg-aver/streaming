"""
Tests for ASR Worker implementation.

Tests Event-driven ASR Worker functionality:
- Event subscription (speech_detected)
- Event publishing (asr_completed)  
- Integration with Mock ASR Service
- Error handling and timeout management
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.workers.asr import ASRWorker
from app.services.asr_service import MockASRService, ASRServiceError
from app.events import AsyncEventBus
from app.models.audio import ProcessingResultModel
from app.interfaces.events import Event
from app.interfaces.services import WorkerError
from app.config import ProcessingSettings, ASRSettings


class TestASRWorker:
    """Test cases for ASRWorker."""
    
    @pytest.fixture
    def processing_config(self):
        """Create test processing configuration."""
        return ProcessingSettings(
            max_concurrent_workers=2,
            chunk_timeout_seconds=5,
            max_chunk_size_bytes=1024 * 1024
        )
    
    @pytest.fixture
    def asr_config(self):
        """Create test ASR configuration."""
        return ASRSettings(
            model_name="base",
            language="ru",  # Русский язык для проекта
            beam_size=5,
            best_of=5
        )
    
    @pytest.fixture
    def event_bus(self):
        """Create AsyncEventBus instance."""
        return AsyncEventBus()
    
    @pytest.fixture
    def mock_asr_service(self, asr_config):
        """Create MockASRService instance."""
        return MockASRService(asr_config)
    
    @pytest.fixture
    def asr_worker(self, event_bus, mock_asr_service, processing_config):
        """Create ASRWorker instance with mocked dependencies."""
        # Create worker without dependency injection
        worker = ASRWorker.__new__(ASRWorker)
        
        # Initialize manually to avoid DI
        from app.events import EventSubscriberMixin, EventPublisherMixin
        EventSubscriberMixin.__init__(worker, event_bus)
        EventPublisherMixin.__init__(worker, event_bus, "asr_worker")
        
        worker.asr_service = mock_asr_service
        worker.config = processing_config
        worker.logger = MagicMock()
        
        # Worker state
        worker.is_running = False
        worker.processing_tasks = set()
        worker.max_concurrent_tasks = processing_config.max_concurrent_workers
        worker.chunk_timeout = processing_config.chunk_timeout_seconds
        
        return worker
    
    @pytest.mark.asyncio
    async def test_asr_worker_initialization(self, asr_worker):
        """Test worker initialization and state."""
        assert not asr_worker.is_running
        assert len(asr_worker.processing_tasks) == 0
        assert asr_worker.max_concurrent_tasks == 2
        assert asr_worker.chunk_timeout == 5
        assert asr_worker.asr_service is not None
    
    @pytest.mark.asyncio
    async def test_asr_worker_start_stop(self, asr_worker, event_bus):
        """Test worker start and stop lifecycle."""
        # Initialize ASR service first
        await asr_worker.asr_service.initialize()
        
        # Initially not running
        assert not asr_worker.is_running
        
        # Start worker
        await asr_worker.start()
        assert asr_worker.is_running
        
        # Check event subscription
        subscribers = await event_bus.get_subscribers("speech_detected")
        assert len(subscribers) == 1
        
        # Stop worker
        await asr_worker.stop()
        assert not asr_worker.is_running
        
        # Check cleanup
        subscribers = await event_bus.get_subscribers("speech_detected")
        assert len(subscribers) == 0
    
    @pytest.mark.asyncio
    async def test_asr_worker_process_chunk(self, asr_worker):
        """Test direct chunk processing."""
        # Initialize and start
        await asr_worker.asr_service.initialize()
        await asr_worker.start()
        
        # Process speech audio
        result = await asr_worker.process_chunk(
            audio_data=b"speech" * 1000,  # 5KB speech data
            sample_rate=16000,
            session_id="test_session",
            chunk_id=1
        )
        
        # Verify result
        assert isinstance(result, ProcessingResultModel)
        assert result.session_id == "test_session"
        assert result.chunk_id == 1
        assert result.component == "asr"
        assert result.success is True
        assert "text" in result.result
        assert "confidence" in result.result
        assert result.processing_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_asr_worker_speech_event_handling(self, asr_worker, event_bus):
        """Test handling speech_detected events."""
        # Initialize and start
        await asr_worker.asr_service.initialize()
        await asr_worker.start()
        
        # Capture published events
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("asr_completed", capture_event)
        
        # Create speech_detected event
        speech_event = Event(
            name="speech_detected",
            data={
                "session_id": "test_session",
                "chunk_id": 2,
                "data": b"hello world" * 500,  # Mock speech data
                "sample_rate": 16000,
                "vad_confidence": 0.95
            },
            source="vad_worker",
            correlation_id="test_correlation"
        )
        
        # Publish and wait
        await event_bus.publish(speech_event)
        await asyncio.sleep(0.1)
        
        if asr_worker.processing_tasks:
            await asyncio.gather(*asr_worker.processing_tasks, return_exceptions=True)
        
        # Verify ASR result published
        assert len(published_events) == 1
        asr_result = published_events[0]
        assert asr_result.name == "asr_completed"
        assert asr_result.data["session_id"] == "test_session"
        assert asr_result.data["chunk_id"] == 2
        assert asr_result.data["component"] == "asr"
        assert asr_result.data["success"] is True
        assert asr_result.correlation_id == "test_correlation"
    
    @pytest.mark.asyncio
    async def test_asr_worker_transcription_quality(self, asr_worker, event_bus):
        """Test transcription result quality."""
        await asr_worker.asr_service.initialize()
        await asr_worker.start()
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("asr_completed", capture_event)
        
        # Large speech chunk should produce good transcription
        large_speech_event = Event(
            name="speech_detected",
            data={
                "session_id": "quality_test",
                "chunk_id": 1,
                "data": b"high quality speech data" * 1000,  # 24KB
                "sample_rate": 16000,
                "vad_confidence": 0.98
            },
            source="vad_worker",
            correlation_id="quality_test"
        )
        
        await event_bus.publish(large_speech_event)
        await asyncio.sleep(0.1)
        
        if asr_worker.processing_tasks:
            await asyncio.gather(*asr_worker.processing_tasks, return_exceptions=True)
        
        assert len(published_events) == 1
        result = published_events[0]
        transcription = result.data["result"]
        
        # Check transcription quality
        assert len(transcription["text"]) > 0
        assert transcription["confidence"] > 0.0
        assert "segments" in transcription
        assert len(transcription["segments"]) > 0
    
    @pytest.mark.asyncio
    async def test_asr_worker_error_handling(self, asr_worker, event_bus):
        """Test error handling in ASR processing."""
        await asr_worker.asr_service.initialize()
        await asr_worker.start()
        
        # Mock ASR service to raise error
        asr_worker.asr_service.transcribe = AsyncMock(
            side_effect=ASRServiceError("Test ASR error")
        )
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("asr_completed", capture_event)
        
        # Create speech event
        error_event = Event(
            name="speech_detected",
            data={
                "session_id": "error_session",
                "chunk_id": 1,
                "data": b"error_data" * 100,
                "sample_rate": 16000,
                "vad_confidence": 0.8
            },
            source="vad_worker",
            correlation_id="error_test"
        )
        
        await event_bus.publish(error_event)
        await asyncio.sleep(0.1)
        
        if asr_worker.processing_tasks:
            await asyncio.gather(*asr_worker.processing_tasks, return_exceptions=True)
        
        # Should have error result
        assert len(published_events) == 1
        error_result = published_events[0]
        assert error_result.name == "asr_completed"
        assert error_result.data["success"] is False
        assert "error" in error_result.data["result"]
    
    @pytest.mark.asyncio
    async def test_asr_worker_not_running_error(self, asr_worker):
        """Test error when processing while not running."""
        assert not asr_worker.is_running
        
        with pytest.raises(WorkerError, match="not running"):
            await asr_worker.process_chunk(
                audio_data=b"test" * 100,
                sample_rate=16000,
                session_id="test",
                chunk_id=1
            )
    
    @pytest.mark.asyncio
    async def test_asr_worker_concurrent_processing(self, asr_worker, event_bus):
        """Test concurrent speech processing."""
        await asr_worker.asr_service.initialize()
        await asr_worker.start()
        
        published_events = []
        
        async def capture_event(event: Event):
            published_events.append(event)
        
        await event_bus.subscribe("asr_completed", capture_event)
        
        # Create multiple speech events
        events = []
        for i in range(3):  # More than max_concurrent_tasks (2)
            event = Event(
                name="speech_detected",
                data={
                    "session_id": f"session_{i}",
                    "chunk_id": i,
                    "data": b"concurrent_speech" * 100,
                    "sample_rate": 16000,
                    "vad_confidence": 0.9
                },
                source="vad_worker",
                correlation_id=f"concurrent_{i}"
            )
            events.append(event)
        
        # Publish all events
        for event in events:
            await event_bus.publish(event)
        
        await asyncio.sleep(0.2)
        
        if asr_worker.processing_tasks:
            await asyncio.gather(*asr_worker.processing_tasks, return_exceptions=True)
        
        # Should process some events (limited by concurrency)
        assert len(published_events) >= 1
        assert len(published_events) <= 3
    
    @pytest.mark.asyncio
    async def test_asr_worker_get_status(self, asr_worker):
        """Test worker status reporting."""
        status = asr_worker.get_status()
        
        assert "is_running" in status
        assert "processing_tasks" in status
        assert "max_concurrent_tasks" in status
        assert "chunk_timeout" in status
        assert "asr_service_info" in status
        
        assert status["is_running"] is False
        assert status["processing_tasks"] == 0
        assert status["max_concurrent_tasks"] == 2