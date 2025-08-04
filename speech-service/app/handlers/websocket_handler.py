"""
WebSocket Handler implementation.

This module provides WebSocket handling for real-time speech-to-text processing,
managing connections, audio data intake, and result delivery.
"""

import asyncio
import json
import uuid
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import structlog
from fastapi import WebSocket, WebSocketDisconnect

from ..interfaces.websocket import (
    IWebSocketHandler, 
    IWebSocketManager, 
    ISessionManager,
    WebSocketHandlerError,
    WebSocketManagerError,
    SessionManagerError
)
from ..interfaces.events import IEventBus, Event
from ..events import EventPublisherMixin, EventSubscriberMixin
from ..models.audio import AudioChunkModel


class SessionManager(ISessionManager):
    """
    Session Manager implementation.
    
    Manages processing sessions, tracking chunk IDs and session metadata.
    """
    
    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    async def create_session(self) -> str:
        """Create a new processing session."""
        session_id = f"ws_session_{uuid.uuid4().hex[:8]}"
        
        self.sessions[session_id] = {
            "session_id": session_id,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "chunk_counter": 0,
            "total_chunks": 0,
            "total_audio_bytes": 0,
            "status": "active"
        }
        
        self.logger.info("Session created", session_id=session_id)
        return session_id
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        return self.sessions.get(session_id)
    
    async def update_session(self, session_id: str, data: Dict[str, Any]) -> None:
        """Update session information."""
        if session_id in self.sessions:
            self.sessions[session_id].update(data)
            self.sessions[session_id]["last_activity"] = datetime.utcnow()
    
    async def end_session(self, session_id: str) -> None:
        """End session and clean up."""
        if session_id in self.sessions:
            session_info = self.sessions[session_id]
            session_info["status"] = "ended"
            session_info["ended_at"] = datetime.utcnow()
            duration = session_info["ended_at"] - session_info["created_at"]
            
            self.logger.info(
                "Session ended",
                session_id=session_id,
                duration_seconds=duration.total_seconds(),
                total_chunks=session_info["total_chunks"],
                total_audio_bytes=session_info["total_audio_bytes"]
            )
            
            # Clean up after 5 minutes for debugging
            asyncio.create_task(self._cleanup_session_later(session_id, 300))
    
    async def get_next_chunk_id(self, session_id: str) -> int:
        """Get next chunk ID for session."""
        if session_id not in self.sessions:
            raise SessionManagerError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        chunk_id = session["chunk_counter"]
        session["chunk_counter"] += 1
        session["total_chunks"] += 1
        session["last_activity"] = datetime.utcnow()
        
        return chunk_id
    
    async def _cleanup_session_later(self, session_id: str, delay_seconds: int) -> None:
        """Clean up session after delay."""
        await asyncio.sleep(delay_seconds)
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.debug("Session cleaned up", session_id=session_id)


class WebSocketManager(IWebSocketManager):
    """
    WebSocket Manager implementation.
    
    Manages multiple WebSocket connections and provides broadcasting capabilities.
    """
    
    def __init__(self):
        """Initialize WebSocket manager."""
        self.connections: Dict[str, WebSocket] = {}
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    async def add_connection(self, session_id: str, websocket: WebSocket) -> None:
        """Add WebSocket connection."""
        self.connections[session_id] = websocket
        self.logger.info(
            "WebSocket connection added",
            session_id=session_id,
            total_connections=len(self.connections)
        )
    
    async def remove_connection(self, session_id: str) -> None:
        """Remove WebSocket connection."""
        if session_id in self.connections:
            del self.connections[session_id]
            self.logger.info(
                "WebSocket connection removed",
                session_id=session_id,
                total_connections=len(self.connections)
            )
    
    async def get_connection(self, session_id: str) -> Optional[WebSocket]:
        """Get WebSocket connection."""
        return self.connections.get(session_id)
    
    async def broadcast_to_session(self, session_id: str, message: Dict[str, Any]) -> None:
        """Send message to specific session."""
        websocket = self.connections.get(session_id)
        if not websocket:
            raise WebSocketManagerError(f"No connection found for session {session_id}")
        
        try:
            await websocket.send_text(json.dumps(message))
            self.logger.debug(
                "Message sent to session",
                session_id=session_id,
                message_type=message.get("type", "unknown")
            )
        except Exception as e:
            self.logger.error(
                "Failed to send message to session",
                session_id=session_id,
                error=str(e)
            )
            raise WebSocketManagerError(f"Failed to send message: {e}")
    
    async def get_active_sessions(self) -> List[str]:
        """Get active session IDs."""
        return list(self.connections.keys())


