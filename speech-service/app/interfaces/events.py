"""
Event system interfaces for the speech-to-text service.

This module defines abstract interfaces for the event-driven architecture,
following Clean Architecture principles with dependency inversion.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Event:
    """
    Base event class for all events in the system.
    
    Attributes:
        name: Event name/type identifier
        data: Event payload data
        source: Component that published the event
        correlation_id: For tracking related events
    """
    name: str
    data: Any
    source: str
    correlation_id: Optional[str] = None


class IEventBus(ABC):
    """
    Abstract interface for the event bus system.
    
    Defines the contract for publishing and subscribing to events
    in the audio processing pipeline. Implementations should handle
    async event delivery and subscription management.
    """
    
    @abstractmethod
    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event: Event instance to publish
            
        Raises:
            EventBusError: If publishing fails
        """
        pass
    
    @abstractmethod
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
            EventBusError: If subscription fails
        """
        pass
    
    @abstractmethod
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
            EventBusError: If unsubscription fails
        """
        pass
    
    @abstractmethod
    async def get_subscribers(self, event_name: str) -> List[Callable]:
        """
        Get all subscribers for a specific event type.
        
        Args:
            event_name: Name of the event type
            
        Returns:
            List of subscriber handler functions
        """
        pass
    
    @abstractmethod
    async def clear_subscribers(self, event_name: Optional[str] = None) -> None:
        """
        Clear subscribers for specific event type or all events.
        
        Args:
            event_name: Event type to clear, or None for all events
        """
        pass


class IEventSubscriber(ABC):
    """
    Abstract interface for components that subscribe to events.
    
    This interface provides a contract for components that need
    to handle events from the event bus.
    """
    
    @abstractmethod
    async def setup_subscriptions(self, event_bus: IEventBus) -> None:
        """
        Set up event subscriptions for this component.
        
        Args:
            event_bus: Event bus instance to subscribe to
        """
        pass
    
    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """
        Handle an incoming event.
        
        Args:
            event: Event to handle
        """
        pass


class IEventPublisher(ABC):
    """
    Abstract interface for components that publish events.
    
    This interface provides a contract for components that need
    to publish events to the event bus.
    """
    
    @abstractmethod
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
        pass


class EventBusError(Exception):
    """Base exception for event bus operations."""
    pass


class EventPublishError(EventBusError):
    """Exception raised when event publishing fails."""
    pass


class EventSubscriptionError(EventBusError):
    """Exception raised when event subscription fails."""
    pass