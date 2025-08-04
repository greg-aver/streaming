"""
Voice Activity Detection (VAD) worker implementation with Clean DI.

Senior approach: Direct dependency injection without mixins for better testability
and cleaner architecture. This module provides VAD worker that processes audio chunks 
and publishes results.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Set
import structlog

from ..interfaces.services import IVADService, IWorker, WorkerError
from ..interfaces.events import IEventBus, Event
from ..models.audio import AudioChunkModel, ProcessingResultModel
from ..config import ProcessingSettings


class VADWorker(IWorker):
    """
    VAD Worker implementation with Clean DI approach.
    
    Senior pattern: Direct dependency injection без mixins для лучшей testability.
    Subscribes to audio_chunk_received events, processes audio through VAD service,
    and publishes vad_completed and speech_detected events.
    """
    
    def __init__(
        self, 
        vad_service: IVADService, 
        config: ProcessingSettings
    ):
        """
        Initialize the VAD worker with dependency injection.
        
        Senior approach: Получаем зависимости через конструктор, event_bus через setter
        
        Args:
            vad_service: VAD service for speech detection  
            config: Processing configuration settings
        """
        self.vad_service = vad_service
        self.config = config
        
        # Internal state management
        self.is_running = False
        self.processing_tasks: Set[asyncio.Task] = set()
        self.max_concurrent_tasks = config.max_concurrent_workers
        self.chunk_timeout = config.chunk_timeout_seconds
        
        # Event bus will be set via set_event_bus() 
        # Senior pattern: separate object creation from configuration
        self._event_bus: Optional[IEventBus] = None
        
        # Logging
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        self.logger.info(
            "VAD worker initialized",
            max_concurrent_tasks=self.max_concurrent_tasks,
            chunk_timeout=self.chunk_timeout
        )
    
    def set_event_bus(self, event_bus: IEventBus) -> None:
        """
        Set event bus for this worker.
        
        Senior pattern: Setter injection for circular dependency avoidance
        """
        self._event_bus = event_bus
    
    @property 
    def event_bus(self) -> IEventBus:
        """Get event bus with validation."""
        if self._event_bus is None:
            raise WorkerError("Event bus not configured. Call set_event_bus() first.")
        return self._event_bus
    
    async def start(self) -> None:
        """
        Start the worker and set up event subscriptions.
        
        Senior approach: Proper initialization order with error handling
        
        Raises:
            WorkerError: If worker startup fails
        """
        try:
            self.logger.info("Starting VAD worker")
            
            # Phase 1: Initialize VAD service
            await self.vad_service.initialize()
            self.logger.info("VAD service initialized")
            
            # Phase 2: Set up event subscriptions
            await self.event_bus.subscribe("audio_chunk_received", self._handle_audio_chunk)
            self.logger.info("Subscribed to audio_chunk_received events")
            
            # Phase 3: Mark as running
            self.is_running = True
            self.logger.info("VAD worker started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start VAD worker", error=str(e), exc_info=True)
            await self._cleanup_on_error()
            raise WorkerError(f"VAD worker startup failed: {e}")
    
    async def stop(self) -> None:
        """
        Stop the worker and clean up resources.
        
        Senior approach: Graceful shutdown with proper resource cleanup
        """
        self.logger.info("Stopping VAD worker")
        
        # Phase 1: Mark as not running (stop accepting new work)
        self.is_running = False
        
        # Phase 2: Wait for current tasks to complete
        if self.processing_tasks:
            self.logger.info(f"Waiting for {len(self.processing_tasks)} tasks to complete")
            
            # Wait with timeout
            done, pending = await asyncio.wait(
                self.processing_tasks, 
                timeout=self.chunk_timeout * 2,
                return_when=asyncio.ALL_COMPLETED
            )
            
            # Force cancel pending tasks
            if pending:
                self.logger.warning(f"Force cancelling {len(pending)} pending tasks")
                for task in pending:
                    task.cancel()
                
                # Wait for cancellation to complete
                await asyncio.gather(*pending, return_exceptions=True)
        
        # Phase 3: Unsubscribe from events
        try:
            await self.event_bus.unsubscribe("audio_chunk_received", self._handle_audio_chunk)
            self.logger.info("Unsubscribed from events")
        except Exception as e:
            self.logger.warning("Error unsubscribing from events", error=str(e))
        
        # Phase 4: Cleanup service
        try:
            await self.vad_service.cleanup()
            self.logger.info("VAD service cleaned up")
        except Exception as e:
            self.logger.warning("Error cleaning up VAD service", error=str(e))
        
        self.logger.info("VAD worker stopped successfully")
    
    async def _handle_audio_chunk(self, event: Event) -> None:
        """
        Handle incoming audio chunk events.
        
        Senior approach: Proper concurrency control and error handling
        """
        if not self.is_running:
            self.logger.debug("Ignoring event - worker not running")
            return
        
        # Check concurrency limits
        if len(self.processing_tasks) >= self.max_concurrent_tasks:
            self.logger.warning(
                "Max concurrent tasks reached, dropping audio chunk",
                active_tasks=len(self.processing_tasks),
                max_tasks=self.max_concurrent_tasks
            )
            return
        
        # Create processing task
        task = asyncio.create_task(self._process_audio_chunk(event))
        self.processing_tasks.add(task)
        
        # Clean up completed tasks
        task.add_done_callback(self.processing_tasks.discard)
    
    async def _process_audio_chunk(self, event: Event) -> None:
        """
        Process individual audio chunk.
        
        Senior approach: Comprehensive error handling and performance tracking
        """
        start_time = time.time()
        chunk_data = event.data
        
        try:
            # Parse audio chunk
            audio_chunk = AudioChunkModel(**chunk_data)
            
            self.logger.debug(
                "Processing audio chunk",
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                data_size=len(audio_chunk.data)
            )
            
            # Process through VAD service with timeout
            result = await asyncio.wait_for(
                self.vad_service.detect_speech(audio_chunk.data, audio_chunk.sample_rate),
                timeout=self.chunk_timeout
            )
            
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Create result model
            processing_result = ProcessingResultModel(
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                component="vad",
                result=result if isinstance(result, dict) else result.model_dump(),
                processing_time_ms=processing_time,
                success=True
            )
            
            # Publish results
            await self._publish_results(processing_result, result, event.correlation_id, chunk_data)
            
            self.logger.debug(
                "Audio chunk processed successfully",
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                processing_time_ms=processing_time,
                is_speech=result.get("is_speech", False) if isinstance(result, dict) else result.is_speech
            )
            
        except asyncio.TimeoutError:
            processing_time = (time.time() - start_time) * 1000
            await self._handle_processing_error(
                chunk_data, "Processing timeout", processing_time
            )
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            await self._handle_processing_error(
                chunk_data, str(e), processing_time
            )
    
    async def _publish_results(self, processing_result: ProcessingResultModel, vad_result, correlation_id: str = None, chunk_data: Dict[str, Any] = None) -> None:
        """
        Publish processing results.
        
        Senior approach: Separate result publishing for better maintainability
        """
        # Always publish vad_completed
        vad_completed_event = Event(
            name="vad_completed",
            data=processing_result.model_dump(),
            source="vad_worker",
            correlation_id=correlation_id
        )
        await self.event_bus.publish(vad_completed_event)
        
        # Publish speech_detected if speech was detected
        if vad_result.get("is_speech", False):  # Handle dict result
            # Create special format for speech_detected event (for ASR/Diarization workers)
            speech_data = {
                "session_id": processing_result.session_id,
                "chunk_id": processing_result.chunk_id,
                "data": chunk_data.get("data"),  # Raw audio data for processing
                "sample_rate": chunk_data.get("sample_rate", 16000),
                "vad_confidence": vad_result.get("confidence", 0.0)
            }
            
            speech_detected_event = Event(
                name="speech_detected", 
                data=speech_data,
                source="vad_worker",
                correlation_id=correlation_id
            )
            await self.event_bus.publish(speech_detected_event)
    
    async def _handle_processing_error(
        self, 
        chunk_data: Dict[str, Any], 
        error_message: str,
        processing_time: float
    ) -> None:
        """
        Handle processing errors gracefully.
        
        Senior approach: Structured error handling with proper logging
        """
        self.logger.error(
            "VAD processing failed",
            error=error_message,
            session_id=chunk_data.get("session_id"),
            chunk_id=chunk_data.get("chunk_id"),
            processing_time_ms=processing_time
        )
        
        # Create error result with required VAD fields
        error_result = ProcessingResultModel(
            session_id=chunk_data.get("session_id", "unknown"),
            chunk_id=chunk_data.get("chunk_id", -1),
            component="vad",
            result={
                "is_speech": False,
                "confidence": 0.0,
                "error": error_message
            },
            processing_time_ms=processing_time,
            success=False
        )
        
        # Publish error result
        try:
            error_event = Event(
                name="vad_completed",
                data=error_result.model_dump(),
                source="vad_worker",
                correlation_id=None
            )
            await self.event_bus.publish(error_event)
        except Exception as publish_error:
            self.logger.error(
                "Failed to publish error result",
                error=str(publish_error),
                original_error=error_message
            )
    
    async def _cleanup_on_error(self) -> None:
        """Clean up resources when startup fails."""
        try:
            if self._event_bus:
                await self._event_bus.unsubscribe("audio_chunk_received", self._handle_audio_chunk)
        except Exception:
            pass  # Ignore cleanup errors during error handling
    
    async def process_chunk(self, audio_chunk: AudioChunkModel) -> ProcessingResultModel:
        """
        Process audio chunk and return VAD result.
        
        Senior approach: Compatibility method для интерфейса IWorker
        
        Args:
            audio_chunk: Audio chunk data to process
            
        Returns:
            Processing result with VAD detection data
            
        Raises:
            WorkerError: If processing fails
        """
        if not self.is_running:
            raise WorkerError("VAD worker is not running")
        
        start_time = time.time()
        
        try:
            # Run VAD detection
            result = await asyncio.wait_for(
                self.vad_service.detect_speech(audio_chunk.data, audio_chunk.sample_rate),
                timeout=self.chunk_timeout
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Create processing result
            processing_result = ProcessingResultModel(
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                component="vad",
                result=result if isinstance(result, dict) else result.model_dump(),
                processing_time_ms=processing_time_ms,
                success=True
            )
            
            self.logger.debug(
                "VAD processing completed",
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                is_speech=result.get("is_speech", False),
                confidence=result.get("confidence", 0.0),
                processing_time_ms=processing_time_ms
            )
            
            return processing_result
            
        except asyncio.TimeoutError:
            processing_time_ms = (time.time() - start_time) * 1000
            # Return error result
            return ProcessingResultModel(
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                component="vad",
                result={
                    "is_speech": False,
                    "confidence": 0.0,
                    "error": "Processing timeout"
                },
                processing_time_ms=processing_time_ms,
                success=False
            )
        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            # Return error result
            return ProcessingResultModel(
                session_id=audio_chunk.session_id,
                chunk_id=audio_chunk.chunk_id,
                component="vad",
                result={
                    "is_speech": False,
                    "confidence": 0.0,
                    "error": str(e)
                },
                processing_time_ms=processing_time_ms,
                success=False
            )

    def get_status(self) -> Dict[str, Any]:
        """
        Get current worker status.
        
        Returns:
            Dictionary with worker status information
        """
        return {
            "is_running": self.is_running,
            "processing_tasks": len(self.processing_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "chunk_timeout": self.chunk_timeout,
            "vad_service_info": {
                "type": type(self.vad_service).__name__,
                "initialized": hasattr(self.vad_service, '_initialized') and self.vad_service._initialized
            }
        }