"""
Main FastAPI application for the Speech-to-Text service.

This module creates and configures the FastAPI application with all
API routers, middleware, and WebSocket endpoints.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api import health, sessions, stats
from app.handlers.websocket_handler import WebSocketHandler
from app.events import AsyncEventBus
from app.container import ServiceLifecycleManager


# Global components managed by DI container
lifecycle_manager = None
websocket_handler = None

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events for the FastAPI application.
    """
    # Startup
    logger.info("Starting Speech-to-Text service...")
    
    global websocket_handler
    settings = get_settings()
    
    # Initialize WebSocket handler (in real implementation, this would be via DI)
    websocket_handler = WebSocketHandler(
        event_bus=event_bus,
        max_audio_chunk_size=settings.websocket.max_message_size,
        session_timeout_minutes=30
    )
    
    # Start WebSocket handler
    await websocket_handler.start()
    logger.info("WebSocket handler started")
    
    # TODO: Start other components (workers, aggregator) when DI is implemented
    
    logger.info("Speech-to-Text service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Speech-to-Text service...")
    
    if websocket_handler:
        await websocket_handler.stop()
        logger.info("WebSocket handler stopped")
    
    # TODO: Stop other components
    
    logger.info("Speech-to-Text service shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()
    
    # Create FastAPI app with lifespan manager
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Real-time Speech-to-Text service with WebSocket support",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )
    
    # Include API routers
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(stats.router)
    
    return app


# Create the FastAPI app
app = create_app()


@app.get("/")
async def root():
    """
    Root endpoint with service information.
    
    Returns:
        Basic service information
    """
    settings = get_settings()
    
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "description": "Real-time Speech-to-Text service",
        "docs_url": "/docs",
        "health_check": "/health",
        "websocket_endpoint": "/ws"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for real-time audio processing.
    
    Args:
        websocket: WebSocket connection
    """
    global websocket_handler
    
    if not websocket_handler:
        await websocket.close(code=1003, reason="Service not ready")
        return
    
    session_id = None
    
    try:
        # Accept WebSocket connection
        await websocket.accept()
        logger.info("WebSocket connection accepted")
        
        # Create session
        session_id = await websocket_handler.session_manager.create_session()
        await websocket_handler.websocket_manager.add_connection(session_id, websocket)
        
        logger.info(f"Session created: {session_id}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "session_created",
            "session_id": session_id,
            "message": "Session created successfully"
        })
        
        # Handle WebSocket messages
        while True:
            # Receive message
            message = await websocket.receive()
            
            if message["type"] == "websocket.receive":
                if "bytes" in message:
                    # Handle audio data
                    audio_data = message["bytes"]
                    await websocket_handler.handle_audio_data(websocket, audio_data, session_id)
                    
                elif "text" in message:
                    # Handle text commands (future extensibility)
                    await websocket.send_json({
                        "type": "info",
                        "message": "Text commands not yet implemented"
                    })
            
            elif message["type"] == "websocket.disconnect":
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
        
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await websocket.close(code=1011, reason=f"Internal error: {str(e)}")
        
    finally:
        # Clean up session
        if session_id and websocket_handler:
            try:
                await websocket_handler.websocket_manager.remove_connection(session_id)
                await websocket_handler.session_manager.end_session(session_id)
                logger.info(f"Session cleaned up: {session_id}")
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unhandled errors.
    
    Args:
        request: The request that caused the exception
        exc: The exception that was raised
        
    Returns:
        JSON error response
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "type": type(exc).__name__
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.logging.level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.logging.level.lower()
    )