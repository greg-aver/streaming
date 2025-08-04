"""
Integration tests for the complete speech processing pipeline.

Tests the full end-to-end flow:
WebSocket → VAD Worker → ASR Worker → Diarization Worker → Result Aggregator → Response
"""

import pytest
import asyncio
import time
import json
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock

from app.events import AsyncEventBus
from app.workers.vad import VADWorker
from app.workers.asr import ASRWorker
from app.workers.diarization import DiarizationWorker
from app.aggregators.result_aggregator import ResultAggregator
from app.handlers.websocket_handler import WebSocketHandler
from app.services.vad_service import MockVADService
from app.services.asr_service import MockASRService
from app.services.diarization_service import MockDiarizationService
from app.interfaces.events import Event
from app.config import ProcessingSettings, VADSettings, ASRSettings, DiarizationSettings


class MockWebSocket:
    """Enhanced mock WebSocket for integration testing."""
    
    def __init__(self):
        self.messages_sent = []
        self.messages_to_receive = []
        self.is_connected = True
        self.accepted = False
    
    async def accept(self):
        self.accepted = True
    
    async def send_text(self, text: str):
        if not self.is_connected:
            raise Exception("WebSocket disconnected")
        self.messages_sent.append(text)
    
    async def receive(self):
        if not self.messages_to_receive:
            if self.is_connected:
                await asyncio.sleep(10)
            return {"type": "websocket.disconnect"}
        return self.messages_to_receive.pop(0)
    
    def add_audio_message(self, audio_data: bytes):
        self.messages_to_receive.append({"type": "websocket.receive", "bytes": audio_data})
    
    def add_disconnect_message(self):
        self.messages_to_receive.append({"type": "websocket.disconnect"})
    
    def get_sent_messages(self) -> List[Dict[str, Any]]:
        """Get all sent messages as parsed JSON."""
        return [json.loads(msg) for msg in self.messages_sent]


