"""
Speaker Diarization worker implementation with Clean DI.

Senior approach: Direct dependency injection without mixins for better testability
and cleaner architecture. This module provides Diarization worker that processes speech audio 
and publishes speaker identification results.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Set
import structlog

from ..interfaces.services import IDiarizationService, IWorker, WorkerError
from ..interfaces.events import IEventBus, Event
from ..models.audio import ProcessingResultModel
from ..config import ProcessingSettings


class DiarizationWorker(IWorker):
    """
    Diarization Worker implementation with Clean DI approach.
    
    Senior pattern: Direct dependency injection без mixins для лучшей testability.
    Subscribes to speech_detected events, processes audio through Diarization service,
    and publishes diarization_completed events with speaker identification results.
    """
    
    def __init__(
        self, 
        diarization_service: IDiarizationService, 
        config: ProcessingSettings
    ):
        """
        Initialize the Diarization worker with dependency injection.
        
        Senior approach: Получаем зависимости через конструктор, event_bus через setter
        
        Args:
            diarization_service: Diarization service for speaker identification
            config: Processing configuration settings
        """
        self.diarization_service = diarization_service
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
            "Diarization worker initialized",
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
            self.logger.info("Starting Diarization worker")
            
            # Phase 1: Initialize diarization service
            await self.diarization_service.initialize()
            self.logger.info("Diarization service initialized")
            
            # Phase 2: Set up event subscriptions
            await self.event_bus.subscribe("speech_detected", self._handle_speech_detected)
            self.logger.info("Subscribed to speech_detected events")
            
            # Phase 3: Mark as running
            self.is_running = True
            self.logger.info("Diarization worker started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start Diarization worker", error=str(e), exc_info=True)
            await self._cleanup_on_error()
            raise WorkerError(f"Diarization worker startup failed: {e}")
    
    async def stop(self) -> None:
        """
        Stop the worker and clean up resources.
        
        Senior approach: Graceful shutdown with proper resource cleanup
        """
        self.logger.info("Stopping Diarization worker")
        
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
            await self.event_bus.unsubscribe("speech_detected", self._handle_speech_detected)
            self.logger.info("Unsubscribed from events")
        except Exception as e:
            self.logger.warning("Error unsubscribing from events", error=str(e))
        
        # Phase 4: Cleanup service
        try:
            await self.diarization_service.cleanup()
            self.logger.info("Diarization service cleaned up")
        except Exception as e:
            self.logger.warning("Error cleaning up Diarization service", error=str(e))
        
        self.logger.info("Diarization worker stopped successfully")
    
    async def _handle_speech_detected(self, event: Event) -> None:
        """
        Handle incoming speech detected events.
        
        Senior approach: Proper concurrency control and error handling
        """
        if not self.is_running:
            self.logger.debug("Ignoring event - worker not running")
            return
        
        # Check concurrency limits
        if len(self.processing_tasks) >= self.max_concurrent_tasks:
            self.logger.warning(
                "Max concurrent tasks reached, dropping speech chunk",
                active_tasks=len(self.processing_tasks),
                max_tasks=self.max_concurrent_tasks
            )
            return
        
        # Create processing task
        task = asyncio.create_task(self._process_speech_chunk(event))
        self.processing_tasks.add(task)
        
        # Clean up completed tasks
        task.add_done_callback(self.processing_tasks.discard)
    
    async def _process_speech_chunk(self, event: Event) -> None:
        """
        Process individual speech chunk.
        
        Senior approach: Comprehensive error handling and performance tracking
        """
        start_time = time.time()
        chunk_data = event.data
        
        try:
            # Extract audio data from the event (following VAD/ASR format)
            audio_data = chunk_data.get("data")  # Primary format from speech_detected
            sample_rate = chunk_data.get("sample_rate", 16000)
            
            if not audio_data:
                # Fallback: try to get from result (new format)
                result_data = chunk_data.get("result", {})
                audio_data = result_data.get("audio_data")
                sample_rate = result_data.get("sample_rate", 16000)
            
            if not audio_data:
                raise ValueError("No audio data found in speech_detected event")
            
            session_id = chunk_data.get("session_id", "unknown")
            chunk_id = chunk_data.get("chunk_id", -1)
            
            self.logger.debug(
                "Processing speech chunk for diarization",
                session_id=session_id,
                chunk_id=chunk_id,
                data_size=len(audio_data) if isinstance(audio_data, (bytes, list)) else "unknown"
            )
            
            # Process through diarization service with timeout
            result = await asyncio.wait_for(
                self.diarization_service.diarize(audio_data, sample_rate),
                timeout=self.chunk_timeout
            )
            
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Create result model
            processing_result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                result=result if isinstance(result, dict) else result.model_dump(),
                processing_time_ms=processing_time,
                success=True
            )
            
            # Publish results
            result_event = Event(
                name="diarization_completed",
                data=processing_result.model_dump(),
                source="diarization_worker",
                correlation_id=event.correlation_id
            )
            await self.event_bus.publish(result_event)
            
            self.logger.debug(
                "Speech chunk processed successfully",
                session_id=session_id,
                chunk_id=chunk_id,
                processing_time_ms=processing_time,
                speakers_found=len(result.get("speakers", []))
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
            "Diarization processing failed",
            error=error_message,
            session_id=chunk_data.get("session_id"),
            chunk_id=chunk_data.get("chunk_id"),
            processing_time_ms=processing_time
        )
        
        # Create error result with required diarization fields
        error_result = ProcessingResultModel(
            session_id=chunk_data.get("session_id", "unknown"),
            chunk_id=chunk_data.get("chunk_id", -1),
            component="diarization",
            result={
                "speakers": [],
                "segments": [],
                "error": error_message
            },
            processing_time_ms=processing_time,
            success=False
        )
        
        # Publish error result
        try:
            error_event = Event(
                name="diarization_completed",
                data=error_result.model_dump(),
                source="diarization_worker",
                correlation_id=None  # No correlation_id available in error context
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
                await self._event_bus.unsubscribe("speech_detected", self._handle_speech_detected)
        except Exception:
            pass  # Ignore cleanup errors during error handling
    
    async def process_chunk(
        self,
        audio_data: bytes,
        sample_rate: int,
        session_id: str,
        chunk_id: int
    ) -> ProcessingResultModel:
        """
        Process speech audio and return diarization result.
        
        Senior approach: Compatibility method для интерфейса IWorker
        
        Args:
            audio_data: Raw audio bytes containing speech
            sample_rate: Audio sample rate
            session_id: Session identifier
            chunk_id: Chunk identifier
            
        Returns:
            Processing result with diarization data
            
        Raises:
            WorkerError: If processing fails
        """
        if not self.is_running:
            raise WorkerError("Diarization worker is not running")
        
        start_time = time.time()
        
        try:
            # Run diarization service
            result = await asyncio.wait_for(
                self.diarization_service.diarize(audio_data, sample_rate),
                timeout=self.chunk_timeout
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Create processing result
            processing_result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                result=result if isinstance(result, dict) else result.model_dump(),
                processing_time_ms=processing_time_ms,
                success=True
            )
            
            self.logger.debug(
                "Diarization processing completed",
                session_id=session_id,
                chunk_id=chunk_id,
                speakers_found=len(result.get("speakers", [])),
                processing_time_ms=processing_time_ms
            )
            
            return processing_result
            
        except asyncio.TimeoutError:
            processing_time_ms = (time.time() - start_time) * 1000
            await self._handle_processing_error(
                {"session_id": session_id, "chunk_id": chunk_id}, 
                "Processing timeout", 
                processing_time_ms
            )
            # Return error result
            return ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                result={
                    "speakers": [],
                    "segments": [],
                    "error": "Processing timeout"
                },
                processing_time_ms=processing_time_ms,
                success=False
            )
        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            await self._handle_processing_error(
                {"session_id": session_id, "chunk_id": chunk_id}, 
                str(e), 
                processing_time_ms
            )
            # Return error result
            return ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                result={
                    "speakers": [],
                    "segments": [],
                    "error": str(e)
                },
                processing_time_ms=processing_time_ms,
                success=False
            )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get worker status information.
        
        Returns:
            Dictionary with worker status
        """
        return {
            "is_running": self.is_running,
            "processing_tasks": len(self.processing_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "chunk_timeout": self.chunk_timeout,
            "diarization_service_info": {
                "type": type(self.diarization_service).__name__,
                "config": getattr(self.diarization_service, 'config', {})
            }
        }