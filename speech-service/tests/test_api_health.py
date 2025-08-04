"""
Tests for health check API endpoints.

Tests all health-related endpoints including basic health check,
detailed health status, and Kubernetes probes.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import create_app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestHealthAPI:
    """Test suite for health check API endpoints."""
    
    def test_basic_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "uptime_seconds" in data
        
        # Verify values
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert data["uptime_seconds"] >= 0
        
        # Verify timestamp format
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)
    
    @patch('app.api.health.psutil')
    @patch('app.api.health.platform')
    @patch('app.api.health.SYSTEM_INFO_AVAILABLE', True)
    def test_detailed_health_check(self, mock_platform, mock_psutil, client):
        """Test detailed health check with system information."""
        # Mock platform responses
        mock_platform.system.return_value = "Linux"
        mock_platform.python_version.return_value = "3.8.10"
        
        # Mock psutil responses
        mock_psutil.cpu_count.return_value = 8
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=16 * 1024**3,  # 16GB
            percent=45.2
        )
        mock_psutil.disk_usage.return_value = MagicMock(percent=67.8)
        
        response = client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "components" in data
        assert "system_info" in data
        
        # Verify overall status
        assert data["status"] == "healthy"
        
        # Verify components
        components = data["components"]
        assert len(components) == 6  # All components
        
        component_names = {c["name"] for c in components}
        expected_components = {
            "event_bus", "vad_worker", "asr_worker", 
            "diarization_worker", "result_aggregator", "websocket_handler"
        }
        assert component_names == expected_components
        
        # Verify component structure
        for component in components:
            assert "name" in component
            assert "status" in component
            assert "details" in component
            assert "last_check" in component
            assert component["status"] == "healthy"
        
        # Verify system info
        system_info = data["system_info"]
        assert "cpu_count" in system_info
        assert "memory_total_gb" in system_info
        assert "memory_used_percent" in system_info
        assert "platform" in system_info
        assert "python_version" in system_info
        assert system_info["cpu_count"] == 8
        assert system_info["memory_used_percent"] == 45.2
        assert system_info["platform"] == "Linux"
        assert system_info["python_version"] == "3.8.10"
    
    def test_readiness_probe(self, client):
        """Test Kubernetes readiness probe."""
        response = client.get("/health/ready")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] == "ready"
    
    def test_liveness_probe(self, client):
        """Test Kubernetes liveness probe."""
        response = client.get("/health/live")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] == "alive"
    
    def test_health_check_timestamps_are_recent(self, client):
        """Test that health check timestamps are recent."""
        from datetime import timezone
        
        # Use UTC time for proper comparison
        before = datetime.now(timezone.utc)
        
        response = client.get("/health/")
        assert response.status_code == 200
        
        after = datetime.now(timezone.utc)
        data = response.json()
        
        # Parse UTC timestamp
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        
        # Compare UTC times
        assert before <= timestamp <= after, f"Timestamp {timestamp} not between {before} and {after}"
    
    def test_health_check_uptime_increases(self, client):
        """Test that uptime increases between calls."""
        import time
        
        # First call
        response1 = client.get("/health/")
        assert response1.status_code == 200
        uptime1 = response1.json()["uptime_seconds"]
        
        # Wait a bit
        time.sleep(0.1)
        
        # Second call
        response2 = client.get("/health/")
        assert response2.status_code == 200
        uptime2 = response2.json()["uptime_seconds"]
        
        # Uptime should have increased
        assert uptime2 > uptime1
    
    @patch('app.api.health.platform')
    @patch('app.api.health.psutil')
    @patch('app.api.health.SYSTEM_INFO_AVAILABLE', True)
    def test_detailed_health_platform_info(self, mock_psutil, mock_platform, client):
        """Test platform-specific information in detailed health check."""
        mock_platform.system.return_value = "Linux"
        mock_platform.python_version.return_value = "3.8.10"
        
        # Mock required psutil methods
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=8 * 1024**3,
            percent=60.0
        )
        mock_psutil.disk_usage.return_value = MagicMock(percent=70.0)
        
        response = client.get("/health/detailed")
        assert response.status_code == 200
        
        data = response.json()
        system_info = data["system_info"]
        
        assert system_info["platform"] == "Linux"
        assert system_info["python_version"] == "3.8.10"