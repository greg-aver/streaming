"""
Speaker Diarization worker implementation.

This module provides Diarization worker that processes speech audio and publishes speaker identification results,
following Clean Architecture principles with dependency injection.
"""

import asyncio
import time
from typing import Dict, Any, Optional
import structlog
from dependency_injector.wiring import Provide, inject

from ..interfaces.services import IDiarizationService, IWorker, WorkerError
from ..interfaces.events import IEventBus, IEventSubscriber, Event
from ..models.audio import ProcessingResultModel
from ..events import EventPublisherMixin, EventSubscriberMixin
from ..container import Container
from ..config import ProcessingSettings


class DiarizationWorker(IWorker, EventSubscriberMixin, EventPublisherMixin):
    """
    Diarization Worker implementation.
    
    Subscribes to speech_detected events, processes audio through Diarization service,
    and publishes diarization_completed events with speaker identification results.
    """
    
    @inject
    def __init__(
        self,
        event_bus: IEventBus = Provide[Container.event_bus],
        diarization_service: IDiarizationService = Provide[Container.diarization_service],
        config: ProcessingSettings = Provide[Container.config.provided.processing]
    ):
        """
        Initialize the Diarization worker.
        
        Args:
            event_bus: Event bus for publishing/subscribing
            diarization_service: Diarization service for speaker identification
            config: Processing configuration settings
        """
        # Initialize mixins
        EventSubscriberMixin.__init__(self, event_bus)
        EventPublisherMixin.__init__(self, event_bus, "diarization_worker")
        
        self.diarization_service = diarization_service
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Worker state
        self.is_running = False
        self.processing_tasks: set = set()
        self.max_concurrent_tasks = config.max_concurrent_workers
        self.chunk_timeout = config.chunk_timeout_seconds
    
    async def start(self) -> None:
        """Start the diarization worker."""
        if self.is_running:
            return
        
        self.logger.info("Starting Diarization worker")
        
        # Subscribe to speech_detected events
        await self.subscribe_to_event("speech_detected", self._handle_speech_detected)
        
        self.is_running = True
        self.logger.info("Diarization worker started successfully")
    
    async def stop(self) -> None:
        """Stop the diarization worker."""
        if not self.is_running:
            return
        
        self.logger.info("Stopping Diarization worker")
        
        # Wait for all processing tasks to complete
        if self.processing_tasks:
            self.logger.info("Waiting for processing tasks to complete", 
                           tasks=len(self.processing_tasks))
            await asyncio.gather(*self.processing_tasks, return_exceptions=True)
        
        # Unsubscribe from events
        await self.unsubscribe_from_event("speech_detected")
        
        self.is_running = False
        self.logger.info("Diarization worker stopped successfully")
    
    async def _handle_speech_detected(self, event: Event) -> None:
        """
        Handle speech_detected events.
        
        Args:
            event: Speech detected event with audio data
        """
        # Check concurrent task limit
        if len(self.processing_tasks) >= self.max_concurrent_tasks:
            self.logger.warning(
                "Dropping diarization task due to concurrency limit",
                max_tasks=self.max_concurrent_tasks,
                current_tasks=len(self.processing_tasks)
            )
            return
        
        # Create processing task
        task = asyncio.create_task(
            self._process_speech_with_timeout(event),
            name=f"diarization_{event.data.get('session_id')}_{event.data.get('chunk_id')}"
        )
        
        self.processing_tasks.add(task)
        
        # Remove task when done
        def remove_task(task):
            self.processing_tasks.discard(task)
        
        task.add_done_callback(remove_task)
    
    async def _process_speech_with_timeout(self, event: Event) -> None:
        """
        Process speech with timeout.
        
        Args:
            event: Speech detected event
        """
        try:
            # Process with timeout
            await asyncio.wait_for(
                self._process_speech(event),
                timeout=self.chunk_timeout
            )
        except asyncio.TimeoutError:
            # Handle timeout
            error_result = ProcessingResultModel(
                session_id=event.data.get("session_id", "unknown"),
                chunk_id=event.data.get("chunk_id", 0),
                component="diarization",
                success=False,
                result={
                    "speakers": [],
                    "segments": [],
                    "error": f"Diarization timeout after {self.chunk_timeout}s"
                },
                processing_time_ms=int(self.chunk_timeout * 1000),
                error=f"Diarization timeout after {self.chunk_timeout}s"
            )
            
            # Publish error result
            await self.publish_event("diarization_completed", {
                "session_id": error_result.session_id,
                "chunk_id": error_result.chunk_id,
                "component": error_result.component,
                "success": error_result.success,
                "result": error_result.result,
                "processing_time_ms": error_result.processing_time_ms,
                "error": f"Diarization timeout after {self.chunk_timeout}s"
            }, correlation_id=event.correlation_id)
            
            self.logger.error(
                "Diarization processing timeout",
                session_id=error_result.session_id,
                chunk_id=error_result.chunk_id,
                timeout_seconds=self.chunk_timeout
            )
    
    async def _process_speech(self, event: Event) -> None:
        """
        Process speech audio for speaker diarization.
        
        Args:
            event: Speech detected event with audio data
        """
        session_id = event.data.get("session_id", "unknown")
        chunk_id = event.data.get("chunk_id", 0)
        audio_data = event.data.get("data", b"")
        sample_rate = event.data.get("sample_rate", 16000)
        
        self.logger.info(
            "Processing speech for diarization",
            session_id=session_id,
            chunk_id=chunk_id,
            audio_size=len(audio_data)
        )
        
        try:
            # Process chunk
            result = await self.process_chunk(
                audio_data=audio_data,
                sample_rate=sample_rate,
                session_id=session_id,
                chunk_id=chunk_id
            )
            
            # Publish result
            await self.publish_event("diarization_completed", {
                "session_id": result.session_id,
                "chunk_id": result.chunk_id,
                "component": result.component,
                "success": result.success,
                "result": result.result,
                "processing_time_ms": result.processing_time_ms
            }, correlation_id=event.correlation_id)
            
            self.logger.info(
                "Diarization processing completed",
                session_id=session_id,
                chunk_id=chunk_id,
                success=result.success,
                processing_time_ms=result.processing_time_ms
            )
        
        except Exception as e:
            # Handle processing error
            error_result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                success=False,
                result={
                    "speakers": [],
                    "segments": [],
                    "error": str(e)
                },
                processing_time_ms=0,
                error=str(e)
            )
            
            # Publish error
            await self.publish_event("diarization_completed", {
                "session_id": error_result.session_id,
                "chunk_id": error_result.chunk_id,
                "component": error_result.component,
                "success": error_result.success,
                "result": error_result.result,
                "processing_time_ms": error_result.processing_time_ms
            }, correlation_id=event.correlation_id)
            
            self.logger.error(
                "Diarization processing error",
                session_id=session_id,
                chunk_id=chunk_id,
                error=str(e)
            )
    
    async def process_chunk(
        self,
        audio_data: bytes,
        sample_rate: int,
        session_id: str,
        chunk_id: int
    ) -> ProcessingResultModel:
        """
        Process a single audio chunk for speaker diarization.
        
        Args:
            audio_data: Raw audio data
            sample_rate: Audio sample rate
            session_id: Session identifier
            chunk_id: Chunk identifier
            
        Returns:
            ProcessingResultModel with diarization results
            
        Raises:
            WorkerError: If worker is not running
        """
        if not self.is_running:
            raise WorkerError("Diarization worker is not running")
        
        start_time = time.time()
        
        try:
            # Process with diarization service
            diarization_result = await self.diarization_service.diarize(
                audio_data=audio_data,
                sample_rate=sample_rate
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Create result
            result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                success=True,
                result=diarization_result,
                processing_time_ms=processing_time
            )
            
            self.logger.debug(
                "Chunk processing completed",
                session_id=session_id,
                chunk_id=chunk_id,
                speakers_found=len(diarization_result.get("speakers", [])),
                processing_time_ms=processing_time
            )
            
            return result
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            
            result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="diarization",
                success=False,
                result={
                    "speakers": [],
                    "segments": [],
                    "error": str(e)
                },
                processing_time_ms=processing_time,
                error=str(e)
            )
            
            self.logger.error(
                "Chunk processing failed",
                session_id=session_id,
                chunk_id=chunk_id,
                error=str(e),
                processing_time_ms=processing_time
            )
            
            return result
    
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