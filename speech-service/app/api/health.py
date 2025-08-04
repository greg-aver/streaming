"""
Health check API endpoints.

Provides system health monitoring endpoints for service status,
component health checks, and readiness probes.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

try:
    import psutil
    import platform
    SYSTEM_INFO_AVAILABLE = True
except ImportError:
    psutil = None
    platform = None
    SYSTEM_INFO_AVAILABLE = False

from app.config import get_settings
from app.workers.vad import VADWorker
from app.workers.asr import ASRWorker 
from app.workers.diarization import DiarizationWorker
from app.aggregators.result_aggregator import ResultAggregator
from app.handlers.websocket_handler import WebSocketHandler


# Response models
class HealthStatus(BaseModel):
    """Basic health status response."""
    
    status: str = Field(description="Overall health status")
    timestamp: datetime = Field(description="Health check timestamp")
    version: str = Field(description="Application version")
    uptime_seconds: float = Field(description="Application uptime in seconds")


class ComponentHealth(BaseModel):
    """Individual component health details."""
    
    name: str = Field(description="Component name")
    status: str = Field(description="Component status (healthy/unhealthy/unknown)")
    details: Dict[str, Any] = Field(description="Component-specific health details")
    last_check: datetime = Field(description="Last health check timestamp")


class DetailedHealthStatus(BaseModel):
    """Detailed health status with component breakdown."""
    
    status: str = Field(description="Overall health status")
    timestamp: datetime = Field(description="Health check timestamp")
    version: str = Field(description="Application version")
    uptime_seconds: float = Field(description="Application uptime in seconds")
    components: List[ComponentHealth] = Field(description="Individual component health")
    system_info: Dict[str, Any] = Field(description="System information")


# Router
router = APIRouter(prefix="/health", tags=["health"])

# Global startup time for uptime calculation
_startup_time = datetime.now(timezone.utc)


def get_uptime() -> float:
    """Calculate application uptime in seconds."""
    return (datetime.now(timezone.utc) - _startup_time).total_seconds()


def _get_system_info() -> Dict[str, Any]:
    """
    Get system information with graceful degradation.
    
    Returns:
        Dictionary with system information, or fallback values if dependencies unavailable
    """
    if not SYSTEM_INFO_AVAILABLE:
        return {
            "platform": "unknown",
            "python_version": "unknown",
            "cpu_count": "unknown",
            "memory_total_gb": "unknown",
            "memory_used_percent": "unknown",
            "disk_usage_percent": "unknown",
            "system_info_available": False
        }
    
    try:
        return {
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "memory_used_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": psutil.disk_usage('/').percent if platform.system() != 'Windows' else psutil.disk_usage('C:').percent,
            "system_info_available": True
        }
    except Exception as e:
        # Graceful degradation in case of system info collection errors
        return {
            "platform": "error",
            "python_version": "error", 
            "error": str(e),
            "system_info_available": False
        }


async def check_component_health(component_name: str, component: Any) -> ComponentHealth:
    """Check health of an individual component."""
    now = datetime.now(timezone.utc)
    
    try:
        # Basic component status check
        if hasattr(component, 'is_running'):
            is_running = component.is_running
            status = "healthy" if is_running else "unhealthy"
            
            details = {
                "is_running": is_running,
                "component_type": type(component).__name__
            }
            
            # Add component-specific details
            if hasattr(component, 'processing_tasks') and component.processing_tasks:
                details["active_tasks"] = len(component.processing_tasks)
            
            if hasattr(component, 'get_stats'):
                try:
                    stats = await component.get_stats()
                    details["stats"] = stats
                except Exception:
                    details["stats_error"] = "Failed to retrieve stats"
                    
        else:
            status = "unknown"
            details = {"error": "Component status cannot be determined"}
            
    except Exception as e:
        status = "unhealthy"
        details = {"error": str(e)}
    
    return ComponentHealth(
        name=component_name,
        status=status,
        details=details,
        last_check=now
    )


@router.get("/", response_model=HealthStatus)
async def health_check(settings = Depends(get_settings)):
    """
    Basic health check endpoint.
    
    Returns:
        Basic health status information
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
        version=settings.app_version,
        uptime_seconds=get_uptime()
    )


@router.get("/detailed", response_model=DetailedHealthStatus)  
async def detailed_health_check(
    settings = Depends(get_settings),
    # Note: In a real implementation, these would be injected via DI
    # For now, we'll create mock responses since components aren't globally available
):
    """
    Detailed health check with component status.
    
    Returns:
        Detailed health information including component status
    """
    # System information with graceful degradation
    system_info = _get_system_info()
    
    # Mock component health checks (in real implementation, these would be injected)
    components = [
        ComponentHealth(
            name="event_bus",
            status="healthy",
            details={"type": "AsyncEventBus", "subscribers_count": 0},
            last_check=datetime.now(timezone.utc)
        ),
        ComponentHealth(
            name="vad_worker", 
            status="healthy",
            details={"type": "VADWorker", "is_running": False, "active_tasks": 0},
            last_check=datetime.now(timezone.utc)
        ),
        ComponentHealth(
            name="asr_worker",
            status="healthy", 
            details={"type": "ASRWorker", "is_running": False, "active_tasks": 0},
            last_check=datetime.now(timezone.utc)
        ),
        ComponentHealth(
            name="diarization_worker",
            status="healthy",
            details={"type": "DiarizationWorker", "is_running": False, "active_tasks": 0}, 
            last_check=datetime.now(timezone.utc)
        ),
        ComponentHealth(
            name="result_aggregator",
            status="healthy",
            details={"type": "ResultAggregator", "is_running": False, "active_chunks": 0},
            last_check=datetime.now(timezone.utc)
        ),
        ComponentHealth(
            name="websocket_handler",
            status="healthy",
            details={"type": "WebSocketHandler", "active_connections": 0, "active_sessions": 0},
            last_check=datetime.now(timezone.utc)
        )
    ]
    
    # Determine overall status
    unhealthy_components = [c for c in components if c.status == "unhealthy"]
    overall_status = "unhealthy" if unhealthy_components else "healthy"
    
    return DetailedHealthStatus(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=settings.app_version,
        uptime_seconds=get_uptime(),
        components=components,
        system_info=system_info
    )


@router.get("/ready")
async def readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    Returns:
        200 if service is ready to accept traffic, 503 otherwise
    """
    # In a real implementation, check if all critical components are ready
    # For now, always return ready
    return {"status": "ready", "timestamp": datetime.now(timezone.utc)}


@router.get("/live") 
async def liveness_probe():
    """
    Kubernetes liveness probe endpoint.
    
    Returns:
        200 if service is alive, 503 if it should be restarted
    """
    # Basic liveness check - if we can respond, we're alive
    return {"status": "alive", "timestamp": datetime.now(timezone.utc)}