# Event-Driven Architecture для Speech-to-Text Service

## 🎯 Архитектурный подход

Проект реализует **Event-Driven Architecture в рамках монолита** через центральную **Event Bus**, а НЕ микросервисную архитектуру. Это более эффективный подход для речевой обработки в реальном времени.

## 🏗️ Структура системы

### **Единый монолит `speech-service` с внутренними компонентами:**

#### **1. Event Bus - Центральная шина событий (`AsyncEventBus`)**
- Асинхронная публикация и подписка на события
- Управление жизненным циклом событий
- Structured logging всех операций
- История событий для отладки

#### **2. Workers (обработчики событий):**
- ✅ **VAD Worker** - слушает `audio_chunk_received`, публикует `vad_completed` + `speech_detected`
- ✅ **ASR Worker** - слушает `speech_detected`, публикует `asr_completed`  
- ⏳ **Diarization Worker** - слушает `speech_detected`, публикует `diarization_completed`

#### **3. Services (бизнес-логика):**
- ✅ **VAD Service** (Silero + Mock версии)
- ✅ **ASR Service** (Faster-Whisper + Mock версии) - настроен на русский язык
- ⏳ **Diarization Service** (pyannote + Mock версии)

#### **4. Aggregator** (планируется):
- Слушает: `vad_completed`, `asr_completed`, `diarization_completed`
- Объединяет результаты разных компонентов
- Публикует: `chunk_complete` с финальным результатом

#### **5. WebSocket Handler** (планируется):
- Получает аудио от клиентов → публикует `audio_chunk_received`
- Слушает `chunk_complete` → отправляет результат клиенту

## 🔄 Поток событий

```
Client (WebSocket) 
    ↓ audio chunk
WebSocket Handler → 📢 audio_chunk_received
    ↓
VAD Worker → 📢 vad_completed + speech_detected (если речь)
    ↓
ASR Worker → 📢 asr_completed 
    ↓
Diarization Worker → 📢 diarization_completed
    ↓
Aggregator → 📢 chunk_complete
    ↓
WebSocket Handler → Client (результат)
```

## 📊 События в системе

| Событие | Источник | Слушатели | Данные |
|---------|----------|-----------|--------|
| `audio_chunk_received` | WebSocket Handler | VAD Worker | session_id, chunk_id, audio_data |
| `vad_completed` | VAD Worker | Aggregator | результат VAD |
| `speech_detected` | VAD Worker | ASR, Diarization Workers | session_id, chunk_id, audio_data |
| `asr_completed` | ASR Worker | Aggregator | результат транскрипции |
| `diarization_completed` | Diarization Worker | Aggregator | результат диаризации |
| `chunk_complete` | Aggregator | WebSocket Handler | финальный результат |

## 🎯 Преимущества Event-Driven Monolith

1. **Слабая связанность** - компоненты общаются только через события
2. **Масштабируемость** - можно легко добавить новые workers
3. **Тестируемость** - каждый worker тестируется изолированно через mock события
4. **Производительность** - нет network overhead между сервисами
5. **Простота деплоя** - один процесс, один контейнер
6. **Асинхронность** - все обработчики работают параллельно
7. **Надёжность** - изоляция ошибок между компонентами
8. **Мониторинг** - централизованное логирование событий

## 🔧 Текущее состояние

### **✅ Реализовано:**
- Event Bus система с подписками и публикациями (`AsyncEventBus`)
- VAD Worker с событийной логикой  
- ASR Worker с событийной логикой
- Mock сервисы для тестирования (VAD, ASR)
- DI контейнер для всех компонент
- Pydantic модели для валидации данных
- Structured logging через structlog
- Clean Architecture с интерфейсами

### **🔄 В разработке (Итерация 2):**
- Тестирование Mock ASR Service
- Создание Mock Diarization Service
- Исправление найденных проблем

### **⏳ Запланировано:**
- Diarization Worker
- Result Aggregator 
- WebSocket Handler (FastAPI)
- Полная интеграция через main.py
- Containerization (Docker)

## 📝 Конфигурация компонентов

### Event Bus
```python
# Асинхронная шина событий с историей и метриками
event_bus = AsyncEventBus()
await event_bus.publish(event)
await event_bus.subscribe("event_name", handler)
```

### Workers
```python
# Worker подписывается на события и публикует результаты
class VADWorker(IWorker, EventSubscriberMixin, EventPublisherMixin):
    async def start(self):
        await self.subscribe_to_event("audio_chunk_received", self._handle_audio_chunk)
```

### Services
```python
# Service реализует бизнес-логику
class SileroVADService(IVADService):
    async def detect_speech(self, audio_data: bytes) -> Dict[str, Any]
```

## 🚀 Следующие итерации

### Итерация 3: Workers тестирование
1. VAD worker с mock сервисом
2. ASR worker с mock сервисом  
3. Diarization worker создание и тестирование

### Итерация 4: Интеграционные тесты
1. Event flow тестирование
2. End-to-end pipeline тест
3. Полная интеграция компонентов

### Итерация 5: WebSocket интеграция
1. FastAPI приложение с WebSocket endpoint
2. Result Aggregator реализация
3. Полный цикл: Client → WebSocket → Event Bus → Workers → Response

## 🏗️ Паттерны проектирования

- **Event-Driven Architecture** - основной архитектурный паттерн
- **Clean Architecture** - разделение на слои (интерфейсы, сервисы, workers)
- **Dependency Injection** - через dependency-injector
- **Publisher-Subscriber** - через Event Bus
- **Command Query Separation** - разделение команд и запросов
- **Domain Events** - события как first-class citizens

## 📈 Метрики и мониторинг

Event Bus предоставляет метрики:
```python
stats = await event_bus.get_stats()
# {
#   "total_event_types": 6,
#   "total_subscribers": 8, 
#   "event_history_size": 150,
#   "event_counts": {"vad_completed": 50, "asr_completed": 45},
#   "subscriber_breakdown": {"vad_completed": 2, "speech_detected": 3}
# }
```

## 📚 Связанная документация

- **Текущее состояние**: `docs/CURRENT_STATUS.md` - ГДЕ МЫ, ЧТО ДЕЛАЕМ, КУДА ИДЕМ
- **Методология разработки**: `docs/DEVELOPMENT_METHODOLOGY.md` - КАК разрабатываем (циклический подход)
- **Детальный прогресс**: `TESTING_LOG.md` - лог итераций и тестирования
- **Планы**: `TODO.md` - задачи и roadmap

---

**Дата создания**: 2025-08-02  
**Версия архитектуры**: 1.0  
**Статус**: Event-Driven Architecture в монолите - АКТИВНАЯ РАЗРАБОТКА  
**Методология**: Циклическая разработка с полным тестированием каждой итерации  
**Язык проекта**: Русский (все модели ASR настроены на русский язык)