class IntegrationTestPipeline:
    """Complete pipeline setup for integration testing."""
    
    def __init__(self):
        """Initialize all components for integration testing."""
        # Event bus
        self.event_bus = AsyncEventBus()
        
        # Configuration
        self.processing_config = ProcessingSettings(
            max_concurrent_workers=2,
            chunk_timeout_seconds=5,
            max_chunk_size_bytes=1024 * 1024
        )
        self.vad_config = VADSettings(
            model_name="silero_vad",
            confidence_threshold=0.5,
            frame_duration_ms=30,
            sample_rate=16000
        )
        self.asr_config = ASRSettings(
            model_name="base",
            language="ru",
            beam_size=5,
            temperature=0.0,
            compute_type="float16"
        )
        self.diarization_config = DiarizationSettings(
            model_name="pyannote/speaker-diarization-3.1",
            min_speakers=1,
            max_speakers=10,
            clustering_method="centroid"
        )
        
        # Services (Mock implementations)
        self.vad_service = MockVADService(self.vad_config)
        self.asr_service = MockASRService(self.asr_config)
        self.diarization_service = MockDiarizationService(self.diarization_config)
        
        # Workers
        self.vad_worker = self._create_vad_worker()
        self.asr_worker = self._create_asr_worker()
        self.diarization_worker = self._create_diarization_worker()
        
        # Result Aggregator
        self.result_aggregator = ResultAggregator(
            event_bus=self.event_bus,
            aggregation_timeout_seconds=10.0,
            cleanup_interval_seconds=1.0
        )
        
        # WebSocket Handler
        self.websocket_handler = WebSocketHandler(
            event_bus=self.event_bus,
            max_audio_chunk_size=1024 * 64,
            session_timeout_minutes=30
        )
        
        # Performance metrics
        self.metrics = {
            "start_time": None,
            "end_time": None,
            "processing_times": {},
            "events_captured": []
        }
    
    def _create_vad_worker(self) -> VADWorker:
        """Create VAD worker with manual initialization."""
        worker = VADWorker.__new__(VADWorker)
        
        # Initialize mixins
        from app.events import EventSubscriberMixin, EventPublisherMixin
        EventSubscriberMixin.__init__(worker, self.event_bus)
        EventPublisherMixin.__init__(worker, self.event_bus, "vad_worker")
        
        worker.vad_service = self.vad_service
        worker.config = self.processing_config
        worker.logger = MagicMock()
        
        # Worker state
        worker.is_running = False
        worker.processing_tasks = set()
        worker.max_concurrent_tasks = self.processing_config.max_concurrent_workers
        worker.chunk_timeout = self.processing_config.chunk_timeout_seconds
        
        return worker
    
    def _create_asr_worker(self) -> ASRWorker:
        """Create ASR worker with manual initialization."""
        worker = ASRWorker.__new__(ASRWorker)
        
        # Initialize mixins
        from app.events import EventSubscriberMixin, EventPublisherMixin
        EventSubscriberMixin.__init__(worker, self.event_bus)
        EventPublisherMixin.__init__(worker, self.event_bus, "asr_worker")
        
        worker.asr_service = self.asr_service
        worker.config = self.processing_config
        worker.logger = MagicMock()
        
        # Worker state
        worker.is_running = False
        worker.processing_tasks = set()
        worker.max_concurrent_tasks = self.processing_config.max_concurrent_workers
        worker.chunk_timeout = self.processing_config.chunk_timeout_seconds
        
        return worker
    
    def _create_diarization_worker(self) -> DiarizationWorker:
        """Create Diarization worker with manual initialization."""
        worker = DiarizationWorker.__new__(DiarizationWorker)
        
        # Initialize mixins
        from app.events import EventSubscriberMixin, EventPublisherMixin
        EventSubscriberMixin.__init__(worker, self.event_bus)
        EventPublisherMixin.__init__(worker, self.event_bus, "diarization_worker")
        
        worker.diarization_service = self.diarization_service
        worker.config = self.processing_config
        worker.logger = MagicMock()
        
        # Worker state
        worker.is_running = False
        worker.processing_tasks = set()
        worker.max_concurrent_tasks = self.processing_config.max_concurrent_workers
        worker.chunk_timeout = self.processing_config.chunk_timeout_seconds
        
        return worker
    
    async def start_all_components(self):
        """Start all pipeline components."""
        # Initialize services
        await self.vad_service.initialize()
        await self.asr_service.initialize()
        await self.diarization_service.initialize()
        
        # Start workers
        await self.vad_worker.start()
        await self.asr_worker.start()
        await self.diarization_worker.start()
        
        # Start result aggregator
        await self.result_aggregator.start()
        
        # Start WebSocket handler
        await self.websocket_handler.start()
    
    async def stop_all_components(self):
        """Stop all pipeline components."""
        await self.websocket_handler.stop()
        await self.result_aggregator.stop()
        await self.diarization_worker.stop()
        await self.asr_worker.stop()
        await self.vad_worker.stop()
    
    def start_metrics_collection(self):
        """Start collecting performance metrics."""
        self.metrics["start_time"] = time.time()
        self.metrics["events_captured"] = []
        self.metrics["processing_times"] = {}
    
    def record_event(self, event_name: str, timestamp: float = None):
        """Record an event for metrics."""
        if timestamp is None:
            timestamp = time.time()
        
        self.metrics["events_captured"].append({
            "event": event_name,
            "timestamp": timestamp,
            "relative_time": timestamp - self.metrics["start_time"] if self.metrics["start_time"] else 0
        })
    
    def finalize_metrics(self):
        """Finalize metrics collection."""
        self.metrics["end_time"] = time.time()
        if self.metrics["start_time"]:
            self.metrics["total_time"] = self.metrics["end_time"] - self.metrics["start_time"]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        return {
            "total_processing_time": self.metrics.get("total_time", 0),
            "events_count": len(self.metrics["events_captured"]),
            "events_timeline": self.metrics["events_captured"],
            "processing_times": self.metrics["processing_times"]
        }


