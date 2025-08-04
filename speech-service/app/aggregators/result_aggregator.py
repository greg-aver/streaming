"""
Result Aggregator implementation.

This module provides Result Aggregator that collects processing results from
VAD, ASR, and Diarization workers and publishes unified chunk completion events.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
import structlog
from datetime import datetime, timedelta

from ..interfaces.events import IEventBus, Event
from ..events import EventPublisherMixin, EventSubscriberMixin
from ..models.audio import ProcessingResultModel


@dataclass
class ChunkAggregationState:
    """
    Tracks aggregation state for a single audio chunk.
    
    Collects results from VAD, ASR, and Diarization workers
    until all components complete or timeout occurs.
    """
    session_id: str
    chunk_id: int
    created_at: float
    timeout_seconds: float
    
    # Component results
    vad_result: Optional[Dict[str, Any]] = None
    asr_result: Optional[Dict[str, Any]] = None
    diarization_result: Optional[Dict[str, Any]] = None
    
    # Completion tracking
    completed_components: Set[str] = field(default_factory=set)
    expected_components: Set[str] = field(default_factory=lambda: {"vad", "asr", "diarization"})
    
    def add_result(self, component: str, result: Dict[str, Any]) -> None:
        """Add a component result and mark as completed."""
        if component == "vad":
            self.vad_result = result
        elif component == "asr":
            self.asr_result = result
        elif component == "diarization":
            self.diarization_result = result
        
        self.completed_components.add(component)
    
    def is_complete(self) -> bool:
        """Check if all expected components have completed."""
        return self.completed_components >= self.expected_components
    
    def is_expired(self) -> bool:
        """Check if aggregation has timed out."""
        return (time.time() - self.created_at) > self.timeout_seconds
    
    def get_completion_percentage(self) -> float:
        """Get percentage of components completed."""
        return len(self.completed_components) / len(self.expected_components) * 100
    
    def get_missing_components(self) -> Set[str]:
        """Get list of components that haven't completed yet."""
        return self.expected_components - self.completed_components


