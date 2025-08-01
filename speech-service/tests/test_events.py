"""
Тесты для событийной системы (EventBus).

Проверяем что события корректно публикуются и обрабатываются.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock

from app.events import AsyncEventBus, EventPublisherMixin, EventSubscriberMixin
from app.interfaces.events import Event


@pytest.mark.asyncio
async def test_event_bus_creation():
    """Тест создания EventBus."""
    event_bus = AsyncEventBus()
    
    assert event_bus is not None
    assert hasattr(event_bus, 'publish')
    assert hasattr(event_bus, 'subscribe')


@pytest.mark.asyncio
async def test_simple_event_publish_subscribe():
    """Тест простой публикации и подписки на события."""
    event_bus = AsyncEventBus()
    received_events = []
    
    async def test_handler(event: Event):
        received_events.append(event)
    
    # Подписываемся на событие
    await event_bus.subscribe("test_event", test_handler)
    
    # Публикуем событие
    test_event = Event(
        name="test_event",
        data={"message": "test"},
        source="test"
    )
    
    await event_bus.publish(test_event)
    
    # Проверяем что событие получено
    assert len(received_events) == 1
    assert received_events[0].name == "test_event"
    assert received_events[0].data["message"] == "test"


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Тест множественных подписчиков на одно событие."""
    event_bus = AsyncEventBus()
    received_events_1 = []
    received_events_2 = []
    
    async def handler_1(event: Event):
        received_events_1.append(event)
    
    async def handler_2(event: Event):
        received_events_2.append(event)
    
    # Подписываемся двумя обработчиками
    await event_bus.subscribe("test_event", handler_1)
    await event_bus.subscribe("test_event", handler_2)
    
    # Публикуем событие
    test_event = Event(
        name="test_event",
        data={"message": "broadcast"},
        source="test"
    )
    
    await event_bus.publish(test_event)
    
    # Проверяем что оба обработчика получили событие
    assert len(received_events_1) == 1
    assert len(received_events_2) == 1
    assert received_events_1[0].data["message"] == "broadcast"
    assert received_events_2[0].data["message"] == "broadcast"


@pytest.mark.asyncio
async def test_unsubscribe():
    """Тест отписки от событий."""
    event_bus = AsyncEventBus()
    received_events = []
    
    async def test_handler(event: Event):
        received_events.append(event)
    
    # Подписываемся
    await event_bus.subscribe("test_event", test_handler)
    
    # Публикуем первое событие
    await event_bus.publish(Event("test_event", {"msg": "first"}, "test"))
    
    # Отписываемся
    await event_bus.unsubscribe("test_event", test_handler)
    
    # Публикуем второе событие
    await event_bus.publish(Event("test_event", {"msg": "second"}, "test"))
    
    # Проверяем что получили только первое событие
    assert len(received_events) == 1
    assert received_events[0].data["msg"] == "first"


@pytest.mark.asyncio 
async def test_no_subscribers():
    """Тест публикации события без подписчиков."""
    event_bus = AsyncEventBus()
    
    # Публикуем событие без подписчиков - не должно вызывать ошибку
    test_event = Event("no_subscribers", {"data": "test"}, "test")
    
    # Это не должно вызвать исключение
    await event_bus.publish(test_event)


@pytest.mark.asyncio
async def test_event_publisher_mixin():
    """Тест EventPublisherMixin."""
    event_bus = AsyncEventBus()
    received_events = []
    
    async def test_handler(event: Event):
        received_events.append(event)
    
    await event_bus.subscribe("test_event", test_handler)
    
    # Создаем объект с миксином
    class TestPublisher(EventPublisherMixin):
        def __init__(self, event_bus):
            super().__init__(event_bus, "test_publisher")
    
    publisher = TestPublisher(event_bus)
    
    # Публикуем событие через миксин
    await publisher.publish_event("test_event", {"message": "from_mixin"})
    
    # Проверяем
    assert len(received_events) == 1
    assert received_events[0].source == "test_publisher"
    assert received_events[0].data["message"] == "from_mixin"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])