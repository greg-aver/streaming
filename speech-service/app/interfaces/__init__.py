"""
Interfaces package for speech-to-text service.

This package contains all abstract interfaces (protocols) used throughout
the application, following Clean Architecture and Dependency Inversion principles.
"""

from .events import (
    IEventBus,
    IEventSubscriber,
    IEventPublisher,
    Event,
    EventBusError,
    EventPublishError,
    EventSubscriptionError
)

from .services import (
    IVADService,
    IASRService,
    IDiarizationService,
    IWorker,
    IAggregator,
    IRepository,
    ServiceError,
    VADServiceError,
    ASRServiceError,
    DiarizationServiceError,
    WorkerError,
    AggregatorError
)

from .websocket import (
    IWebSocketHandler,
    IWebSocketManager,
    ISessionManager,
    WebSocketError,
    WebSocketHandlerError,
    WebSocketManagerError,
    SessionManagerError
)

__all__ = [
    # Event interfaces
    "IEventBus",
    "IEventSubscriber", 
    "IEventPublisher",
    "Event",
    "EventBusError",
    "EventPublishError",
    "EventSubscriptionError",
    
    # Service interfaces
    "IVADService",
    "IASRService",
    "IDiarizationService",
    "IWorker",
    "IAggregator",
    "IRepository",
    "ServiceError",
    "VADServiceError",
    "ASRServiceError",
    "DiarizationServiceError",
    "WorkerError",
    "AggregatorError",
    
    # WebSocket interfaces
    "IWebSocketHandler",
    "IWebSocketManager",
    "ISessionManager",
    "WebSocketError",
    "WebSocketHandlerError",
    "WebSocketManagerError",
    "SessionManagerError"
]