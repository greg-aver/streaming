"""
Tests for statistics API endpoints.

Tests all statistics-related endpoints including system stats,
worker statistics, aggregator metrics, and performance data.
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


class TestStatsAPI:
    """Test suite for statistics API endpoints."""
    
    def test_get_comprehensive_stats(self, client):
        """Test getting comprehensive system statistics."""
        response = client.get("/stats/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "timestamp" in data
        assert "system" in data
        assert "workers" in data
        assert "aggregator" in data
        assert "performance_trends" in data
        
        # Verify timestamp
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)
        
        # Verify system stats structure
        system = data["system"]
        assert "uptime_seconds" in system
        assert "total_sessions" in system
        assert "active_sessions" in system
        assert "total_audio_chunks" in system
        assert "throughput_chunks_per_minute" in system
        assert "memory_usage_mb" in system
        assert "cpu_usage_percent" in system
        
        # Verify workers structure
        workers = data["workers"]
        assert isinstance(workers, list)
        assert len(workers) == 3  # VAD, ASR, Diarization
        
        worker_types = {w["worker_type"] for w in workers}
        assert worker_types == {"vad", "asr", "diarization"}
        
        # Verify aggregator structure
        aggregator = data["aggregator"]
        assert "is_running" in aggregator
        assert "active_chunks" in aggregator
        assert "completed_chunks" in aggregator
        assert "success_rate_percent" in aggregator
    
    def test_get_workers_stats(self, client):
        """Test getting statistics for all workers."""
        response = client.get("/stats/workers")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 3  # VAD, ASR, Diarization
        
        # Verify each worker has required fields
        for worker in data:
            assert "worker_type" in worker
            assert "is_running" in worker
            assert "active_tasks" in worker
            assert "total_processed" in worker
            assert "total_processing_time_ms" in worker
            assert "average_processing_time_ms" in worker
            assert "success_rate_percent" in worker
            assert "errors_count" in worker
            
            # Verify data types and ranges
            assert isinstance(worker["worker_type"], str)
            assert isinstance(worker["is_running"], bool)
            assert isinstance(worker["active_tasks"], int)
            assert worker["active_tasks"] >= 0
            assert worker["success_rate_percent"] >= 0
            assert worker["success_rate_percent"] <= 100
    
    def test_get_specific_worker_stats(self, client):
        """Test getting statistics for a specific worker type."""
        # Test each worker type
        worker_types = ["vad", "asr", "diarization"]
        
        for worker_type in worker_types:
            response = client.get(f"/stats/workers/{worker_type}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["worker_type"] == worker_type
            assert "is_running" in data
            assert "total_processed" in data
            assert "average_processing_time_ms" in data
            assert "success_rate_percent" in data
    
    def test_get_invalid_worker_stats(self, client):
        """Test getting statistics for invalid worker type."""
        response = client.get("/stats/workers/invalid_worker")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    def test_get_aggregator_stats(self, client):
        """Test getting Result Aggregator statistics."""
        response = client.get("/stats/aggregator")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "is_running" in data
        assert "active_chunks" in data
        assert "completed_chunks" in data
        assert "timeout_chunks" in data
        assert "average_aggregation_time_ms" in data
        assert "success_rate_percent" in data
        assert "component_completion_rates" in data
        
        # Verify component completion rates
        completion_rates = data["component_completion_rates"]
        assert "vad" in completion_rates
        assert "asr" in completion_rates
        assert "diarization" in completion_rates
        
        # Verify completion rates are percentages
        for rate in completion_rates.values():
            assert 0 <= rate <= 100
    
    @patch('app.api.stats.psutil')
    @patch('app.api.stats.PSUTIL_AVAILABLE', True)
    def test_get_system_stats(self, mock_psutil, client):
        """Test getting overall system statistics."""
        # Mock psutil responses
        mock_psutil.virtual_memory.return_value = MagicMock(used=8 * 1024**3)  # 8GB
        mock_psutil.cpu_percent.return_value = 45.7
        
        response = client.get("/stats/system")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "uptime_seconds" in data
        assert "total_sessions" in data
        assert "active_sessions" in data
        assert "total_audio_chunks" in data
        assert "total_processing_time_ms" in data
        assert "average_end_to_end_latency_ms" in data
        assert "throughput_chunks_per_minute" in data
        assert "memory_usage_mb" in data
        assert "cpu_usage_percent" in data
        
        # Verify data types and ranges
        assert data["uptime_seconds"] >= 0
        assert data["total_sessions"] >= 0
        assert data["active_sessions"] >= 0
        assert data["memory_usage_mb"] > 0  # Should have some memory usage
        assert 0 <= data["cpu_usage_percent"] <= 100
    
    def test_get_performance_metrics_default(self, client):
        """Test getting performance metrics with default period."""
        response = client.get("/stats/performance")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "time_period" in data
        assert "data_points" in data
        assert "summary" in data
        
        # Verify default period
        assert data["time_period"] == "last_hour"
        
        # Verify data points structure
        data_points = data["data_points"]
        assert isinstance(data_points, list)
        assert len(data_points) > 0
        
        # Verify each data point has required fields
        for point in data_points:
            assert "timestamp" in point
            assert "throughput" in point
            assert "latency_ms" in point
            assert "error_rate" in point
        
        # Verify summary structure
        summary = data["summary"]
        assert "avg_throughput" in summary
        assert "avg_latency_ms" in summary
        assert "avg_error_rate" in summary
        assert "data_points_count" in summary
        assert summary["data_points_count"] == len(data_points)
    
    def test_get_performance_metrics_custom_period(self, client):
        """Test getting performance metrics with custom time period."""
        response = client.get("/stats/performance?period=last_day")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["time_period"] == "last_day"
        assert "data_points" in data
        assert "summary" in data
    
    def test_worker_stats_logical_consistency(self, client):
        """Test that worker statistics are logically consistent."""
        response = client.get("/stats/workers")
        assert response.status_code == 200
        
        workers = response.json()
        
        for worker in workers:
            # Average processing time should be reasonable
            if worker["total_processed"] > 0:
                expected_avg = worker["total_processing_time_ms"] / worker["total_processed"]
                actual_avg = worker["average_processing_time_ms"]
                assert abs(expected_avg - actual_avg) < 0.1  # Allow small floating point differences
            
            # Success rate should be reasonable
            assert 0 <= worker["success_rate_percent"] <= 100
            
            # Active tasks should not exceed total processed (for mock data)
            assert worker["active_tasks"] >= 0
    
    def test_system_stats_relationships(self, client):
        """Test logical relationships in system statistics."""
        response = client.get("/stats/system")
        assert response.status_code == 200
        
        data = response.json()
        
        # Active sessions should not exceed total sessions
        assert data["active_sessions"] <= data["total_sessions"]
        
        # All numeric fields should be non-negative
        numeric_fields = [
            "uptime_seconds", "total_sessions", "active_sessions",
            "total_audio_chunks", "total_processing_time_ms",
            "average_end_to_end_latency_ms", "throughput_chunks_per_minute",
            "memory_usage_mb"
        ]
        
        for field in numeric_fields:
            assert data[field] >= 0, f"Field {field} should be non-negative"
    
    def test_performance_metrics_time_ordering(self, client):
        """Test that performance metrics data points are properly time-ordered."""
        response = client.get("/stats/performance?period=last_hour")
        assert response.status_code == 200
        
        data = response.json()
        data_points = data["data_points"]
        
        if len(data_points) > 1:
            # Verify timestamps are in ascending order
            timestamps = [
                datetime.fromisoformat(point["timestamp"].replace('Z', '+00:00'))
                for point in data_points
            ]
            
            for i in range(1, len(timestamps)):
                assert timestamps[i] >= timestamps[i-1], "Timestamps should be in ascending order"