class WebSocketHandler(IWebSocketHandler, EventPublisherMixin, EventSubscriberMixin):
    """
    WebSocket Handler implementation.
    
    Handles WebSocket connections, processes audio data, and manages
    communication between clients and the speech processing pipeline.
    """
    
    def __init__(
        self,
        event_bus: IEventBus,
        websocket_manager: Optional[IWebSocketManager] = None,
        session_manager: Optional[ISessionManager] = None,
        max_audio_chunk_size: int = 1024 * 64,  # 64KB chunks
        session_timeout_minutes: int = 30
    ):
        """
        Initialize WebSocket handler.
        
        Args:
            event_bus: Event bus for publishing/subscribing
            websocket_manager: WebSocket connection manager
            session_manager: Session state manager
            max_audio_chunk_size: Maximum size for audio chunks
            session_timeout_minutes: Session timeout in minutes
        """
        # Initialize mixins
        EventSubscriberMixin.__init__(self, event_bus)
        EventPublisherMixin.__init__(self, event_bus, "websocket_handler")
        
        self.websocket_manager = websocket_manager or WebSocketManager()
        self.session_manager = session_manager or SessionManager()
        self.max_audio_chunk_size = max_audio_chunk_size
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.is_running = False
        
        self.logger.info(
            "WebSocket handler initialized",
            max_audio_chunk_size=max_audio_chunk_size,
            session_timeout_minutes=session_timeout_minutes
        )
    
    async def start(self) -> None:
        """Start WebSocket handler and subscribe to events."""
        if self.is_running:
            return
        
        self.logger.info("Starting WebSocket handler")
        
        # Subscribe to chunk completion events
        await self.subscribe_to_event("chunk_complete", self._handle_chunk_complete)
        
        self.is_running = True
        self.logger.info("WebSocket handler started successfully")
    
    async def stop(self) -> None:
        """Stop WebSocket handler and clean up."""
        if not self.is_running:
            return
        
        self.logger.info("Stopping WebSocket handler")
        
        self.is_running = False
        
        # Disconnect all active connections
        active_sessions = await self.websocket_manager.get_active_sessions()
        for session_id in active_sessions:
            await self.handle_disconnect(session_id)
        
        # Clean up subscriptions
        await self.cleanup_subscriptions()
        
        self.logger.info("WebSocket handler stopped successfully")
    
    async def handle_connection(self, websocket: WebSocket) -> None:
        """
        Handle new WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
        """
        try:
            # Accept connection
            await websocket.accept()
            
            # Create session
            session_id = await self.session_manager.create_session()
            
            # Add to connection manager
            await self.websocket_manager.add_connection(session_id, websocket)
            
            # Send welcome message
            await self.send_response(websocket, {
                "type": "connection_established",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Connected to speech-to-text service"
            })
            
            self.logger.info("WebSocket connection established", session_id=session_id)
            
            # Handle messages
            await self._handle_messages(websocket, session_id)
            
        except WebSocketDisconnect:
            self.logger.info("WebSocket disconnected normally")
        except Exception as e:
            self.logger.error("Error handling WebSocket connection", error=str(e))
            raise WebSocketHandlerError(f"Connection handling failed: {e}")
    
    async def _handle_messages(self, websocket: WebSocket, session_id: str) -> None:
        """Handle incoming WebSocket messages."""
        try:
            while True:
                message = await websocket.receive()
                
                if message["type"] == "websocket.disconnect":
                    break
                elif message["type"] == "websocket.receive":
                    if "bytes" in message:
                        # Binary audio data
                        audio_data = message["bytes"]
                        await self.handle_audio_data(websocket, audio_data, session_id)
                    elif "text" in message:
                        # Text command
                        await self._handle_text_message(websocket, message["text"], session_id)
                
        except WebSocketDisconnect:
            pass
        except Exception as e:
            self.logger.error(
                "Error handling WebSocket messages",
                session_id=session_id,
                error=str(e)
            )
        finally:
            await self.handle_disconnect(session_id)
    
    async def _handle_text_message(
        self, 
        websocket: WebSocket, 
        text: str, 
        session_id: str
    ) -> None:
        """Handle text messages from client."""
        try:
            data = json.loads(text)
            command = data.get("command")
            
            if command == "ping":
                await self.send_response(websocket, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif command == "get_session_info":
                session_info = await self.session_manager.get_session_info(session_id)
                await self.send_response(websocket, {
                    "type": "session_info",
                    "session_info": session_info
                })
            else:
                await self.send_response(websocket, {
                    "type": "error",
                    "message": f"Unknown command: {command}"
                })
                
        except json.JSONDecodeError:
            await self.send_response(websocket, {
                "type": "error",
                "message": "Invalid JSON message"
            })
    
    async def handle_audio_data(
        self, 
        websocket: WebSocket, 
        data: bytes, 
        session_id: str
    ) -> None:
        """
        Handle incoming audio data.
        
        Args:
            websocket: WebSocket connection
            data: Raw audio bytes
            session_id: Session identifier
        """
        try:
            if len(data) == 0:
                return
            
            if len(data) > self.max_audio_chunk_size:
                await self.send_response(websocket, {
                    "type": "error",
                    "message": f"Audio chunk too large: {len(data)} bytes (max: {self.max_audio_chunk_size})"
                })
                return
            
            # Get next chunk ID
            chunk_id = await self.session_manager.get_next_chunk_id(session_id)
            
            # Update session stats
            await self.session_manager.update_session(session_id, {
                "total_audio_bytes": (await self.session_manager.get_session_info(session_id))["total_audio_bytes"] + len(data)
            })
            
            # Create audio chunk model
            audio_chunk = AudioChunkModel(
                session_id=session_id,
                chunk_id=chunk_id,
                data=data,
                sample_rate=16000,  # Default, could be configurable
                channels=1          # Default mono
            )
            
            # Publish audio_chunk_received event
            await self.publish_event(
                "audio_chunk_received",
                {
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "data": data,
                    "sample_rate": audio_chunk.sample_rate,
                    "channels": audio_chunk.channels,
                    "timestamp": datetime.utcnow().isoformat()
                },
                correlation_id=f"{session_id}_{chunk_id}"
            )
            
            self.logger.debug(
                "Audio chunk received and published",
                session_id=session_id,
                chunk_id=chunk_id,
                data_size=len(data)
            )
            
            # Send acknowledgment
            await self.send_response(websocket, {
                "type": "chunk_received",
                "chunk_id": chunk_id,
                "size": len(data),
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            self.logger.error(
                "Error handling audio data",
                session_id=session_id,
                error=str(e)
            )
            await self.send_response(websocket, {
                "type": "error",
                "message": f"Failed to process audio data: {str(e)}"
            })
    
    async def send_response(self, websocket: WebSocket, response: Dict[str, Any]) -> None:
        """
        Send response to WebSocket client.
        
        Args:
            websocket: WebSocket connection
            response: Response data
        """
        try:
            await websocket.send_text(json.dumps(response))
        except Exception as e:
            self.logger.error("Failed to send WebSocket response", error=str(e))
            raise WebSocketHandlerError(f"Failed to send response: {e}")
    
    async def handle_disconnect(self, session_id: str) -> None:
        """
        Handle WebSocket disconnection.
        
        Args:
            session_id: Session to clean up
        """
        try:
            # Remove from connection manager
            await self.websocket_manager.remove_connection(session_id)
            
            # End session
            await self.session_manager.end_session(session_id)
            
            self.logger.info("WebSocket disconnection handled", session_id=session_id)
            
        except Exception as e:
            self.logger.error(
                "Error handling WebSocket disconnect",
                session_id=session_id,
                error=str(e)
            )
    
    async def _handle_chunk_complete(self, event: Event) -> None:
        """
        Handle chunk_complete events from Result Aggregator.
        
        Args:
            event: Chunk completion event
        """
        try:
            data = event.data
            session_id = data.get("session_id")
            chunk_id = data.get("chunk_id")
            
            if not session_id:
                self.logger.warning("Chunk complete event missing session_id", event_data=data)
                return
            
            # Check if session has active connection
            websocket = await self.websocket_manager.get_connection(session_id)
            if not websocket:
                self.logger.debug(
                    "No active connection for completed chunk",
                    session_id=session_id,
                    chunk_id=chunk_id
                )
                return
            
            # Prepare response message
            response = {
                "type": "processing_complete",
                "session_id": session_id,
                "chunk_id": chunk_id,
                "is_complete": data.get("is_complete", False),
                "is_timeout": data.get("is_timeout", False),
                "completed_components": data.get("completed_components", []),
                "missing_components": data.get("missing_components", []),
                "aggregation_time_ms": data.get("aggregation_time_ms", 0),
                "results": data.get("results", {}),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send result to client
            await self.websocket_manager.broadcast_to_session(session_id, response)
            
            self.logger.info(
                "Processing result sent to client",
                session_id=session_id,
                chunk_id=chunk_id,
                is_complete=response["is_complete"],
                components_count=len(response["completed_components"])
            )
            
        except Exception as e:
            self.logger.error(
                "Error handling chunk complete event",
                error=str(e),
                correlation_id=event.correlation_id
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket handler statistics."""
        return {
            "is_running": self.is_running,
            "active_connections": len(self.websocket_manager.connections) if hasattr(self.websocket_manager, 'connections') else 0,
            "max_audio_chunk_size": self.max_audio_chunk_size,
            "session_timeout_minutes": self.session_timeout.total_seconds() / 60,
            "total_sessions": len(self.session_manager.sessions) if hasattr(self.session_manager, 'sessions') else 0
        }