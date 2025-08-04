"""
Statistics API endpoints.

Provides comprehensive system statistics including worker performance,
aggregator metrics, and overall system health metrics.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

from app.config import get_settings


# Response models
class WorkerStats(BaseModel):
    """Statistics for a specific worker type."""
    
    worker_type: str = Field(description="Type of worker (vad, asr, diarization)")
    is_running: bool = Field(description="Whether worker is currently running")
    active_tasks: int = Field(description="Number of currently active tasks")
    total_processed: int = Field(description="Total number of chunks processed")
    total_processing_time_ms: float = Field(description="Total processing time in milliseconds")
    average_processing_time_ms: float = Field(description="Average processing time per chunk")
    success_rate_percent: float = Field(description="Success rate as percentage")
    errors_count: int = Field(description="Total number of errors")
    last_activity: Optional[datetime] = Field(description="Last processing activity timestamp")


class AggregatorStats(BaseModel):
    """Statistics for the Result Aggregator."""
    
    is_running: bool = Field(description="Whether aggregator is currently running")
    active_chunks: int = Field(description="Number of chunks currently being aggregated")
    completed_chunks: int = Field(description="Total number of completed chunks")
    timeout_chunks: int = Field(description="Number of chunks that timed out")
    average_aggregation_time_ms: float = Field(description="Average time to complete aggregation")
    success_rate_percent: float = Field(description="Percentage of successfully completed chunks")
    component_completion_rates: Dict[str, float] = Field(description="Completion rates by component")


class SystemStats(BaseModel):
    """Overall system statistics."""
    
    uptime_seconds: float = Field(description="System uptime in seconds")
    total_sessions: int = Field(description="Total number of sessions created")
    active_sessions: int = Field(description="Number of currently active sessions")
    total_audio_chunks: int = Field(description="Total audio chunks processed")
    total_processing_time_ms: float = Field(description="Total processing time across all components")
    average_end_to_end_latency_ms: float = Field(description="Average end-to-end processing latency")
    throughput_chunks_per_minute: float = Field(description="Processing throughput in chunks per minute")
    memory_usage_mb: float = Field(description="Current memory usage in MB")
    cpu_usage_percent: float = Field(description="Current CPU usage percentage")


class PerformanceMetrics(BaseModel):
    """Performance metrics over time."""
    
    time_period: str = Field(description="Time period for metrics (last_hour, last_day, etc.)")
    data_points: List[Dict[str, Any]] = Field(description="Time-series data points")
    summary: Dict[str, Any] = Field(description="Summary statistics for the period")


class ComprehensiveStats(BaseModel):
    """Complete system statistics response."""
    
    timestamp: datetime = Field(description="Statistics collection timestamp")
    system: SystemStats = Field(description="Overall system statistics")
    workers: List[WorkerStats] = Field(description="Individual worker statistics")
    aggregator: AggregatorStats = Field(description="Result aggregator statistics")
    performance_trends: Dict[str, Any] = Field(description="Performance trend data")


# Router
router = APIRouter(prefix="/stats", tags=["statistics"])

# Mock data storage (in real implementation, this would be from actual components)
_startup_time = datetime.now(timezone.utc)


def get_uptime() -> float:
    """Calculate system uptime in seconds."""
    return (datetime.now(timezone.utc) - _startup_time).total_seconds()


def get_mock_worker_stats() -> List[WorkerStats]:
    """Generate mock worker statistics."""
    from datetime import timedelta
    
    now = datetime.now(timezone.utc)
    
    return [
        WorkerStats(
            worker_type="vad",
            is_running=True,
            active_tasks=2,
            total_processed=1247,
            total_processing_time_ms=15623.4,
            average_processing_time_ms=12.5,
            success_rate_percent=99.2,
            errors_count=10,
            last_activity=now - timedelta(seconds=5)
        ),
        WorkerStats(
            worker_type="asr", 
            is_running=True,
            active_tasks=3,
            total_processed=1189,
            total_processing_time_ms=47891.7,
            average_processing_time_ms=40.3,
            success_rate_percent=97.8,
            errors_count=26,
            last_activity=now - timedelta(seconds=2)
        ),
        WorkerStats(
            worker_type="diarization",
            is_running=True,
            active_tasks=1,
            total_processed=1156,
            total_processing_time_ms=89234.1,
            average_processing_time_ms=77.2,
            success_rate_percent=95.4,
            errors_count=53,
            last_activity=now - timedelta(seconds=8)
        )
    ]


def get_mock_aggregator_stats() -> AggregatorStats:
    """Generate mock aggregator statistics."""
    return AggregatorStats(
        is_running=True,
        active_chunks=4,
        completed_chunks=1134,
        timeout_chunks=22,
        average_aggregation_time_ms=145.7,
        success_rate_percent=98.1,
        component_completion_rates={
            "vad": 99.2,
            "asr": 97.8, 
            "diarization": 95.4
        }
    )


def get_mock_system_stats() -> SystemStats:
    """Generate mock system statistics."""
    # Get real system metrics where possible, with fallback
    if PSUTIL_AVAILABLE:
        try:
            memory_info = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)  # Non-blocking
            memory_usage_mb = memory_info.used / (1024 * 1024)
        except Exception:
            # Fallback to mock values if psutil fails
            memory_usage_mb = 2048.0  # 2GB mock
            cpu_percent = 45.0
    else:
        # Mock values when psutil not available
        memory_usage_mb = 2048.0  # 2GB mock
        cpu_percent = 45.0
    
    uptime = get_uptime()
    total_chunks = 1247  # From mock worker stats
    throughput = (total_chunks / (uptime / 60)) if uptime > 0 else 0
    
    return SystemStats(
        uptime_seconds=uptime,
        total_sessions=156,
        active_sessions=8,
        total_audio_chunks=total_chunks,
        total_processing_time_ms=152749.2,  # Sum from workers
        average_end_to_end_latency_ms=230.4,
        throughput_chunks_per_minute=throughput,
        memory_usage_mb=memory_usage_mb,
        cpu_usage_percent=cpu_percent
    )


@router.get("/", response_model=ComprehensiveStats)
async def get_comprehensive_stats():
    """
    Get comprehensive system statistics.
    
    Returns:
        Complete statistics for all system components
    """
    return ComprehensiveStats(
        timestamp=datetime.now(timezone.utc),
        system=get_mock_system_stats(),
        workers=get_mock_worker_stats(),
        aggregator=get_mock_aggregator_stats(),
        performance_trends={
            "last_hour_throughput": 45.2,
            "last_hour_error_rate": 2.1,
            "last_hour_avg_latency": 235.8
        }
    )


@router.get("/workers", response_model=List[WorkerStats])
async def get_workers_stats():
    """
    Get statistics for all workers.
    
    Returns:
        List of worker statistics
    """
    return get_mock_worker_stats()


@router.get("/workers/{worker_type}", response_model=WorkerStats)
async def get_worker_stats(worker_type: str):
    """
    Get statistics for a specific worker type.
    
    Args:
        worker_type: Type of worker (vad, asr, diarization)
        
    Returns:
        Statistics for the specified worker
        
    Raises:
        HTTPException: 404 if worker type not found
    """
    from fastapi import HTTPException
    
    workers = get_mock_worker_stats()
    worker_stats = next((w for w in workers if w.worker_type == worker_type), None)
    
    if not worker_stats:
        raise HTTPException(
            status_code=404, 
            detail=f"Worker type '{worker_type}' not found"
        )
    
    return worker_stats


@router.get("/aggregator", response_model=AggregatorStats)
async def get_aggregator_stats():
    """
    Get Result Aggregator statistics.
    
    Returns:
        Aggregator performance and status statistics
    """
    return get_mock_aggregator_stats()


@router.get("/system", response_model=SystemStats)
async def get_system_stats():
    """
    Get overall system statistics.
    
    Returns:
        System-wide performance and resource statistics
    """
    return get_mock_system_stats()


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    period: str = Query("last_hour", description="Time period (last_hour, last_day, last_week)")
):
    """
    Get performance metrics over time.
    
    Args:
        period: Time period for metrics collection
        
    Returns:
        Time-series performance data
    """
    now = datetime.now(timezone.utc)
    
    # Generate mock time-series data
    if period == "last_hour":
        # Generate hourly data points for last hour  
        data_points = []
        for i in range(60, 0, -5):  # Every 5 minutes for last hour
            timestamp = now - timedelta(minutes=i)
            data_points.append({
                "timestamp": timestamp,
                "throughput": 45.2 + (i * 0.1),  # Mock varying throughput
                "latency_ms": 230.4 + (i * 0.5),  # Mock varying latency
                "error_rate": max(0, 2.1 - (i * 0.02))  # Mock varying error rate
            })
    else:
        # Mock data for other periods
        data_points = [{
            "timestamp": now,
            "throughput": 45.2,
            "latency_ms": 230.4,
            "error_rate": 2.1
        }]
    
    return PerformanceMetrics(
        time_period=period,
        data_points=data_points,
        summary={
            "avg_throughput": 45.2,
            "avg_latency_ms": 230.4,
            "avg_error_rate": 2.1,
            "peak_throughput": 52.1,
            "min_latency_ms": 198.7,
            "data_points_count": len(data_points)
        }
    )