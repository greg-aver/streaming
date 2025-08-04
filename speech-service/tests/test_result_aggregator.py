"""
Tests for Result Aggregator implementation.

Tests Result Aggregator functionality:
- Event subscription and aggregation
- Chunk completion detection  
- Timeout handling
- Statistics tracking
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.aggregators.result_aggregator import ResultAggregator, ChunkAggregationState
from app.events import AsyncEventBus
from app.interfaces.events import Event


class TestChunkAggregationState:
    """Test cases for ChunkAggregationState."""
    
    def test_chunk_aggregation_state_initialization(self):
        """Test ChunkAggregationState initialization."""
        state = ChunkAggregationState(
            session_id="test_session",
            chunk_id=1,
            created_at=1000.0,
            timeout_seconds=30.0
        )
        
        assert state.session_id == "test_session"
        assert state.chunk_id == 1
        assert state.created_at == 1000.0
        assert state.timeout_seconds == 30.0
        assert state.vad_result is None
        assert state.asr_result is None
        assert state.diarization_result is None
        assert len(state.completed_components) == 0
        assert state.expected_components == {"vad", "asr", "diarization"}
    
    def test_add_result(self):
        """Test adding component results."""
        state = ChunkAggregationState("session", 1, 1000.0, 30.0)
        
        # Add VAD result
        vad_data = {"is_speech": True, "confidence": 0.9}
        state.add_result("vad", vad_data)
        
        assert state.vad_result == vad_data
        assert "vad" in state.completed_components
        assert not state.is_complete()
        
        # Add ASR result
        asr_data = {"text": "hello", "confidence": 0.8}
        state.add_result("asr", asr_data)
        
        assert state.asr_result == asr_data
        assert "asr" in state.completed_components
        assert not state.is_complete()
        
        # Add Diarization result
        diar_data = {"speakers": ["SPEAKER_00"], "segments": []}
        state.add_result("diarization", diar_data)
        
        assert state.diarization_result == diar_data
        assert "diarization" in state.completed_components
        assert state.is_complete()
    
    def test_completion_percentage(self):
        """Test completion percentage calculation."""
        state = ChunkAggregationState("session", 1, 1000.0, 30.0)
        
        assert state.get_completion_percentage() == 0.0
        
        state.add_result("vad", {"is_speech": True})
        assert state.get_completion_percentage() == pytest.approx(33.33, rel=1e-2)
        
        state.add_result("asr", {"text": "hello"})
        assert state.get_completion_percentage() == pytest.approx(66.67, rel=1e-2)
        
        state.add_result("diarization", {"speakers": []})
        assert state.get_completion_percentage() == 100.0
    
    def test_missing_components(self):
        """Test missing components tracking."""
        state = ChunkAggregationState("session", 1, 1000.0, 30.0)
        
        assert state.get_missing_components() == {"vad", "asr", "diarization"}
        
        state.add_result("vad", {"is_speech": True})
        assert state.get_missing_components() == {"asr", "diarization"}
        
        state.add_result("asr", {"text": "hello"})
        assert state.get_missing_components() == {"diarization"}
        
        state.add_result("diarization", {"speakers": []})
        assert state.get_missing_components() == set()


class TestResultAggregator:
    """Test cases for ResultAggregator."""
    
    @pytest.fixture
    def event_bus(self):
        """Create AsyncEventBus instance."""
        return AsyncEventBus()
    
    @pytest.fixture
    def result_aggregator(self, event_bus):
        """Create ResultAggregator instance."""
        return ResultAggregator(
            event_bus=event_bus,
            aggregation_timeout_seconds=1.0,  # Short timeout for tests
            cleanup_interval_seconds=0.1      # Fast cleanup for tests
        )
    
    @pytest.mark.asyncio
    async def test_result_aggregator_initialization(self, result_aggregator):
        """Test Result Aggregator initialization."""
        assert not result_aggregator.is_running
        assert len(result_aggregator.chunk_states) == 0
        assert result_aggregator.aggregation_timeout == 1.0
        assert result_aggregator.cleanup_interval == 0.1
        assert result_aggregator.cleanup_task is None
    
    @pytest.mark.asyncio
    async def test_result_aggregator_start_stop(self, result_aggregator, event_bus):
        """Test Result Aggregator start and stop lifecycle."""
        # Initially not running
        assert not result_aggregator.is_running
        
        # Start aggregator
        await result_aggregator.start()
        assert result_aggregator.is_running
        assert result_aggregator.cleanup_task is not None
        
        # Check subscriptions were set up
        vad_subscribers = await event_bus.get_subscribers("vad_completed")
        asr_subscribers = await event_bus.get_subscribers("asr_completed")
        diar_subscribers = await event_bus.get_subscribers("diarization_completed")
        
        assert len(vad_subscribers) >= 1
        assert len(asr_subscribers) >= 1
        assert len(diar_subscribers) >= 1
        
        # Stop aggregator
        await result_aggregator.stop()
        assert not result_aggregator.is_running
    
    @pytest.mark.asyncio
    async def test_single_component_result(self, result_aggregator, event_bus):
        """Test handling single component result."""
        await result_aggregator.start()
        
        # Create and publish VAD completion event
        vad_event = Event(
            name="vad_completed",
            data={
                "session_id": "test_session",
                "chunk_id": 1,
                "component": "vad",
                "success": True,
                "result": {"is_speech": True, "confidence": 0.9}
            },
            source="vad_worker",
            correlation_id="test_1"
        )
        
        await event_bus.publish(vad_event)
        await asyncio.sleep(0.01)  # Let event process
        
        # Check chunk state was created
        chunk_key = "test_session_1"
        assert chunk_key in result_aggregator.chunk_states
        
        chunk_state = result_aggregator.chunk_states[chunk_key]
        assert chunk_state.session_id == "test_session"
        assert chunk_state.chunk_id == 1
        assert "vad" in chunk_state.completed_components
        assert not chunk_state.is_complete()
        
        await result_aggregator.stop()
    
    @pytest.mark.asyncio
    async def test_complete_chunk_aggregation(self, result_aggregator, event_bus):
        """Test complete chunk aggregation with all components."""
        await result_aggregator.start()
        
        # Set up event capture
        captured_events = []
        async def capture_chunk_complete(event):
            captured_events.append(event)
        
        await event_bus.subscribe("chunk_complete", capture_chunk_complete)
        
        # Publish all three completion events
        events = [
            Event(
                name="vad_completed",
                data={
                    "session_id": "test_session",
                    "chunk_id": 1,
                    "component": "vad",
                    "success": True,
                    "result": {"is_speech": True, "confidence": 0.9}
                },
                source="vad_worker",
                correlation_id="test_1"
            ),
            Event(
                name="asr_completed",
                data={
                    "session_id": "test_session", 
                    "chunk_id": 1,
                    "component": "asr",
                    "success": True,
                    "result": {"text": "hello world", "confidence": 0.8}
                },
                source="asr_worker",
                correlation_id="test_1"
            ),
            Event(
                name="diarization_completed",
                data={
                    "session_id": "test_session",
                    "chunk_id": 1,
                    "component": "diarization", 
                    "success": True,
                    "result": {"speakers": ["SPEAKER_00"], "segments": []}
                },
                source="diarization_worker",
                correlation_id="test_1"
            )
        ]
        
        # Publish events
        for event in events:
            await event_bus.publish(event)
            await asyncio.sleep(0.01)
        
        # Wait for aggregation
        await asyncio.sleep(0.1)
        
        # Verify chunk_complete event was published
        assert len(captured_events) == 1
        complete_event = captured_events[0]
        
        assert complete_event.name == "chunk_complete"
        assert complete_event.data["session_id"] == "test_session"
        assert complete_event.data["chunk_id"] == 1
        assert complete_event.data["is_complete"] is True
        assert complete_event.data["is_timeout"] is False
        assert len(complete_event.data["completed_components"]) == 3
        assert len(complete_event.data["missing_components"]) == 0
        
        # Check all results are present
        results = complete_event.data["results"]
        assert "vad" in results
        assert "asr" in results
        assert "diarization" in results
        
        # Verify chunk state was cleaned up
        chunk_key = "test_session_1"
        assert chunk_key not in result_aggregator.chunk_states
        
        await result_aggregator.stop()
    
    @pytest.mark.asyncio
    async def test_partial_results_before_stop(self, result_aggregator, event_bus):
        """Test handling partial results during shutdown."""
        await result_aggregator.start()
        
        # Set up event capture
        captured_events = []
        async def capture_chunk_complete(event):
            captured_events.append(event)
        
        await event_bus.subscribe("chunk_complete", capture_chunk_complete)
        
        # Publish only VAD result
        vad_event = Event(
            name="vad_completed",
            data={
                "session_id": "test_session",
                "chunk_id": 1,
                "component": "vad",
                "success": True,
                "result": {"is_speech": True, "confidence": 0.9}
            },
            source="vad_worker",
            correlation_id="test_1"
        )
        
        await event_bus.publish(vad_event)
        await asyncio.sleep(0.01)
        
        # Stop aggregator (should flush remaining chunks)
        await result_aggregator.stop()
        
        # Verify partial result was published
        assert len(captured_events) == 1
        partial_event = captured_events[0]
        
        assert partial_event.data["is_complete"] is False
        assert partial_event.data["is_timeout"] is False
        assert len(partial_event.data["completed_components"]) == 1
        assert len(partial_event.data["missing_components"]) == 2
        assert "vad" in partial_event.data["results"]
        assert "asr" not in partial_event.data["results"]
        assert "diarization" not in partial_event.data["results"]
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, result_aggregator, event_bus):
        """Test timeout handling for incomplete chunks."""
        await result_aggregator.start()
        
        # Set up event capture
        captured_events = []
        async def capture_chunk_complete(event):
            captured_events.append(event)
        
        await event_bus.subscribe("chunk_complete", capture_chunk_complete)
        
        # Publish only VAD result  
        vad_event = Event(
            name="vad_completed",
            data={
                "session_id": "timeout_session",
                "chunk_id": 2,
                "component": "vad",
                "success": True,
                "result": {"is_speech": True, "confidence": 0.9}
            },
            source="vad_worker",
            correlation_id="timeout_2"
        )
        
        await event_bus.publish(vad_event)
        await asyncio.sleep(0.01)
        
        # Wait for timeout (1 second + cleanup interval)
        await asyncio.sleep(1.2)
        
        # Verify timeout event was published
        assert len(captured_events) == 1
        timeout_event = captured_events[0]
        
        assert timeout_event.data["session_id"] == "timeout_session"
        assert timeout_event.data["chunk_id"] == 2
        assert timeout_event.data["is_complete"] is False
        assert timeout_event.data["is_timeout"] is True
        assert len(timeout_event.data["completed_components"]) == 1
        assert len(timeout_event.data["missing_components"]) == 2
        
        await result_aggregator.stop()
    
    @pytest.mark.asyncio
    async def test_statistics_tracking(self, result_aggregator, event_bus):
        """Test statistics tracking functionality."""
        await result_aggregator.start()
        
        # Initial stats
        stats = result_aggregator.get_stats()
        assert stats["chunks_processed"] == 0
        assert stats["chunks_completed"] == 0
        assert stats["chunks_timed_out"] == 0
        assert stats["active_chunks"] == 0
        
        # Set up event capture  
        captured_events = []
        async def capture_chunk_complete(event):
            captured_events.append(event)
        
        await event_bus.subscribe("chunk_complete", capture_chunk_complete)
        
        # Process complete chunk
        events = [
            Event(
                name="vad_completed",
                data={
                    "session_id": "stats_session",
                    "chunk_id": 1,
                    "component": "vad", 
                    "success": True,
                    "result": {"is_speech": True}
                },
                source="vad_worker",
                correlation_id="stats_1"
            ),
            Event(
                name="asr_completed",
                data={
                    "session_id": "stats_session",
                    "chunk_id": 1,
                    "component": "asr",
                    "success": True,
                    "result": {"text": "hello"}
                },
                source="asr_worker",
                correlation_id="stats_1"
            ),
            Event(
                name="diarization_completed",
                data={
                    "session_id": "stats_session",
                    "chunk_id": 1,
                    "component": "diarization",
                    "success": True,
                    "result": {"speakers": [], "segments": []}
                },
                source="diarization_worker",
                correlation_id="stats_1"
            )
        ]
        
        for event in events:
            await event_bus.publish(event)
            await asyncio.sleep(0.01)
        
        await asyncio.sleep(0.1)
        
        # Check updated stats
        stats = result_aggregator.get_stats()
        assert stats["chunks_processed"] == 1
        assert stats["chunks_completed"] == 1
        assert stats["active_chunks"] == 0
        assert stats["average_aggregation_time_ms"] > 0
        
        await result_aggregator.stop()
    
    @pytest.mark.asyncio
    async def test_active_chunks_info(self, result_aggregator, event_bus):
        """Test active chunks information."""
        await result_aggregator.start()
        
        # Publish partial result
        vad_event = Event(
            name="vad_completed",
            data={
                "session_id": "active_session",
                "chunk_id": 1,
                "component": "vad",
                "success": True,
                "result": {"is_speech": True}
            },
            source="vad_worker",
            correlation_id="active_1"
        )
        
        await event_bus.publish(vad_event)
        await asyncio.sleep(0.01)
        
        # Check active chunks info
        active_chunks = result_aggregator.get_active_chunks()
        assert len(active_chunks) == 1
        
        chunk_key = "active_session_1"
        assert chunk_key in active_chunks
        
        chunk_info = active_chunks[chunk_key]
        assert chunk_info["session_id"] == "active_session"
        assert chunk_info["chunk_id"] == 1
        assert chunk_info["completion_percentage"] == pytest.approx(33.33, rel=1e-2)
        assert len(chunk_info["completed_components"]) == 1
        assert len(chunk_info["missing_components"]) == 2
        assert chunk_info["age_seconds"] >= 0
        
        await result_aggregator.stop()