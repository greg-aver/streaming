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
        """Create DiarizationWorker instance with mocked dependencies."""
        # Create worker without dependency injection
        worker = DiarizationWorker.__new__(DiarizationWorker)
        
        # Initialize manually to avoid DI
        from app.events import EventSubscriberMixin, EventPublisherMixin
        EventSubscriberMixin.__init__(worker, event_bus)
        EventPublisherMixin.__init__(worker, event_bus, "diarization_worker")
        
        worker.diarization_service = mock_diarization_service
        worker.config = processing_config
        worker.logger = MagicMock()
        
        # Worker state
        worker.is_running = False
        worker.processing_tasks = set()
        worker.max_concurrent_tasks = processing_config.max_concurrent_workers
        worker.chunk_timeout = processing_config.chunk_timeout_seconds
        
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
    
    # TODO: Add remaining tests:
    # - test_diarization_worker_process_chunk  
    # - test_diarization_worker_speech_event_handling
    # - test_diarization_worker_speaker_identification
    # - test_diarization_worker_error_handling
    # - test_diarization_worker_concurrent_processing
    # - test_diarization_worker_timeout_handling