class ResultAggregator(EventSubscriberMixin, EventPublisherMixin):
    """
    Result Aggregator implementation.
    
    Subscribes to processing completion events from VAD, ASR, and Diarization workers,
    aggregates results per chunk, and publishes unified chunk completion events.
    """
    
    def __init__(
        self,
        event_bus: IEventBus,
        aggregation_timeout_seconds: float = 30.0,
        cleanup_interval_seconds: float = 60.0
    ):
        """
        Initialize Result Aggregator.
        
        Args:
            event_bus: Event bus for subscribing/publishing
            aggregation_timeout_seconds: Max time to wait for all components
            cleanup_interval_seconds: How often to clean up expired aggregations
        """
        # Initialize mixins
        EventSubscriberMixin.__init__(self, event_bus)
        EventPublisherMixin.__init__(self, event_bus, "result_aggregator")
        
        self.aggregation_timeout = aggregation_timeout_seconds
        self.cleanup_interval = cleanup_interval_seconds
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # State tracking
        self.is_running = False
        self.chunk_states: Dict[str, ChunkAggregationState] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "chunks_processed": 0,
            "chunks_completed": 0,
            "chunks_timed_out": 0,
            "chunks_partial": 0,
            "average_aggregation_time_ms": 0.0
        }
        
        self.logger.info(
            "Result Aggregator initialized",
            aggregation_timeout=aggregation_timeout_seconds,
            cleanup_interval=cleanup_interval_seconds
        )
    
    async def start(self) -> None:
        """Start the Result Aggregator and set up subscriptions."""
        if self.is_running:
            return
        
        self.logger.info("Starting Result Aggregator")
        
        # Subscribe to completion events from all workers
        await self.subscribe_to_event("vad_completed", self._handle_vad_completed)
        await self.subscribe_to_event("asr_completed", self._handle_asr_completed)
        await self.subscribe_to_event("diarization_completed", self._handle_diarization_completed)
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_chunks())
        
        self.is_running = True
        self.logger.info("Result Aggregator started successfully")
    
    async def stop(self) -> None:
        """Stop the Result Aggregator and clean up resources."""
        if not self.is_running:
            return
        
        self.logger.info("Stopping Result Aggregator")
        
        self.is_running = False
        
        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Process any remaining chunks as partial results
        await self._flush_remaining_chunks()
        
        # Clean up subscriptions
        await self.cleanup_subscriptions()
        
        self.logger.info("Result Aggregator stopped successfully")
    
    async def _handle_vad_completed(self, event: Event) -> None:
        """Handle VAD completion event."""
        await self._handle_component_completed("vad", event)
    
    async def _handle_asr_completed(self, event: Event) -> None:
        """Handle ASR completion event."""
        await self._handle_component_completed("asr", event)
    
    async def _handle_diarization_completed(self, event: Event) -> None:
        """Handle Diarization completion event."""
        await self._handle_component_completed("diarization", event)
    
    async def _handle_component_completed(self, component: str, event: Event) -> None:
        """
        Handle completion event from any component.
        
        Args:
            component: Name of the component (vad, asr, diarization)  
            event: Completion event from the component
        """
        try:
            data = event.data
            session_id = data.get("session_id")
            chunk_id = data.get("chunk_id")
            
            if not session_id or chunk_id is None:
                self.logger.warning(
                    "Invalid completion event data",
                    component=component,
                    event_data=data
                )
                return
            
            chunk_key = f"{session_id}_{chunk_id}"
            
            # Get or create chunk aggregation state
            if chunk_key not in self.chunk_states:
                self.chunk_states[chunk_key] = ChunkAggregationState(
                    session_id=session_id,
                    chunk_id=chunk_id,
                    created_at=time.time(),
                    timeout_seconds=self.aggregation_timeout
                )
                self.stats["chunks_processed"] += 1
            
            chunk_state = self.chunk_states[chunk_key]
            
            # Add component result
            chunk_state.add_result(component, data)
            
            self.logger.debug(
                "Component result received",
                component=component,
                session_id=session_id,
                chunk_id=chunk_id,
                completion_percentage=chunk_state.get_completion_percentage(),
                missing_components=list(chunk_state.get_missing_components())
            )
            
            # Check if chunk is complete
            if chunk_state.is_complete():
                await self._publish_chunk_complete(chunk_key, chunk_state)
            
        except Exception as e:
            self.logger.error(
                "Error handling component completion",
                component=component,
                error=str(e),
                correlation_id=event.correlation_id
            )
    
    async def _publish_chunk_complete(
        self,
        chunk_key: str,
        chunk_state: ChunkAggregationState,
        is_timeout: bool = False
    ) -> None:
        """
        Publish chunk completion event with aggregated results.
        
        Args:
            chunk_key: Unique chunk identifier  
            chunk_state: Aggregation state for the chunk
            is_timeout: Whether this is a timeout-triggered completion
        """
        aggregation_time_ms = (time.time() - chunk_state.created_at) * 1000
        
        # Create aggregated result
        aggregated_result = {
            "session_id": chunk_state.session_id,
            "chunk_id": chunk_state.chunk_id,
            "aggregation_time_ms": aggregation_time_ms,
            "completed_components": list(chunk_state.completed_components),
            "missing_components": list(chunk_state.get_missing_components()),
            "is_complete": chunk_state.is_complete(),
            "is_timeout": is_timeout,
            "results": {}
        }
        
        # Add available results
        if chunk_state.vad_result:
            aggregated_result["results"]["vad"] = chunk_state.vad_result
        if chunk_state.asr_result:
            aggregated_result["results"]["asr"] = chunk_state.asr_result
        if chunk_state.diarization_result:
            aggregated_result["results"]["diarization"] = chunk_state.diarization_result
        
        # Publish chunk_complete event
        await self.publish_event(
            "chunk_complete",
            aggregated_result,
            correlation_id=f"{chunk_state.session_id}_{chunk_state.chunk_id}"
        )
        
        # Update statistics
        if chunk_state.is_complete():
            self.stats["chunks_completed"] += 1
        elif is_timeout:
            self.stats["chunks_timed_out"] += 1
        else:
            self.stats["chunks_partial"] += 1
        
        # Update average aggregation time
        current_avg = self.stats["average_aggregation_time_ms"]
        total_processed = self.stats["chunks_processed"]
        self.stats["average_aggregation_time_ms"] = (
            (current_avg * (total_processed - 1) + aggregation_time_ms) / total_processed
        )
        
        self.logger.info(
            "Chunk aggregation completed",
            session_id=chunk_state.session_id,
            chunk_id=chunk_state.chunk_id,
            aggregation_time_ms=aggregation_time_ms,
            completed_components=list(chunk_state.completed_components),
            missing_components=list(chunk_state.get_missing_components()),
            is_complete=chunk_state.is_complete(),
            is_timeout=is_timeout
        )
        
        # Clean up chunk state
        del self.chunk_states[chunk_key]
    
    async def _cleanup_expired_chunks(self) -> None:
        """Periodic cleanup task for expired chunk aggregations."""
        while self.is_running:
            try:
                expired_chunks = []
                current_time = time.time()
                
                for chunk_key, chunk_state in self.chunk_states.items():
                    if chunk_state.is_expired():
                        expired_chunks.append((chunk_key, chunk_state))
                
                # Process expired chunks
                for chunk_key, chunk_state in expired_chunks:
                    self.logger.warning(
                        "Chunk aggregation timed out",
                        session_id=chunk_state.session_id,
                        chunk_id=chunk_state.chunk_id,
                        completed_components=list(chunk_state.completed_components),
                        missing_components=list(chunk_state.get_missing_components()),
                        timeout_seconds=self.aggregation_timeout
                    )
                    
                    await self._publish_chunk_complete(chunk_key, chunk_state, is_timeout=True)
                
                # Wait for next cleanup cycle
                await asyncio.sleep(self.cleanup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in cleanup task", error=str(e))
                await asyncio.sleep(1)  # Brief pause on error
    
    async def _flush_remaining_chunks(self) -> None:
        """Flush all remaining chunks as partial results during shutdown."""
        remaining_chunks = list(self.chunk_states.items())
        
        for chunk_key, chunk_state in remaining_chunks:
            self.logger.info(
                "Flushing remaining chunk during shutdown",
                session_id=chunk_state.session_id,
                chunk_id=chunk_state.chunk_id,
                completed_components=list(chunk_state.completed_components)
            )
            
            await self._publish_chunk_complete(chunk_key, chunk_state, is_timeout=False)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get aggregator statistics.
        
        Returns:
            Dictionary with aggregation metrics
        """
        return {
            **self.stats,
            "active_chunks": len(self.chunk_states),
            "is_running": self.is_running,
            "aggregation_timeout_seconds": self.aggregation_timeout,
            "cleanup_interval_seconds": self.cleanup_interval
        }
    
    def get_active_chunks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about currently active chunk aggregations.
        
        Returns:
            Dictionary mapping chunk keys to their state info
        """
        return {
            chunk_key: {
                "session_id": state.session_id,
                "chunk_id": state.chunk_id,
                "age_seconds": time.time() - state.created_at,
                "completion_percentage": state.get_completion_percentage(),
                "completed_components": list(state.completed_components),
                "missing_components": list(state.get_missing_components()),
                "is_expired": state.is_expired()
            }
            for chunk_key, state in self.chunk_states.items()
        }