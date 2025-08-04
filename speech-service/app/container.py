"""
Dependency Injection container for the speech-to-text service.

This module configures and manages all application dependencies
using the dependency-injector framework, following Clean Architecture principles.
"""

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject
import structlog

from .config import Settings, get_settings 
from .events import AsyncEventBus
from .interfaces.events import IEventBus


class Container(containers.DeclarativeContainer):
    """
    Main dependency injection container.
    
    Configures and provides all application dependencies including
    services, repositories, workers, and infrastructure components.
    """
    
    # Configuration
    config = providers.Singleton(get_settings)
    
    # Logging setup
    logger = providers.Singleton(
        structlog.get_logger,
        "speech_service"
    )
    
    # Core Event System
    event_bus = providers.Singleton(
        AsyncEventBus
    )
    
    # Services - Real implementations
    vad_service = providers.Factory(
        "app.services.vad_service.MockVADService",
        config=config.provided.vad
    )
    
    asr_service = providers.Factory(
        "app.services.asr_service.FasterWhisperASRService", 
        config=config.provided.asr
    )
    
    diarization_service = providers.Factory(
        "app.services.diarization_service.MockDiarizationService",
        config=config.provided.diarization
    )
    
    # Workers - Event-driven processing components
    # Note: Используем string imports для lazy loading и избежания circular imports
    vad_worker = providers.Factory(
        "app.workers.vad.VADWorker",
        vad_service=vad_service,
        config=config.provided.processing
    )
    
    asr_worker = providers.Factory(
        "app.workers.asr.ASRWorker",
        asr_service=asr_service,
        config=config.provided.processing
    )
    
    diarization_worker = providers.Factory(
        "app.workers.diarization.DiarizationWorker",
        diarization_service=diarization_service,
        config=config.provided.processing
    )
    
    # Result Aggregator - объединяет результаты от всех workers
    result_aggregator = providers.Factory(
        "app.aggregators.result_aggregator.ResultAggregator",
        event_bus=event_bus,
        aggregation_timeout_seconds=config.provided.processing.chunk_timeout_seconds,
        cleanup_interval_seconds=1.0
    )
    
    # WebSocket components - real-time communication
    websocket_handler = providers.Factory(
        "app.handlers.websocket_handler.WebSocketHandler",
        event_bus=event_bus,
        max_audio_chunk_size=config.provided.websocket.max_message_size,
        session_timeout_minutes=30
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """
    Application-level container that includes additional wiring configuration.
    
    This container extends the base Container with application-specific
    configuration and wiring setup.
    """
    
    # Include the main container
    core = providers.DependenciesContainer()
    
    # Application lifecycle management
    @providers.Factory
    async def create_app():
        """Create and configure the FastAPI application."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        # Get configuration
        settings = get_settings()
        
        # Create FastAPI app
        app = FastAPI(
            title=settings.app_name,
            version=settings.app_version,
            debug=settings.debug
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=settings.cors_methods,
            allow_headers=settings.cors_headers,
        )
        
        return app
    
    @providers.Factory
    async def setup_logging():
        """Configure structured logging."""
        import logging.config
        
        settings = get_settings()
        log_config = settings.get_log_config()
        
        logging.config.dictConfig(log_config)
        
        logger = structlog.get_logger("startup")
        logger.info(
            "Logging configured",
            level=settings.logging.level,
            format=settings.logging.format
        )
        
        return logger


# Global container instance
container = Container()


def wire_container() -> None:
    """
    Wire the container with application modules.
    
    This function should be called during application startup
    to configure dependency injection across the application.
    """
    # Modules to wire for dependency injection
    modules_to_wire = [
        "app.main",
        "app.handlers.websocket_handler",
        "app.workers.vad",
        "app.workers.asr", 
        "app.workers.diarization",
        "app.services.vad_service",
        "app.services.asr_service",
        "app.services.diarization_service",
    ]
    
    # Wire the container
    container.wire(modules=modules_to_wire)
    
    logger = structlog.get_logger("container")
    logger.info(
        "Dependency injection container wired",
        modules=modules_to_wire
    )


def unwire_container() -> None:
    """
    Unwire the container.
    
    This function should be called during application shutdown
    for clean resource cleanup.
    """
    container.unwire()
    
    logger = structlog.get_logger("container")
    logger.info("Dependency injection container unwired")


async def initialize_services() -> None:
    """
    Initialize all services and workers with proper DI setup.
    
    Senior approach: Правильный порядок инициализации с обработкой ошибок
    и поддержкой new DI pattern с setter injection.
    """
    logger = structlog.get_logger("initialization")
    
    try:
        # Phase 1: Initialize core infrastructure
        event_bus = container.event_bus()
        logger.info("Event bus initialized")
        
        # Phase 2: Initialize services
        vad_service = container.vad_service()
        await vad_service.initialize()
        logger.info("VAD service initialized")
        
        asr_service = container.asr_service()
        await asr_service.initialize()
        logger.info("ASR service initialized")
        
        diarization_service = container.diarization_service()
        await diarization_service.initialize()
        logger.info("Diarization service initialized")
        
        # Phase 3: Create and configure workers
        # Senior pattern: two-phase initialization для новых DI workers
        vad_worker = container.vad_worker()
        vad_worker.set_event_bus(event_bus)  # Setter injection
        await vad_worker.start()
        logger.info("VAD worker started")
        
        # ASR worker with Clean DI (Phase 2 completed)
        asr_worker = container.asr_worker()
        asr_worker.set_event_bus(event_bus)  # Setter injection
        await asr_worker.start()
        logger.info("ASR worker started")
        
        # Diarization worker with Clean DI 
        diarization_worker = container.diarization_worker()
        diarization_worker.set_event_bus(event_bus)  # Setter injection
        await diarization_worker.start()
        logger.info("Diarization worker started")
        
        # Phase 4: Start aggregator (должен стартовать ПОСЛЕ workers)
        result_aggregator = container.result_aggregator()
        await result_aggregator.start()
        logger.info("Result aggregator started")
        
        # Phase 5: Start WebSocket handler (последний, так как принимает трафик)
        websocket_handler = container.websocket_handler()
        await websocket_handler.start()
        logger.info("WebSocket handler started")
        
        logger.info("All services initialized successfully - system ready to accept traffic")
        
    except Exception as e:
        logger.error("Failed to initialize services", error=str(e), exc_info=True)
        # При ошибке инициализации - попытаться cleanup что успели создать
        await cleanup_services()
        raise


async def cleanup_services() -> None:
    """
    Clean up all services and workers.
    
    This function should be called during application shutdown
    for graceful resource cleanup.
    
    Senior approach: Cleanup в обратном порядке с graceful degradation
    """
    logger = structlog.get_logger("cleanup")
    
    # Senior pattern: Cleanup в ОБРАТНОМ порядке от инициализации
    # Не падаем при ошибках cleanup - логируем и продолжаем
    
    # Phase 1: Stop WebSocket handler (перестаем принимать новый трафик)
    try:
        websocket_handler = container.websocket_handler()
        await websocket_handler.stop()
        logger.info("WebSocket handler stopped")
    except Exception as e:
        logger.warning("Error stopping WebSocket handler", error=str(e))
    
    # Phase 2: Stop aggregator (перестаем агрегировать результаты)
    try:
        result_aggregator = container.result_aggregator()
        await result_aggregator.stop()
        logger.info("Result aggregator stopped")
    except Exception as e:
        logger.warning("Error stopping result aggregator", error=str(e))
    
    # Phase 3: Stop workers (в обратном порядке)
    try:
        diarization_worker = container.diarization_worker()
        await diarization_worker.stop()
        logger.info("Diarization worker stopped")
    except Exception as e:
        logger.warning("Error stopping diarization worker", error=str(e))
    
    try:
        asr_worker = container.asr_worker()
        await asr_worker.stop()
        logger.info("ASR worker stopped")
    except Exception as e:
        logger.warning("Error stopping ASR worker", error=str(e))
    
    try:
        vad_worker = container.vad_worker()
        await vad_worker.stop()
        logger.info("VAD worker stopped")
    except Exception as e:
        logger.warning("Error stopping VAD worker", error=str(e))
    
    # Phase 4: Cleanup services
    try:
        diarization_service = container.diarization_service()
        await diarization_service.cleanup()
        logger.info("Diarization service cleaned up")
    except Exception as e:
        logger.warning("Error cleaning up diarization service", error=str(e))
    
    try:
        asr_service = container.asr_service()
        await asr_service.cleanup()
        logger.info("ASR service cleaned up")
    except Exception as e:
        logger.warning("Error cleaning up ASR service", error=str(e))
    
    try:
        vad_service = container.vad_service()
        await vad_service.cleanup()
        logger.info("VAD service cleaned up")
    except Exception as e:
        logger.warning("Error cleaning up VAD service", error=str(e))
    
    logger.info("All services cleanup completed (with graceful error handling)")


# Dependency injection decorators and utilities
def get_event_bus() -> IEventBus:
    """Get event bus instance from container."""
    return container.event_bus()


def get_config() -> Settings:
    """Get configuration from container."""
    return container.config()


# Context manager for application lifecycle
class ServiceLifecycleManager:
    """
    Context manager for managing service lifecycle.
    
    Handles initialization and cleanup of all application services
    with proper error handling and logging.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    async def __aenter__(self):
        """Initialize all services."""
        self.logger.info("Starting service initialization")
        
        # Wire container
        wire_container()
        
        # Initialize services
        await initialize_services()
        
        self.logger.info("Service initialization completed")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up all services."""
        self.logger.info("Starting service cleanup")
        
        # Clean up services
        await cleanup_services()
        
        # Unwire container
        unwire_container()
        
        if exc_type:
            self.logger.error(
                "Service cleanup completed with errors",
                exc_type=str(exc_type),
                exc_val=str(exc_val)
            )
        else:
            self.logger.info("Service cleanup completed successfully")


# Factory functions for testing
def create_test_container() -> Container:
    """
    Create a container configured for testing.
    
    Returns:
        Container instance with test configuration
    """
    test_container = Container()
    
    # Override with test configuration
    test_settings = Settings(
        debug=True,
        logging={"level": "DEBUG"},
        processing={"max_concurrent_workers": 1}
    )
    test_container.config.override(test_settings)
    
    return test_container


def create_mock_container() -> Container:
    """
    Create a container with mocked dependencies for testing.
    
    Returns:
        Container instance with mocked services
    """
    from unittest.mock import AsyncMock, Mock
    
    mock_container = Container()
    
    # Mock event bus
    mock_event_bus = AsyncMock(spec=IEventBus)
    mock_container.event_bus.override(mock_event_bus)
    
    return mock_container