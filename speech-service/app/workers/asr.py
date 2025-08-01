"""
Automatic Speech Recognition (ASR) worker implementation.

This module provides ASR worker that processes speech audio and publishes transcription results,
following Clean Architecture principles with dependency injection.
"""

import asyncio
import time
from typing import Dict, Any, Optional
import structlog
from dependency_injector.wiring import Provide, inject

from ..interfaces.services import IASRService, IWorker, WorkerError
from ..interfaces.events import IEventBus, IEventSubscriber, Event
from ..models.audio import ProcessingResultModel
from ..events import EventPublisherMixin, EventSubscriberMixin
from ..container import Container
from ..config import ProcessingSettings


class ASRWorker(IWorker, EventSubscriberMixin, EventPublisherMixin):
    """
    ASR Worker implementation.
    
    Subscribes to speech_detected events, processes audio through ASR service,
    and publishes asr_completed events with transcription results.
    """
    
    @inject
    def __init__(
        self,
        event_bus: IEventBus = Provide[Container.event_bus],
        asr_service: IASRService = Provide[Container.asr_service],
        config: ProcessingSettings = Provide[Container.config.provided.processing]
    ):
        """
        Initialize the ASR worker.
        
        Args:
            event_bus: Event bus for publishing/subscribing
            asr_service: ASR service for speech transcription
            config: Processing configuration settings
        """
        # Initialize mixins
        EventSubscriberMixin.__init__(self, event_bus)
        EventPublisherMixin.__init__(self, event_bus, "asr_worker")
        
        self.asr_service = asr_service
        self.config = config
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Worker state
        self.is_running = False
        self.processing_tasks = set()
        self.max_concurrent_tasks = config.max_concurrent_workers
        self.chunk_timeout = config.chunk_timeout_seconds
        
        self.logger.info(
            "ASR worker initialized",
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
            self.logger.info("Starting ASR worker")
            
            # Initialize ASR service
            await self.asr_service.initialize()
            
            # Set up event subscriptions
            await self.subscribe_to_event("speech_detected", self._handle_speech_detected)
            
            self.is_running = True
            
            self.logger.info("ASR worker started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start ASR worker", error=str(e))
            raise WorkerError(f"ASR worker startup failed: {e}")
    
    async def stop(self) -> None:
        """
        Stop the worker and clean up resources.
        
        Raises:
            WorkerError: If worker shutdown fails
        """
        try:
            self.logger.info("Stopping ASR worker")
            
            self.is_running = False
            
            # Wait for processing tasks to complete
            if self.processing_tasks:
                self.logger.info(
                    "Waiting for processing tasks to complete",
                    task_count=len(self.processing_tasks)
                )
                await asyncio.gather(*self.processing_tasks, return_exceptions=True)
            
            # Clean up event subscriptions
            await self.cleanup_subscriptions()
            
            # Clean up ASR service
            await self.asr_service.cleanup()
            
            self.logger.info("ASR worker stopped successfully")
            
        except Exception as e:
            self.logger.error("Error during ASR worker shutdown", error=str(e))
            raise WorkerError(f"ASR worker shutdown failed: {e}")
    
    async def process_chunk(self, audio_data: bytes, sample_rate: int, session_id: str, chunk_id: int) -> ProcessingResultModel:
        """
        Process speech audio and return transcription result.
        
        Args:
            audio_data: Raw audio bytes containing speech
            sample_rate: Audio sample rate
            session_id: Session identifier
            chunk_id: Chunk identifier
            
        Returns:
            Processing result with transcription data
            
        Raises:
            WorkerError: If processing fails
        """
        if not self.is_running:
            raise WorkerError("ASR worker is not running")
        
        start_time = time.time()
        
        try:
            # Run ASR transcription
            asr_result = await self.asr_service.transcribe(
                audio_data,
                sample_rate
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Create processing result
            result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="asr",
                result=asr_result,
                processing_time_ms=processing_time_ms,
                success=True
            )
            
            self.logger.debug(
                "ASR processing completed",
                session_id=session_id,
                chunk_id=chunk_id,
                text_length=len(asr_result.get("text", "")),
                confidence=asr_result.get("confidence", 0.0),
                language=asr_result.get("language", "unknown"),
                processing_time_ms=processing_time_ms
            )
            
            return result
            
        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            
            self.logger.error(
                "ASR processing failed",
                session_id=session_id,
                chunk_id=chunk_id,
                error=str(e),
                processing_time_ms=processing_time_ms
            )
            
            # Create error result
            result = ProcessingResultModel(
                session_id=session_id,
                chunk_id=chunk_id,
                component="asr",
                result={
                    "text": "",
                    "confidence": 0.0,
                    "segments": [],
                    "language": "unknown",
                    "error": str(e)
                },
                processing_time_ms=processing_time_ms,
                success=False,
                error=str(e)
            )
            
            return result
    
    async def _handle_speech_detected(self, event: Event) -> None:
        """
        Handle speech_detected event.
        
        Args:
            event: Event containing speech audio data
        """
        try:
            # Check if we're at max concurrent tasks
            if len(self.processing_tasks) >= self.max_concurrent_tasks:
                self.logger.warning(
                    "Max concurrent tasks reached, dropping speech chunk",
                    current_tasks=len(self.processing_tasks),
                    max_tasks=self.max_concurrent_tasks
                )
                return
            
            # Extract speech data from event
            event_data = event.data
            
            session_id = event_data["session_id"]
            chunk_id = event_data["chunk_id"]
            audio_data = event_data["data"]
            sample_rate = event_data.get("sample_rate", 16000)
            vad_confidence = event_data.get("vad_confidence", 0.0)
            
            self.logger.debug(
                "Processing speech detected event",
                session_id=session_id,
                chunk_id=chunk_id,
                audio_size=len(audio_data),
                sample_rate=sample_rate,
                vad_confidence=vad_confidence
            )
            
            # Process speech asynchronously
            task = asyncio.create_task(
                self._process_speech_with_cleanup(
                    audio_data, sample_rate, session_id, chunk_id, event.correlation_id
                )
            )
            self.processing_tasks.add(task)
            
        except Exception as e:
            self.logger.error(
                "Error handling speech detected event",
                error=str(e),
                correlation_id=event.correlation_id
            )
    
    async def _process_speech_with_cleanup(
        self, 
        audio_data: bytes,
        sample_rate: int,
        session_id: str,
        chunk_id: int,
        correlation_id: Optional[str]
    ) -> None:
        """
        Process speech with automatic task cleanup.
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
            session_id: Session identifier
            chunk_id: Chunk identifier
            correlation_id: Event correlation ID
        """
        current_task = asyncio.current_task()
        
        try:
            # Process the speech with timeout
            result = await asyncio.wait_for(
                self.process_chunk(audio_data, sample_rate, session_id, chunk_id),
                timeout=self.chunk_timeout
            )
            
            # Publish asr_completed event
            await self.publish_event(
                "asr_completed",
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
            
            # Log transcription result
            if result.success:
                transcribed_text = result.result.get("text", "")
                if transcribed_text:
                    self.logger.info(
                        "Speech transcribed successfully",
                        session_id=session_id,
                        chunk_id=chunk_id,
                        text=transcribed_text[:100] + "..." if len(transcribed_text) > 100 else transcribed_text,
                        confidence=result.result.get("confidence", 0.0),
                        language=result.result.get("language", "unknown")
                    )
                else:
                    self.logger.debug(
                        "No transcription result (empty text)",
                        session_id=session_id,
                        chunk_id=chunk_id
                    )
            
        except asyncio.TimeoutError:
            self.logger.error(
                "ASR processing timeout",
                session_id=session_id,
                chunk_id=chunk_id,
                timeout=self.chunk_timeout
            )
            
            # Publish timeout error event
            await self.publish_event(
                "asr_completed",
                {
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "component": "asr",
                    "result": {
                        "text": "",
                        "confidence": 0.0,
                        "segments": [],
                        "language": "unknown",
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
                "Unexpected error in ASR processing",
                session_id=session_id,
                chunk_id=chunk_id,
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
            "asr_service_info": (
                self.asr_service.get_model_info() 
                if hasattr(self.asr_service, 'get_model_info') 
                else {"type": type(self.asr_service).__name__}
            )
        }