class TestIntegrationPipeline:
    """Integration tests for the complete speech processing pipeline."""
    
    @pytest.fixture
    def pipeline(self):
        """Create integration test pipeline."""
        return IntegrationTestPipeline()
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_flow(self, pipeline):
        """Test complete end-to-end pipeline flow."""
        await pipeline.start_all_components()
        pipeline.start_metrics_collection()
        
        try:
            # Create mock WebSocket
            mock_ws = MockWebSocket()
            
            # Set up result capture
            final_results = []
            async def capture_final_result(event):
                final_results.append(event)
                pipeline.record_event("chunk_complete_received")
            
            await pipeline.event_bus.subscribe("chunk_complete", capture_final_result)
            
            # Simulate audio data processing
            audio_data = b"integration_test_audio_data" * 100  # 2700 bytes
            
            pipeline.record_event("audio_sent_to_websocket")
            
            # Process audio through WebSocket handler
            session_id = await pipeline.websocket_handler.session_manager.create_session()
            await pipeline.websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
            
            pipeline.record_event("session_created")
            
            # Send audio data
            await pipeline.websocket_handler.handle_audio_data(mock_ws, audio_data, session_id)
            
            pipeline.record_event("audio_processed_by_websocket")
            
            # Wait for complete processing
            max_wait_time = 15.0  # 15 seconds max wait
            wait_start = time.time()
            
            while len(final_results) == 0 and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(0.1)
            
            pipeline.finalize_metrics()
            
            # Verify results
            assert len(final_results) == 1, f"Expected 1 final result, got {len(final_results)}"
            
            final_result = final_results[0]
            assert final_result.name == "chunk_complete"
            
            result_data = final_result.data
            assert result_data["session_id"] == session_id
            assert result_data["chunk_id"] == 0
            assert result_data["is_complete"] is True
            assert len(result_data["completed_components"]) == 3
            assert "vad" in result_data["completed_components"]
            assert "asr" in result_data["completed_components"]
            assert "diarization" in result_data["completed_components"]
            
            # Verify all component results are present
            results = result_data["results"]
            assert "vad" in results
            assert "asr" in results  
            assert "diarization" in results
            
            # Verify VAD result structure
            vad_result = results["vad"]
            assert "result" in vad_result
            assert "is_speech" in vad_result["result"]
            assert "confidence" in vad_result["result"]
            
            # Verify ASR result structure
            asr_result = results["asr"]
            assert "result" in asr_result
            assert "text" in asr_result["result"]
            assert "confidence" in asr_result["result"]
            
            # Verify Diarization result structure
            diar_result = results["diarization"]
            assert "result" in diar_result
            assert "speakers" in diar_result["result"]
            assert "segments" in diar_result["result"]
            
            # Verify WebSocket responses were sent
            sent_messages = mock_ws.get_sent_messages()
            assert len(sent_messages) >= 1  # At least chunk_received acknowledgment
            
            # Check for chunk_received acknowledgment
            chunk_ack_found = any(msg.get("type") == "chunk_received" for msg in sent_messages)
            assert chunk_ack_found, "Chunk received acknowledgment not found"
            
            # Get metrics
            metrics = pipeline.get_metrics_summary()
            assert metrics["total_processing_time"] > 0
            assert metrics["events_count"] >= 4  # At least 4 events captured
            
            print(f"\n🎯 Integration Test Metrics:")
            print(f"Total processing time: {metrics['total_processing_time']:.3f}s")
            print(f"Events captured: {metrics['events_count']}")
            for event in metrics["events_timeline"]:
                print(f"  - {event['event']}: {event['relative_time']:.3f}s")
            
        finally:
            await pipeline.stop_all_components()
    
    @pytest.mark.asyncio
    async def test_multiple_audio_chunks_processing(self, pipeline):
        """Test processing multiple audio chunks in sequence."""
        await pipeline.start_all_components()
        
        try:
            mock_ws = MockWebSocket()
            
            # Set up result capture
            chunk_results = []
            async def capture_chunk_results(event):
                chunk_results.append(event)
            
            await pipeline.event_bus.subscribe("chunk_complete", capture_chunk_results)
            
            # Create session
            session_id = await pipeline.websocket_handler.session_manager.create_session()
            await pipeline.websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
            
            # Send multiple audio chunks
            num_chunks = 3
            for i in range(num_chunks):
                audio_data = b"multi_chunk_audio_data" * (50 + i)  # Different sizes
                await pipeline.websocket_handler.handle_audio_data(mock_ws, audio_data, session_id)
                await asyncio.sleep(0.05)  # Small delay between chunks
            
            # Wait for all chunks to be processed
            max_wait_time = 20.0
            wait_start = time.time()
            
            while len(chunk_results) < num_chunks and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(0.1)
            
            # Verify all chunks were processed
            assert len(chunk_results) == num_chunks, f"Expected {num_chunks} results, got {len(chunk_results)}"
            
            # Verify chunk IDs are sequential
            chunk_ids = [result.data["chunk_id"] for result in chunk_results]
            chunk_ids.sort()
            assert chunk_ids == list(range(num_chunks))
            
            # Verify all chunks have complete results
            for result in chunk_results:
                assert result.data["is_complete"] is True
                assert len(result.data["completed_components"]) == 3
            
        finally:
            await pipeline.stop_all_components()
    
    @pytest.mark.asyncio
    async def test_concurrent_sessions_processing(self, pipeline):
        """Test processing from multiple concurrent sessions."""
        await pipeline.start_all_components()
        
        try:
            # Create multiple sessions
            num_sessions = 3
            sessions_data = []
            
            for i in range(num_sessions):
                mock_ws = MockWebSocket()
                session_id = await pipeline.websocket_handler.session_manager.create_session()
                await pipeline.websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
                
                sessions_data.append({
                    "session_id": session_id,
                    "websocket": mock_ws
                })
            
            # Set up result capture
            all_results = []
            async def capture_all_results(event):
                all_results.append(event)
            
            await pipeline.event_bus.subscribe("chunk_complete", capture_all_results)
            
            # Send audio from all sessions simultaneously
            audio_tasks = []
            for i, session_data in enumerate(sessions_data):
                audio_data = b"concurrent_session_audio" * (30 + i)
                task = pipeline.websocket_handler.handle_audio_data(
                    session_data["websocket"], 
                    audio_data, 
                    session_data["session_id"]
                )
                audio_tasks.append(task)
            
            # Wait for all audio to be sent
            await asyncio.gather(*audio_tasks)
            
            # Wait for all processing to complete
            max_wait_time = 25.0
            wait_start = time.time()
            
            while len(all_results) < num_sessions and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(0.1)
            
            # Verify all sessions got results
            assert len(all_results) == num_sessions, f"Expected {num_sessions} results, got {len(all_results)}"
            
            # Verify results are from different sessions
            result_session_ids = {result.data["session_id"] for result in all_results}
            expected_session_ids = {session_data["session_id"] for session_data in sessions_data}
            assert result_session_ids == expected_session_ids
            
            # Verify all results are complete
            for result in all_results:
                assert result.data["is_complete"] is True
                assert len(result.data["completed_components"]) == 3
            
        finally:
            await pipeline.stop_all_components()
    
    @pytest.mark.asyncio
    async def test_pipeline_performance_metrics(self, pipeline):
        """Test pipeline performance and collect detailed metrics."""
        await pipeline.start_all_components()
        pipeline.start_metrics_collection()
        
        try:
            mock_ws = MockWebSocket()
            
            # Detailed event tracking
            event_timeline = []
            
            async def track_vad_completed(event):
                pipeline.record_event("vad_completed")
                event_timeline.append(("vad_completed", time.time()))
            
            async def track_asr_completed(event):
                pipeline.record_event("asr_completed")
                event_timeline.append(("asr_completed", time.time()))
            
            async def track_diarization_completed(event):
                pipeline.record_event("diarization_completed")
                event_timeline.append(("diarization_completed", time.time()))
            
            async def track_chunk_complete(event):
                pipeline.record_event("chunk_complete")
                event_timeline.append(("chunk_complete", time.time()))
            
            # Subscribe to all key events
            await pipeline.event_bus.subscribe("vad_completed", track_vad_completed)
            await pipeline.event_bus.subscribe("asr_completed", track_asr_completed)
            await pipeline.event_bus.subscribe("diarization_completed", track_diarization_completed)
            await pipeline.event_bus.subscribe("chunk_complete", track_chunk_complete)
            
            # Process audio
            session_id = await pipeline.websocket_handler.session_manager.create_session()
            await pipeline.websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
            
            audio_data = b"performance_test_audio" * 150  # ~4KB
            
            processing_start = time.time()
            await pipeline.websocket_handler.handle_audio_data(mock_ws, audio_data, session_id)
            
            # Wait for complete processing
            max_wait_time = 10.0
            wait_start = time.time()
            
            while len(event_timeline) < 4 and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(0.05)
            
            processing_end = time.time()
            pipeline.finalize_metrics()
            
            # Analyze performance
            total_processing_time = processing_end - processing_start
            
            # Verify all events occurred
            event_names = [event[0] for event in event_timeline]
            expected_events = ["vad_completed", "asr_completed", "diarization_completed", "chunk_complete"]
            
            for expected_event in expected_events:
                assert expected_event in event_names, f"Missing event: {expected_event}"
            
            # Calculate component processing times
            if len(event_timeline) >= 4:
                vad_time = event_timeline[0][1] - processing_start
                asr_time = event_timeline[1][1] - event_timeline[0][1]
                diarization_time = event_timeline[2][1] - event_timeline[1][1]
                aggregation_time = event_timeline[3][1] - event_timeline[2][1]
                
                print(f"\n📊 Performance Breakdown:")
                print(f"Total processing time: {total_processing_time:.3f}s")
                print(f"VAD processing: {vad_time:.3f}s")
                print(f"ASR processing: {asr_time:.3f}s")
                print(f"Diarization processing: {diarization_time:.3f}s")
                print(f"Result aggregation: {aggregation_time:.3f}s")
                
                # Performance assertions
                assert total_processing_time < 5.0, f"Total processing time too high: {total_processing_time:.3f}s"
                assert vad_time < 2.0, f"VAD processing time too high: {vad_time:.3f}s"
                assert asr_time < 2.0, f"ASR processing time too high: {asr_time:.3f}s"
                assert diarization_time < 2.0, f"Diarization processing time too high: {diarization_time:.3f}s"
                assert aggregation_time < 1.0, f"Aggregation time too high: {aggregation_time:.3f}s"
            
        finally:
            await pipeline.stop_all_components()
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, pipeline):
        """Test pipeline behavior under error conditions."""
        await pipeline.start_all_components()
        
        try:
            mock_ws = MockWebSocket()
            
            # Force an error in one component (ASR)
            original_transcribe = pipeline.asr_service.transcribe
            async def failing_transcribe(*args, **kwargs):
                raise Exception("Simulated ASR failure")
            
            pipeline.asr_service.transcribe = failing_transcribe
            
            # Set up result capture
            error_results = []
            async def capture_error_results(event):
                error_results.append(event)
            
            await pipeline.event_bus.subscribe("chunk_complete", capture_error_results)
            
            # Process audio that will cause ASR to fail
            session_id = await pipeline.websocket_handler.session_manager.create_session()
            await pipeline.websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
            
            audio_data = b"error_test_audio" * 50
            await pipeline.websocket_handler.handle_audio_data(mock_ws, audio_data, session_id)
            
            # Wait for processing
            max_wait_time = 10.0
            wait_start = time.time()
            
            while len(error_results) == 0 and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(0.1)
            
            # Verify partial result was still generated
            assert len(error_results) == 1
            
            error_result = error_results[0]
            assert error_result.data["is_complete"] is False  # Not complete due to ASR failure
            assert "vad" in error_result.data["completed_components"]  # VAD should succeed
            assert "asr" not in error_result.data["completed_components"]  # ASR should fail
            
            # Restore original method
            pipeline.asr_service.transcribe = original_transcribe
            
        finally:
            await pipeline.stop_all_components()