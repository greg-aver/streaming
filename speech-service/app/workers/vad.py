"""
Voice Activity Detection (VAD) worker implementation.

This module provides VAD worker that processes audio chunks and publishes results,
following Clean Architecture principles with dependency injection.
"""

import asyncio
import time
from typing import Dict, Any, Optional
import structlog
from dependency_injector.wiring import Provide, inject

from ..interfaces.services import IVADService, IWorker, WorkerError
from ..interfaces.events import IEventBus, IEventSubscriber, Event
from ..models.audio import AudioChunkModel, ProcessingResultModel
from ..events import EventPublisherMixin, EventSubscriberMixin
from ..container import Container
from ..config import ProcessingSettings


class VADWorker(IWorker, EventSubscriberMixin, EventPublisherMixin):
    """
    VAD Worker implementation.
    
    Subscribes to audio_chunk_received events, processes audio through VAD service,
    and publishes vad_completed and speech_detected events.
    """
    
    @inject
    def __init__(
        self,
        event_bus: IEventBus = Provide[Container.event_bus],
        vad_service: IVADService = Provide[Container.vad_service],
        config: ProcessingSettings = Provide[Container.config.provided.processing]
    ):
        """
        Initialize the VAD worker.
        
        Args:
            event_bus: Event bus for publishing/subscribing
            vad_service: VAD service for speech detection
            config: Processing configuration settings
        """
        # Initialize mixins
        EventSubscriberMixin.__init__(self, event_bus)
        EventPublisherMixin.__init__(self, event_bus, "vad_worker")
        
        self.vad_service = vad_service
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Worker state
        self.is_running = False
        self.processing_tasks = set()
        self.max_concurrent_tasks = config.max_concurrent_workers
        self.chunk_timeout = config.chunk_timeout_seconds
        
        self.logger.info(
            "VAD worker initialized",
            max_concurrent_tasks=self.max_concurrent_tasks,
            chunk_timeout=self.chunk_timeout
        )
    
    async def start(self) -> None:
        """
        Start the worker and set up event subscriptions.
        
        Raises:
            WorkerError: If worker startup fails
        """
        try:
            self.logger.info("Starting VAD worker")
            
            # Initialize VAD service
            await self.vad_service.initialize()
            
            # Set up event subscriptions
            await self.subscribe_to_event("audio_chunk_received", self._handle_audio_chunk)
            
            self.is_running = True
            
            self.logger.info("VAD worker started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start VAD worker", error=str(e))
            raise WorkerError(f"VAD worker startup failed: {e}")
    
    async def stop(self) -> None:
        """
        Stop the worker and clean up resources.
        
        Raises:
            WorkerError: If worker shutdown fails
        """
        self.logger.info("Stopping VAD worker")
        
        # Stop accepting new tasks
        self.is_running = False
        
        cleanup_errors = []
        
        # Wait for processing tasks to complete
        try:
            if self.processing_tasks:
                self.logger.info(
                    "Waiting for processing tasks to complete",
                    task_count=len(self.processing_tasks)
                )
                # Give tasks time to complete, but don't wait forever
                done, pending = await asyncio.wait(
                    self.processing_tasks, 
                    timeout=self.chunk_timeout * 2,
                    return_when=asyncio.ALL_COMPLETED
                )
                
                # Cancel any remaining tasks
                if pending:
                    self.logger.warning(
                        "Cancelling pending tasks during shutdown",
                        pending_count=len(pending)
                    )
                    for task in pending:
                        task.cancel()
                    
                    # Wait a bit for cancellation to complete
                    await asyncio.gather(*pending, return_exceptions=True)
                
        except Exception as e:
            cleanup_errors.append(f"Task cleanup failed: {e}")
            self.logger.error("Error waiting for tasks to complete", error=str(e))
        
        # Clean up event subscriptions (independent of task cleanup)
        try:
            await self.cleanup_subscriptions()
        except Exception as e:
            cleanup_errors.append(f"Subscription cleanup failed: {e}")
            self.logger.error("Error cleaning up subscriptions", error=str(e))
        
        # Clean up VAD service (independent of other cleanup)
        try:
            await self.vad_service.cleanup()
        except Exception as e:
            cleanup_errors.append(f"VAD service cleanup failed: {e}")
            self.logger.error("Error cleaning up VAD service", error=str(e))
        
        # Report results
        if cleanup_errors:
            error_msg = f"VAD worker shutdown completed with errors: {'; '.join(cleanup_errors)}"
            self.logger.warning("VAD worker stopped with cleanup errors", errors=cleanup_errors)
            raise WorkerError(error_msg)
        else:
            self.logger.info("VAD worker stopped successfully")
    
    async def process_chunk(self, chunk: AudioChunkModel) -> ProcessingResultModel:
        """
        Process an audio chunk and return the result.
        
        Args:
            chunk: Audio chunk to process
            
        Returns:
            Processing result with VAD data
            
        Raises:
            WorkerError: If processing fails
        """
        if not self.is_running:
            raise WorkerError("VAD worker is not running")
        
        start_time = time.time()
        
        try:
            # Run VAD detection
            vad_result = await self.vad_service.detect_speech(
                chunk.data,
                chunk.sample_rate
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Create processing result
            result = ProcessingResultModel(
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                component="vad",
                result=vad_result,
                processing_time_ms=processing_time_ms,
                success=True
            )
            
            self.logger.debug(
                "VAD processing completed",
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                is_speech=vad_result["is_speech"],
                confidence=vad_result["confidence"],
                processing_time_ms=processing_time_ms
            )
            
            return result
            
        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            
            self.logger.error(
                "VAD processing failed",
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                error=str(e),
                processing_time_ms=processing_time_ms
            )
            
            # Create error result
            result = ProcessingResultModel(
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                component="vad",
                result={
                    "is_speech": False,
                    "confidence": 0.0,
                    "error": str(e)
                },
                processing_time_ms=processing_time_ms,
                success=False,
                error=str(e)
            )
            
            return result
    
    async def _handle_audio_chunk(self, event: Event) -> None:
        """
        Handle audio_chunk_received event.
        
        Args:
            event: Event containing audio chunk data
        """
        try:
            # Check if we're at max concurrent tasks
            if len(self.processing_tasks) >= self.max_concurrent_tasks:
                self.logger.warning(
                    "Max concurrent tasks reached, dropping audio chunk",
                    current_tasks=len(self.processing_tasks),
                    max_tasks=self.max_concurrent_tasks
                )
                return
            
            # Extract audio chunk data from event
            event_data = event.data
            
            # Create audio chunk model
            chunk = AudioChunkModel(
                session_id=event_data["session_id"],
                chunk_id=event_data["chunk_id"],
                data=event_data["data"]
            )
            
            # Process chunk asynchronously
            task = asyncio.create_task(
                self._process_chunk_with_cleanup(chunk, event.correlation_id)
            )
            self.processing_tasks.add(task)
            
        except Exception as e:
            self.logger.error(
                "Error handling audio chunk event",
                error=str(e),
                correlation_id=event.correlation_id
            )
    
    async def _process_chunk_with_cleanup(
        self, 
        chunk: AudioChunkModel, 
        correlation_id: Optional[str]
    ) -> None:
        """
        Process chunk with automatic task cleanup.
        
        Args:
            chunk: Audio chunk to process
            correlation_id: Event correlation ID
        """
        current_task = asyncio.current_task()
        
        try:
            # Process the chunk with timeout
            result = await asyncio.wait_for(
                self.process_chunk(chunk),
                timeout=self.chunk_timeout
            )
            
            # Publish vad_completed event
            await self.publish_event(
                "vad_completed",
                {
                    "session_id": result.session_id,
                    "chunk_id": result.chunk_id,
                    "component": result.component,
                    "result": result.result,
                    "processing_time_ms": result.processing_time_ms,
                    "success": result.success
                },
                correlation_id
            )
            
            # If speech detected, also publish speech_detected event
            if result.success and result.result.get("is_speech", False):
                await self.publish_event(
                    "speech_detected",
                    {
                        "session_id": result.session_id,
                        "chunk_id": result.chunk_id,
                        "data": chunk.data,
                        "sample_rate": chunk.sample_rate,
                        "vad_confidence": result.result.get("confidence", 0.0)
                    },
                    correlation_id
                )
                
                self.logger.debug(
                    "Speech detected, published speech_detected event",
                    session_id=result.session_id,
                    chunk_id=result.chunk_id,
                    confidence=result.result.get("confidence", 0.0)
                )
            
        except asyncio.TimeoutError:
            self.logger.error(
                "VAD processing timeout",
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                timeout=self.chunk_timeout
            )
            
            # Publish timeout error event
            await self.publish_event(
                "vad_completed",
                {
                    "session_id": chunk.session_id,
                    "chunk_id": chunk.chunk_id,
                    "component": "vad",
                    "result": {
                        "is_speech": False,
                        "confidence": 0.0,
                        "error": "Processing timeout"
                    },
                    "processing_time_ms": self.chunk_timeout * 1000,
                    "success": False,
                    "error": "Processing timeout"
                },
                correlation_id
            )
            
        except Exception as e:
            self.logger.error(
                "Unexpected error in VAD processing",
                session_id=chunk.session_id,
                chunk_id=chunk.chunk_id,
                error=str(e)
            )
            
        finally:
            # Clean up task from tracking set
            if current_task and current_task in self.processing_tasks:
                self.processing_tasks.discard(current_task)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current worker status.
        
        Returns:
            Status information dictionary
        """
        return {
            "is_running": self.is_running,
            "processing_tasks": len(self.processing_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "chunk_timeout": self.chunk_timeout,
            "vad_service_info": (
                self.vad_service.get_model_info() 
                if hasattr(self.vad_service, 'get_model_info') 
                else {"type": type(self.vad_service).__name__}
            )
        }