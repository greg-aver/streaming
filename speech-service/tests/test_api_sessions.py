"""
Tests for session management API endpoints.

Tests all session-related endpoints including listing sessions,
getting session details, and session lifecycle management.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestSessionsAPI:
    """Test suite for session management API endpoints."""
    
    def test_list_sessions_default(self, client):
        """Test listing sessions with default parameters."""
        response = client.get("/sessions/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "sessions" in data
        assert "total_count" in data
        assert "active_count" in data
        assert "page" in data
        assert "per_page" in data
        
        # Verify pagination defaults
        assert data["page"] == 1
        assert data["per_page"] == 10
        
        # Verify sessions structure
        sessions = data["sessions"]
        assert isinstance(sessions, list)
        assert data["total_count"] >= len(sessions)
        
        # Verify session structure if any sessions exist
        if sessions:
            session = sessions[0]
            assert "session_id" in session
            assert "created_at" in session
            assert "last_activity" in session
            assert "is_active" in session
            assert "connection_status" in session
            assert "processed_chunks" in session
            assert "total_processing_time_ms" in session
            assert "metadata" in session
    
    def test_list_sessions_with_pagination(self, client):
        """Test session listing with custom pagination."""
        response = client.get("/sessions/?page=1&per_page=2")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert len(data["sessions"]) <= 2
    
    def test_list_sessions_active_only(self, client):
        """Test filtering sessions to show only active ones."""
        response = client.get("/sessions/?active_only=true")
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned sessions should be active
        sessions = data["sessions"]
        for session in sessions:
            assert session["is_active"] is True
    
    def test_list_sessions_pagination_validation(self, client):
        """Test pagination parameter validation."""
        # Test invalid page number
        response = client.get("/sessions/?page=0")
        assert response.status_code == 422  # Validation error
        
        # Test invalid per_page number
        response = client.get("/sessions/?per_page=101")
        assert response.status_code == 422  # Validation error
    
    def test_get_session_stats(self, client):
        """Test getting session statistics."""
        response = client.get("/sessions/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "total_sessions" in data
        assert "active_sessions" in data
        assert "completed_sessions" in data
        assert "average_session_duration_seconds" in data
        assert "total_chunks_processed" in data
        assert "average_processing_time_ms" in data
        
        # Verify data types and logical relationships
        assert isinstance(data["total_sessions"], int)
        assert isinstance(data["active_sessions"], int)
        assert isinstance(data["completed_sessions"], int)
        assert data["total_sessions"] >= 0
        assert data["active_sessions"] >= 0
        assert data["completed_sessions"] >= 0
        assert data["total_sessions"] == data["active_sessions"] + data["completed_sessions"]
    
    def test_get_existing_session(self, client):
        """Test getting details for an existing session."""
        # First, get list of sessions to find a valid session ID
        response = client.get("/sessions/")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        if not sessions:
            pytest.skip("No sessions available for testing")
        
        session_id = sessions[0]["session_id"]
        
        # Get specific session details
        response = client.get(f"/sessions/{session_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["session_id"] == session_id
        assert "created_at" in data
        assert "last_activity" in data
        assert "is_active" in data
        assert "connection_status" in data
        assert "processed_chunks" in data
        assert "total_processing_time_ms" in data
        assert "metadata" in data
    
    def test_get_nonexistent_session(self, client):
        """Test getting details for a non-existent session."""
        response = client.get("/sessions/nonexistent_session_id")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    def test_terminate_existing_active_session(self, client):
        """Test terminating an existing active session."""
        # First, get list of active sessions
        response = client.get("/sessions/?active_only=true")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        if not sessions:
            pytest.skip("No active sessions available for testing")
        
        session_id = sessions[0]["session_id"]
        
        # Terminate the session
        response = client.delete(f"/sessions/{session_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["session_id"] == session_id
        assert "terminated successfully" in data["message"]
        assert "timestamp" in data
    
    def test_terminate_nonexistent_session(self, client):
        """Test terminating a non-existent session."""
        response = client.delete("/sessions/nonexistent_session_id")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    def test_terminate_inactive_session(self, client):
        """Test terminating an already inactive session."""
        # First, get list of all sessions to find an inactive one
        response = client.get("/sessions/")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        inactive_sessions = [s for s in sessions if not s["is_active"]]
        
        if not inactive_sessions:
            pytest.skip("No inactive sessions available for testing")
        
        session_id = inactive_sessions[0]["session_id"]
        
        # Try to terminate inactive session
        response = client.delete(f"/sessions/{session_id}")
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        assert "already inactive" in data["detail"].lower()
    
    def test_ping_existing_active_session(self, client):
        """Test ping for an existing active session."""
        # First, get list of active sessions
        response = client.get("/sessions/?active_only=true")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        if not sessions:
            pytest.skip("No active sessions available for testing")
        
        session_id = sessions[0]["session_id"]
        
        # Ping the session
        response = client.post(f"/sessions/{session_id}/ping")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["session_id"] == session_id
        assert "ping successful" in data["message"]
        assert "timestamp" in data
    
    def test_ping_nonexistent_session(self, client):
        """Test ping for a non-existent session."""
        response = client.post("/sessions/nonexistent_session_id/ping")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    def test_ping_inactive_session(self, client):
        """Test ping for an inactive session."""
        # First, get list of all sessions to find an inactive one
        response = client.get("/sessions/")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        inactive_sessions = [s for s in sessions if not s["is_active"]]
        
        if not inactive_sessions:
            pytest.skip("No inactive sessions available for testing")
        
        session_id = inactive_sessions[0]["session_id"]
        
        # Try to ping inactive session
        response = client.post(f"/sessions/{session_id}/ping")
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        assert "not active" in data["detail"].lower()
    
    def test_session_timestamps_format(self, client):
        """Test that session timestamps are in correct ISO format."""
        response = client.get("/sessions/")
        assert response.status_code == 200
        
        sessions = response.json()["sessions"]
        if not sessions:
            pytest.skip("No sessions available for testing")
        
        session = sessions[0]
        
        # Verify timestamp formats
        created_at = datetime.fromisoformat(session["created_at"].replace('Z', '+00:00'))
        last_activity = datetime.fromisoformat(session["last_activity"].replace('Z', '+00:00'))
        
        assert isinstance(created_at, datetime)
        assert isinstance(last_activity, datetime)
        assert last_activity >= created_at