"""
Tests for WebSocket Handler implementation.

Tests WebSocket handling functionality:
- Connection management
- Audio data processing
- Session management
- Event integration
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.handlers.websocket_handler import WebSocketHandler, WebSocketManager, SessionManager
from app.events import AsyncEventBus
from app.interfaces.events import Event
from app.interfaces.websocket import WebSocketHandlerError, WebSocketManagerError, SessionManagerError


class MockWebSocket:
    """Mock WebSocket for testing."""
    
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
                # Simulate waiting
                await asyncio.sleep(10)
            return {"type": "websocket.disconnect"}
        return self.messages_to_receive.pop(0)
    
    def add_message(self, message_type: str, data=None):
        if message_type == "bytes":
            self.messages_to_receive.append({"type": "websocket.receive", "bytes": data})
        elif message_type == "text":
            self.messages_to_receive.append({"type": "websocket.receive", "text": data})
        elif message_type == "disconnect":
            self.messages_to_receive.append({"type": "websocket.disconnect"})
    
    def disconnect(self):
        self.is_connected = False


class TestSessionManager:
    """Test cases for SessionManager."""
    
    @pytest.fixture
    def session_manager(self):
        """Create SessionManager instance."""
        return SessionManager()
    
    @pytest.mark.asyncio
    async def test_create_session(self, session_manager):
        """Test session creation."""
        session_id = await session_manager.create_session()
        
        assert session_id.startswith("ws_session_")
        assert len(session_id) == 19  # ws_session_ + 8 hex chars
        
        session_info = await session_manager.get_session_info(session_id)
        assert session_info is not None
        assert session_info["session_id"] == session_id
        assert session_info["status"] == "active"
        assert session_info["chunk_counter"] == 0
        assert session_info["total_chunks"] == 0
        assert session_info["total_audio_bytes"] == 0
    
    @pytest.mark.asyncio
    async def test_get_next_chunk_id(self, session_manager):
        """Test chunk ID generation."""
        session_id = await session_manager.create_session()
        
        # Get sequential chunk IDs
        chunk_id_1 = await session_manager.get_next_chunk_id(session_id)
        chunk_id_2 = await session_manager.get_next_chunk_id(session_id)
        chunk_id_3 = await session_manager.get_next_chunk_id(session_id)
        
        assert chunk_id_1 == 0
        assert chunk_id_2 == 1
        assert chunk_id_3 == 2
        
        # Check session stats updated
        session_info = await session_manager.get_session_info(session_id)
        assert session_info["chunk_counter"] == 3
        assert session_info["total_chunks"] == 3
    
    @pytest.mark.asyncio
    async def test_nonexistent_session_error(self, session_manager):
        """Test error for nonexistent session."""
        with pytest.raises(SessionManagerError):
            await session_manager.get_next_chunk_id("nonexistent")
    
    @pytest.mark.asyncio
    async def test_update_session(self, session_manager):
        """Test session updates."""
        session_id = await session_manager.create_session()
        
        await session_manager.update_session(session_id, {
            "custom_field": "test_value",
            "total_audio_bytes": 1024
        })
        
        session_info = await session_manager.get_session_info(session_id)
        assert session_info["custom_field"] == "test_value"
        assert session_info["total_audio_bytes"] == 1024
    
    @pytest.mark.asyncio
    async def test_end_session(self, session_manager):
        """Test session ending."""
        session_id = await session_manager.create_session()
        
        await session_manager.end_session(session_id)
        
        session_info = await session_manager.get_session_info(session_id)
        assert session_info["status"] == "ended"
        assert "ended_at" in session_info


class TestWebSocketManager:
    """Test cases for WebSocketManager."""
    
    @pytest.fixture
    def websocket_manager(self):
        """Create WebSocketManager instance."""
        return WebSocketManager()
    
    @pytest.mark.asyncio
    async def test_add_remove_connection(self, websocket_manager):
        """Test adding and removing connections."""
        mock_ws = MockWebSocket()
        session_id = "test_session"
        
        # Add connection
        await websocket_manager.add_connection(session_id, mock_ws)
        
        # Verify connection added
        connection = await websocket_manager.get_connection(session_id)
        assert connection is mock_ws
        
        active_sessions = await websocket_manager.get_active_sessions()
        assert session_id in active_sessions
        
        # Remove connection
        await websocket_manager.remove_connection(session_id)
        
        # Verify connection removed
        connection = await websocket_manager.get_connection(session_id)
        assert connection is None
        
        active_sessions = await websocket_manager.get_active_sessions()
        assert session_id not in active_sessions
    
    @pytest.mark.asyncio
    async def test_broadcast_to_session(self, websocket_manager):
        """Test broadcasting to specific session."""
        mock_ws = MockWebSocket()
        session_id = "test_session"
        
        await websocket_manager.add_connection(session_id, mock_ws)
        
        message = {"type": "test", "data": "hello"}
        await websocket_manager.broadcast_to_session(session_id, message)
        
        assert len(mock_ws.messages_sent) == 1
        sent_message = json.loads(mock_ws.messages_sent[0])
        assert sent_message == message
    
    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_session(self, websocket_manager):
        """Test error when broadcasting to nonexistent session."""
        with pytest.raises(WebSocketManagerError):
            await websocket_manager.broadcast_to_session("nonexistent", {"test": "data"})


class TestWebSocketHandler:
    """Test cases for WebSocketHandler."""
    
    @pytest.fixture
    def event_bus(self):
        """Create AsyncEventBus instance."""
        return AsyncEventBus()
    
    @pytest.fixture
    def websocket_handler(self, event_bus):
        """Create WebSocketHandler instance."""
        return WebSocketHandler(
            event_bus=event_bus,
            max_audio_chunk_size=1024,
            session_timeout_minutes=30
        )
    
    @pytest.mark.asyncio
    async def test_websocket_handler_initialization(self, websocket_handler):
        """Test WebSocket handler initialization."""
        assert not websocket_handler.is_running
        assert websocket_handler.max_audio_chunk_size == 1024
        assert websocket_handler.session_timeout == timedelta(minutes=30)
        assert websocket_handler.websocket_manager is not None
        assert websocket_handler.session_manager is not None
    
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, websocket_handler, event_bus):
        """Test handler start/stop lifecycle."""
        # Initially not running
        assert not websocket_handler.is_running
        
        # Start handler
        await websocket_handler.start()
        assert websocket_handler.is_running
        
        # Check subscriptions
        subscribers = await event_bus.get_subscribers("chunk_complete")
        assert len(subscribers) >= 1
        
        # Stop handler
        await websocket_handler.stop()
        assert not websocket_handler.is_running
    
    @pytest.mark.asyncio
    async def test_audio_data_handling(self, websocket_handler, event_bus):
        """Test audio data processing."""
        await websocket_handler.start()
        
        # Set up event capture
        captured_events = []
        async def capture_audio_event(event):
            captured_events.append(event)
        
        await event_bus.subscribe("audio_chunk_received", capture_audio_event)
        
        # Create mock WebSocket and session
        mock_ws = MockWebSocket()
        session_id = await websocket_handler.session_manager.create_session()
        
        # Process audio data
        audio_data = b"test_audio_data" * 10
        await websocket_handler.handle_audio_data(mock_ws, audio_data, session_id)
        
        # Verify event was published
        await asyncio.sleep(0.01)
        assert len(captured_events) == 1
        
        audio_event = captured_events[0]
        assert audio_event.name == "audio_chunk_received"
        assert audio_event.data["session_id"] == session_id
        assert audio_event.data["chunk_id"] == 0
        assert audio_event.data["data"] == audio_data
        
        # Verify acknowledgment sent
        assert len(mock_ws.messages_sent) == 1
        ack_message = json.loads(mock_ws.messages_sent[0])
        assert ack_message["type"] == "chunk_received"
        assert ack_message["chunk_id"] == 0
        assert ack_message["size"] == len(audio_data)
        
        await websocket_handler.stop()
    
    @pytest.mark.asyncio
    async def test_large_audio_chunk_rejection(self, websocket_handler):
        """Test rejection of oversized audio chunks."""
        await websocket_handler.start()
        
        mock_ws = MockWebSocket()
        session_id = await websocket_handler.session_manager.create_session()
        
        # Try to send chunk larger than limit
        large_audio_data = b"x" * (websocket_handler.max_audio_chunk_size + 1)
        await websocket_handler.handle_audio_data(mock_ws, large_audio_data, session_id)
        
        # Verify error message sent
        assert len(mock_ws.messages_sent) == 1
        error_message = json.loads(mock_ws.messages_sent[0])
        assert error_message["type"] == "error"
        assert "too large" in error_message["message"]
        
        await websocket_handler.stop()
    
    @pytest.mark.asyncio
    async def test_chunk_complete_handling(self, websocket_handler, event_bus):
        """Test handling of chunk_complete events."""
        await websocket_handler.start()
        
        # Create session and connection
        mock_ws = MockWebSocket()
        session_id = await websocket_handler.session_manager.create_session()
        await websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
        
        # Create chunk_complete event
        chunk_complete_event = Event(
            name="chunk_complete",
            data={
                "session_id": session_id,
                "chunk_id": 1,
                "is_complete": True,
                "is_timeout": False,
                "completed_components": ["vad", "asr", "diarization"],
                "missing_components": [],
                "aggregation_time_ms": 150.5,
                "results": {
                    "vad": {"is_speech": True, "confidence": 0.9},
                    "asr": {"text": "hello world", "confidence": 0.8},
                    "diarization": {"speakers": ["SPEAKER_00"], "segments": []}
                }
            },
            source="result_aggregator",
            correlation_id=f"{session_id}_1"
        )
        
        # Publish event
        await event_bus.publish(chunk_complete_event)
        await asyncio.sleep(0.01)
        
        # Verify response sent to client
        assert len(mock_ws.messages_sent) == 1
        response = json.loads(mock_ws.messages_sent[0])
        
        assert response["type"] == "processing_complete"
        assert response["session_id"] == session_id
        assert response["chunk_id"] == 1
        assert response["is_complete"] is True
        assert response["is_timeout"] is False
        assert len(response["completed_components"]) == 3
        assert len(response["missing_components"]) == 0
        assert "results" in response
        assert "vad" in response["results"]
        assert "asr" in response["results"]
        assert "diarization" in response["results"]
        
        await websocket_handler.stop()
    
    @pytest.mark.asyncio
    async def test_send_response(self, websocket_handler):
        """Test sending responses to WebSocket."""
        mock_ws = MockWebSocket()
        
        response = {"type": "test", "message": "hello"}
        await websocket_handler.send_response(mock_ws, response)
        
        assert len(mock_ws.messages_sent) == 1
        sent_message = json.loads(mock_ws.messages_sent[0])
        assert sent_message == response
    
    @pytest.mark.asyncio
    async def test_send_response_error(self, websocket_handler):
        """Test error handling when sending response fails."""
        mock_ws = MockWebSocket()
        mock_ws.disconnect()
        
        with pytest.raises(WebSocketHandlerError):
            await websocket_handler.send_response(mock_ws, {"test": "data"})
    
    @pytest.mark.asyncio
    async def test_handle_disconnect(self, websocket_handler):
        """Test WebSocket disconnection handling."""
        await websocket_handler.start()
        
        # Create session and connection
        session_id = await websocket_handler.session_manager.create_session()
        mock_ws = MockWebSocket()
        await websocket_handler.websocket_manager.add_connection(session_id, mock_ws)
        
        # Handle disconnect
        await websocket_handler.handle_disconnect(session_id)
        
        # Verify cleanup
        connection = await websocket_handler.websocket_manager.get_connection(session_id)
        assert connection is None
        
        session_info = await websocket_handler.session_manager.get_session_info(session_id)
        assert session_info["status"] == "ended"
        
        await websocket_handler.stop()
    
    @pytest.mark.asyncio
    async def test_get_stats(self, websocket_handler):
        """Test statistics retrieval."""
        stats = websocket_handler.get_stats()
        
        assert "is_running" in stats
        assert "active_connections" in stats
        assert "max_audio_chunk_size" in stats
        assert "session_timeout_minutes" in stats
        assert "total_sessions" in stats
        
        assert stats["is_running"] is False
        assert stats["max_audio_chunk_size"] == 1024
        assert stats["session_timeout_minutes"] == 30
    
    @pytest.mark.asyncio
    async def test_empty_audio_data_handling(self, websocket_handler):
        """Test handling of empty audio data."""
        await websocket_handler.start()
        
        mock_ws = MockWebSocket()
        session_id = await websocket_handler.session_manager.create_session()
        
        # Send empty audio data
        await websocket_handler.handle_audio_data(mock_ws, b"", session_id)
        
        # Should not send any messages for empty data
        assert len(mock_ws.messages_sent) == 0
        
        await websocket_handler.stop()