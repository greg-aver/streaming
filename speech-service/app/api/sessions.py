"""
Session management API endpoints.

Provides REST API for managing WebSocket sessions, viewing session status,
and controlling session lifecycle.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings


# Response models
class SessionInfo(BaseModel):
    """Information about a WebSocket session."""
    
    session_id: str = Field(description="Unique session identifier")
    created_at: datetime = Field(description="Session creation timestamp")
    last_activity: datetime = Field(description="Last activity timestamp")
    is_active: bool = Field(description="Whether session is currently active")
    connection_status: str = Field(description="WebSocket connection status")
    processed_chunks: int = Field(description="Number of processed audio chunks")
    total_processing_time_ms: float = Field(description="Total processing time in milliseconds")
    metadata: Dict[str, Any] = Field(description="Session metadata")


class SessionList(BaseModel):
    """List of sessions with pagination info."""
    
    sessions: List[SessionInfo] = Field(description="List of sessions")
    total_count: int = Field(description="Total number of sessions")
    active_count: int = Field(description="Number of active sessions")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")


class SessionStats(BaseModel):
    """Session statistics."""
    
    total_sessions: int = Field(description="Total number of sessions created")
    active_sessions: int = Field(description="Number of currently active sessions")
    completed_sessions: int = Field(description="Number of completed sessions")
    average_session_duration_seconds: float = Field(description="Average session duration")
    total_chunks_processed: int = Field(description="Total audio chunks processed")
    average_processing_time_ms: float = Field(description="Average chunk processing time")


class SessionActionResponse(BaseModel):
    """Response for session action operations."""
    
    success: bool = Field(description="Whether operation was successful")
    message: str = Field(description="Human-readable message")
    session_id: str = Field(description="Session ID that was affected")
    timestamp: datetime = Field(description="Operation timestamp")


# Router
router = APIRouter(prefix="/sessions", tags=["sessions"])


# Mock session storage (in real implementation, this would be injected via DI)
_mock_sessions: Dict[str, Dict[str, Any]] = {}


def get_mock_session_data() -> Dict[str, Dict[str, Any]]:
    """Get mock session data for demonstration."""
    from datetime import timedelta
    
    now = datetime.now(timezone.utc)
    
    if not _mock_sessions:
        # Create some mock sessions for demonstration
        _mock_sessions.update({
            "ws_session_demo1": {
                "session_id": "ws_session_demo1",
                "created_at": now - timedelta(hours=1),
                "last_activity": now - timedelta(minutes=5),
                "is_active": True,
                "connection_status": "connected",
                "processed_chunks": 15,
                "total_processing_time_ms": 2543.5,
                "metadata": {"client_ip": "192.168.1.100", "user_agent": "WebSocket Client"}
            },
            "ws_session_demo2": {
                "session_id": "ws_session_demo2", 
                "created_at": now - timedelta(hours=2),
                "last_activity": now - timedelta(minutes=30),
                "is_active": False,
                "connection_status": "disconnected",
                "processed_chunks": 42,
                "total_processing_time_ms": 7829.3,
                "metadata": {"client_ip": "192.168.1.101", "user_agent": "Python Client"}
            },
            "ws_session_demo3": {
                "session_id": "ws_session_demo3",
                "created_at": now - timedelta(minutes=10),
                "last_activity": now - timedelta(minutes=1),
                "is_active": True,
                "connection_status": "connected",
                "processed_chunks": 3,
                "total_processing_time_ms": 456.7,
                "metadata": {"client_ip": "192.168.1.102", "user_agent": "Browser WebSocket"}
            }
        })
    
    return _mock_sessions


@router.get("/", response_model=SessionList)
async def list_sessions(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    active_only: bool = Query(False, description="Show only active sessions")
):
    """
    List all sessions with pagination.
    
    Args:
        page: Page number (starts at 1)
        per_page: Number of items per page (1-100)
        active_only: Filter to show only active sessions
        
    Returns:
        Paginated list of sessions
    """
    sessions_data = get_mock_session_data()
    
    # Filter sessions if requested
    if active_only:
        filtered_sessions = {k: v for k, v in sessions_data.items() if v["is_active"]}
    else:
        filtered_sessions = sessions_data
    
    # Convert to SessionInfo objects
    sessions = [SessionInfo(**data) for data in filtered_sessions.values()]
    
    # Apply pagination
    total_count = len(sessions)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_sessions = sessions[start_idx:end_idx]
    
    # Count active sessions
    active_count = sum(1 for s in sessions if s.is_active)
    
    return SessionList(
        sessions=paginated_sessions,
        total_count=total_count,
        active_count=active_count,
        page=page,
        per_page=per_page
    )


@router.get("/stats", response_model=SessionStats)
async def get_session_stats():
    """
    Get session statistics.
    
    Returns:
        Aggregated session statistics
    """
    sessions_data = get_mock_session_data()
    sessions = [SessionInfo(**data) for data in sessions_data.values()]
    
    total_sessions = len(sessions)
    active_sessions = sum(1 for s in sessions if s.is_active)
    completed_sessions = total_sessions - active_sessions
    
    # Calculate average session duration (mock calculation)
    total_chunks = sum(s.processed_chunks for s in sessions)
    total_processing_time = sum(s.total_processing_time_ms for s in sessions)
    
    avg_processing_time = total_processing_time / total_chunks if total_chunks > 0 else 0.0
    avg_session_duration = 3600.0  # Mock: 1 hour average
    
    return SessionStats(
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        completed_sessions=completed_sessions,
        average_session_duration_seconds=avg_session_duration,
        total_chunks_processed=total_chunks,
        average_processing_time_ms=avg_processing_time
    )


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """
    Get detailed information about a specific session.
    
    Args:
        session_id: The session ID to retrieve
        
    Returns:
        Detailed session information
        
    Raises:
        HTTPException: 404 if session not found
    """
    sessions_data = get_mock_session_data()
    
    if session_id not in sessions_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return SessionInfo(**sessions_data[session_id])


@router.delete("/{session_id}", response_model=SessionActionResponse)
async def terminate_session(session_id: str):
    """
    Terminate a specific session.
    
    Args:
        session_id: The session ID to terminate
        
    Returns:
        Operation result
        
    Raises:
        HTTPException: 404 if session not found, 400 if session already inactive
    """
    sessions_data = get_mock_session_data()
    
    if session_id not in sessions_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    session = sessions_data[session_id]
    
    if not session["is_active"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Session {session_id} is already inactive"
        )
    
    # Mock termination - in real implementation, this would call WebSocketHandler
    session["is_active"] = False
    session["connection_status"] = "terminated"
    session["last_activity"] = datetime.now(timezone.utc)
    
    return SessionActionResponse(
        success=True,
        message=f"Session {session_id} terminated successfully",
        session_id=session_id,
        timestamp=datetime.now(timezone.utc)
    )


@router.post("/{session_id}/ping", response_model=SessionActionResponse)
async def ping_session(session_id: str):
    """
    Send a ping to a specific session to test connectivity.
    
    Args:
        session_id: The session ID to ping
        
    Returns:
        Ping result
        
    Raises:
        HTTPException: 404 if session not found, 400 if session not active
    """
    sessions_data = get_mock_session_data()
    
    if session_id not in sessions_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    session = sessions_data[session_id]
    
    if not session["is_active"]:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_id} is not active"
        )
    
    # Mock ping - update last activity
    session["last_activity"] = datetime.now(timezone.utc)
    
    return SessionActionResponse(
        success=True,
        message=f"Session {session_id} ping successful",
        session_id=session_id, 
        timestamp=datetime.now(timezone.utc)
    )