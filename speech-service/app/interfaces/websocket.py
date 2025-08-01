"""
WebSocket interface definitions for the speech-to-text service.

This module defines abstract interfaces for WebSocket handling,
following Clean Architecture principles.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from fastapi import WebSocket


class IWebSocketHandler(ABC):
    """
    Abstract interface for WebSocket connection handling.
    
    Defines the contract for managing WebSocket connections,
    handling incoming audio data, and sending responses.
    """
    
    @abstractmethod
    async def handle_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
            
        Raises:
            WebSocketHandlerError: If connection handling fails
        """
        pass
    
    @abstractmethod
    async def handle_audio_data(
        self, 
        websocket: WebSocket, 
        data: bytes, 
        session_id: str
    ) -> None:
        """
        Handle incoming audio data from WebSocket.
        
        Args:
            websocket: WebSocket connection
            data: Raw audio bytes
            session_id: Session identifier
            
        Raises:
            WebSocketHandlerError: If data handling fails
        """
        pass
    
    @abstractmethod
    async def send_response(
        self, 
        websocket: WebSocket, 
        response: Dict[str, Any]
    ) -> None:
        """
        Send response back to WebSocket client.
        
        Args:
            websocket: WebSocket connection
            response: Response data to send
            
        Raises:
            WebSocketHandlerError: If sending fails
        """
        pass
    
    @abstractmethod
    async def handle_disconnect(self, session_id: str) -> None:
        """
        Handle WebSocket disconnection cleanup.
        
        Args:
            session_id: Session identifier to clean up
        """
        pass


class IWebSocketManager(ABC):
    """
    Abstract interface for managing multiple WebSocket connections.
    
    Provides methods for tracking active connections and
    broadcasting messages to multiple clients.
    """
    
    @abstractmethod
    async def add_connection(self, session_id: str, websocket: WebSocket) -> None:
        """
        Add a new WebSocket connection.
        
        Args:
            session_id: Unique session identifier
            websocket: WebSocket connection instance
        """
        pass
    
    @abstractmethod
    async def remove_connection(self, session_id: str) -> None:
        """
        Remove a WebSocket connection.
        
        Args:
            session_id: Session identifier to remove
        """
        pass
    
    @abstractmethod
    async def get_connection(self, session_id: str) -> Optional[WebSocket]:
        """
        Get WebSocket connection by session ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            WebSocket instance or None if not found
        """
        pass
    
    @abstractmethod
    async def broadcast_to_session(
        self, 
        session_id: str, 
        message: Dict[str, Any]
    ) -> None:
        """
        Send message to a specific session.
        
        Args:
            session_id: Target session identifier
            message: Message data to send
            
        Raises:
            WebSocketManagerError: If broadcasting fails
        """
        pass
    
    @abstractmethod
    async def get_active_sessions(self) -> list[str]:
        """
        Get list of all active session IDs.
        
        Returns:
            List of active session identifiers
        """
        pass


class ISessionManager(ABC):
    """
    Abstract interface for managing session state.
    
    Handles creation, tracking, and cleanup of processing sessions.
    """
    
    @abstractmethod
    async def create_session(self) -> str:
        """
        Create a new processing session.
        
        Returns:
            Unique session identifier
        """
        pass
    
    @abstractmethod
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session information dictionary or None if not found
        """
        pass
    
    @abstractmethod
    async def update_session(
        self, 
        session_id: str, 
        data: Dict[str, Any]
    ) -> None:
        """
        Update session information.
        
        Args:
            session_id: Session identifier
            data: Data to update in session
        """
        pass
    
    @abstractmethod
    async def end_session(self, session_id: str) -> None:
        """
        End a processing session and clean up resources.
        
        Args:
            session_id: Session identifier to end
        """
        pass
    
    @abstractmethod
    async def get_next_chunk_id(self, session_id: str) -> int:
        """
        Get the next chunk ID for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Next chunk ID number
        """
        pass


# Exception classes for WebSocket interfaces
class WebSocketError(Exception):
    """Base exception for WebSocket operations."""
    pass


class WebSocketHandlerError(WebSocketError):
    """Exception raised by WebSocket handler operations."""
    pass


class WebSocketManagerError(WebSocketError):
    """Exception raised by WebSocket manager operations."""
    pass


class SessionManagerError(Exception):
    """Exception raised by session manager operations."""
    pass