"""
Event bus implementation for the speech-to-text service.

This module provides a concrete implementation of the event-driven architecture,
following Clean Architecture principles with async/await support.
"""

import asyncio
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from datetime import datetime
import structlog
from collections import defaultdict

from .interfaces.events import (
    IEventBus, 
    IEventSubscriber, 
    IEventPublisher,
    Event, 
    EventBusError, 
    EventPublishError, 
    EventSubscriptionError
)

logger = structlog.get_logger(__name__)


class AsyncEventBus(IEventBus):
    """
    Async implementation of the event bus interface.
    
    Provides in-memory event publishing and subscription system
    with async/await support and structured logging.
    """
    
    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        self._event_history: List[Event] = []
        self._max_history_size: int = 1000
        self._lock = asyncio.Lock()
        
        logger.info("EventBus initialized")
    
    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event: Event instance to publish
            
        Raises:
            EventPublishError: If publishing fails
        """
        try:
            async with self._lock:
                # Add to event history
                self._event_history.append(event)
                if len(self._event_history) > self._max_history_size:
                    self._event_history.pop(0)
                
                # Get subscribers for this event type
                subscribers = self._subscribers.get(event.name, set()).copy()
            
            if not subscribers:
                logger.debug(
                    "No subscribers for event",
                    event_name=event.name,
                    correlation_id=event.correlation_id
                )
                return
            
            logger.info(
                "Publishing event",
                event_name=event.name,
                source=event.source,
                correlation_id=event.correlation_id,
                subscriber_count=len(subscribers)
            )
            
            # Execute all handlers concurrently
            tasks = []
            for handler in subscribers:
                try:
                    task = asyncio.create_task(
                        self._safe_handler_call(handler, event)
                    )
                    tasks.append(task)
                except Exception as e:
                    logger.error(
                        "Error creating handler task",
                        event_name=event.name,
                        handler=str(handler),
                        error=str(e),
                        correlation_id=event.correlation_id
                    )
            
            if tasks:
                # Wait for all handlers to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log any handler errors
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(
                            "Event handler failed",
                            event_name=event.name,
                            handler_index=i,
                            error=str(result),
                            correlation_id=event.correlation_id
                        )
            
            logger.debug(
                "Event published successfully",
                event_name=event.name,
                correlation_id=event.correlation_id
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish event",
                event_name=event.name,
                error=str(e),
                correlation_id=getattr(event, 'correlation_id', None)
            )
            raise EventPublishError(f"Failed to publish event {event.name}: {e}")
    
    async def _safe_handler_call(
        self, 
        handler: Callable, 
        event: Event
    ) -> None:
        """
        Safely call an event handler with error handling.
        
        Args:
            handler: Handler function to call
            event: Event to pass to handler
        """
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                # Run sync handler in thread pool
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler, event)
        except Exception as e:
            logger.error(
                "Event handler exception",
                handler=str(handler),
                event_name=event.name,
                error=str(e),
                correlation_id=event.correlation_id
            )
            # Don't re-raise - we want to continue with other handlers
    
    async def subscribe(
        self, 
        event_name: str, 
        handler: Callable[[Event], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Subscribe to events of a specific type.
        
        Args:
            event_name: Name of the event type to subscribe to
            handler: Async function to handle the event
            
        Raises:
            EventSubscriptionError: If subscription fails
        """
        try:
            async with self._lock:
                self._subscribers[event_name].add(handler)
            
            logger.info(
                "Handler subscribed to event",
                event_name=event_name,
                handler=str(handler),
                total_subscribers=len(self._subscribers[event_name])
            )
            
        except Exception as e:
            logger.error(
                "Failed to subscribe to event",
                event_name=event_name,
                handler=str(handler),
                error=str(e)
            )
            raise EventSubscriptionError(
                f"Failed to subscribe to {event_name}: {e}"
            )
    
    async def unsubscribe(
        self, 
        event_name: str, 
        handler: Callable[[Event], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Unsubscribe from events of a specific type.
        
        Args:
            event_name: Name of the event type to unsubscribe from
            handler: Handler function to remove
            
        Raises:
            EventSubscriptionError: If unsubscription fails
        """
        try:
            async with self._lock:
                if event_name in self._subscribers:
                    self._subscribers[event_name].discard(handler)
                    
                    # Clean up empty subscriber sets
                    if not self._subscribers[event_name]:
                        del self._subscribers[event_name]
            
            logger.info(
                "Handler unsubscribed from event",
                event_name=event_name,
                handler=str(handler)
            )
            
        except Exception as e:
            logger.error(
                "Failed to unsubscribe from event",
                event_name=event_name,
                handler=str(handler),
                error=str(e)
            )
            raise EventSubscriptionError(
                f"Failed to unsubscribe from {event_name}: {e}"
            )
    
    async def get_subscribers(self, event_name: str) -> List[Callable]:
        """
        Get all subscribers for a specific event type.
        
        Args:
            event_name: Name of the event type
            
        Returns:
            List of subscriber handler functions
        """
        async with self._lock:
            return list(self._subscribers.get(event_name, set()))
    
    async def clear_subscribers(self, event_name: Optional[str] = None) -> None:
        """
        Clear subscribers for specific event type or all events.
        
        Args:
            event_name: Event type to clear, or None for all events
        """
        async with self._lock:
            if event_name:
                if event_name in self._subscribers:
                    del self._subscribers[event_name]
                    logger.info("Cleared subscribers for event", event_name=event_name)
            else:
                self._subscribers.clear()
                logger.info("Cleared all event subscribers")
    
    async def get_event_history(
        self, 
        event_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        Get recent event history.
        
        Args:
            event_name: Filter by event name, or None for all events
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        async with self._lock:
            events = self._event_history
            
            if event_name:
                events = [e for e in events if e.name == event_name]
            
            return events[-limit:] if events else []
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get event bus statistics.
        
        Returns:
            Dictionary with event bus metrics
        """
        async with self._lock:
            total_subscribers = sum(
                len(handlers) for handlers in self._subscribers.values()
            )
            
            event_counts = defaultdict(int)
            for event in self._event_history:
                event_counts[event.name] += 1
            
            return {
                "total_event_types": len(self._subscribers),
                "total_subscribers": total_subscribers,
                "event_history_size": len(self._event_history),
                "event_counts": dict(event_counts),
                "subscriber_breakdown": {
                    name: len(handlers) 
                    for name, handlers in self._subscribers.items()
                }
            }


class EventPublisherMixin(IEventPublisher):
    """
    Mixin class for components that need to publish events.
    
    Provides a convenient interface for publishing events
    with automatic source attribution and correlation ID handling.
    """
    
    def __init__(self, event_bus: IEventBus, source_name: str):
        """
        Initialize the event publisher.
        
        Args:
            event_bus: Event bus instance to publish to
            source_name: Name to use as event source
        """
        self._event_bus = event_bus
        self._source_name = source_name
        self._logger = structlog.get_logger(self.__class__.__name__)
    
    async def publish_event(
        self, 
        event_name: str, 
        data: Any, 
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Publish an event with the given data.
        
        Args:
            event_name: Name/type of the event
            data: Event payload data
            correlation_id: Optional correlation ID for tracking
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        
        event = Event(
            name=event_name,
            data=data,
            source=self._source_name,
            correlation_id=correlation_id
        )
        
        self._logger.debug(
            "Publishing event",
            event_name=event_name,
            correlation_id=correlation_id
        )
        
        await self._event_bus.publish(event)


class EventSubscriberMixin(IEventSubscriber):
    """
    Mixin class for components that need to subscribe to events.
    
    Provides a convenient interface for setting up event subscriptions
    with automatic handler registration.
    """
    
    def __init__(self, event_bus: IEventBus):
        """
        Initialize the event subscriber.
        
        Args:
            event_bus: Event bus instance to subscribe to
        """
        self._event_bus = event_bus
        self._logger = structlog.get_logger(self.__class__.__name__)
        self._subscriptions: Dict[str, Callable] = {}
    
    async def setup_subscriptions(self, event_bus: IEventBus) -> None:
        """
        Set up event subscriptions for this component.
        
        This method should be overridden by subclasses to define
        their specific event subscriptions.
        
        Args:
            event_bus: Event bus instance to subscribe to
        """
        pass
    
    async def handle_event(self, event: Event) -> None:
        """
        Handle an incoming event.
        
        This method should be overridden by subclasses to define
        their specific event handling logic.
        
        Args:
            event: Event to handle
        """
        self._logger.warning(
            "Unhandled event received",
            event_name=event.name,
            correlation_id=event.correlation_id
        )
    
    async def subscribe_to_event(
        self, 
        event_name: str, 
        handler: Optional[Callable] = None
    ) -> None:
        """
        Subscribe to a specific event type.
        
        Args:
            event_name: Name of the event type to subscribe to
            handler: Optional custom handler, defaults to handle_event
        """
        if handler is None:
            handler = self.handle_event
        
        await self._event_bus.subscribe(event_name, handler)
        self._subscriptions[event_name] = handler
        
        self._logger.info(
            "Subscribed to event",
            event_name=event_name
        )
    
    async def unsubscribe_from_event(self, event_name: str) -> None:
        """
        Unsubscribe from a specific event type.
        
        Args:
            event_name: Name of the event type to unsubscribe from
        """
        if event_name in self._subscriptions:
            handler = self._subscriptions[event_name]
            try:
                await self._event_bus.unsubscribe(event_name, handler)
                self._logger.info(
                    "Unsubscribed from event",
                    event_name=event_name
                )
            except Exception as e:
                self._logger.error(
                    "Failed to unsubscribe from event",
                    event_name=event_name,
                    error=str(e)
                )
            finally:
                # Always remove from local subscriptions even if event bus unsubscribe fails
                # This prevents memory leaks in the mixin itself
                del self._subscriptions[event_name]
        else:
            self._logger.warning(
                "Attempted to unsubscribe from non-existent subscription",
                event_name=event_name
            )
    
    async def cleanup_subscriptions(self) -> None:
        """Clean up all event subscriptions."""
        for event_name in list(self._subscriptions.keys()):
            await self.unsubscribe_from_event(event_name)
        
        self._logger.info("Cleaned up all event subscriptions")


# Convenience functions for creating events
def create_audio_chunk_event(
    session_id: str, 
    chunk_id: int, 
    data: bytes, 
    source: str = "websocket"
) -> Event:
    """Create an audio chunk received event."""
    return Event(
        name="audio_chunk_received",
        data={
            "session_id": session_id,
            "chunk_id": chunk_id,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        },
        source=source,
        correlation_id=f"{session_id}_{chunk_id}"
    )


def create_processing_result_event(
    session_id: str,
    chunk_id: int,
    component: str,
    result: Dict[str, Any],
    processing_time_ms: float,
    source: str
) -> Event:
    """Create a processing result event."""
    event_name = f"{component}_completed"
    
    return Event(
        name=event_name,
        data={
            "session_id": session_id,
            "chunk_id": chunk_id,
            "component": component,
            "result": result,
            "processing_time_ms": processing_time_ms,
            "timestamp": datetime.utcnow().isoformat()
        },
        source=source,
        correlation_id=f"{session_id}_{chunk_id}"
    )


def create_chunk_complete_event(
    session_id: str,
    chunk_id: int,
    aggregated_result: Dict[str, Any],
    source: str = "aggregator"
) -> Event:
    """Create a chunk processing complete event."""
    return Event(
        name="chunk_complete",
        data={
            "session_id": session_id,
            "chunk_id": chunk_id,
            "result": aggregated_result,
            "timestamp": datetime.utcnow().isoformat()
        },
        source=source,
        correlation_id=f"{session_id}_{chunk_id}"
    )