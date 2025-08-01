# TODO List для Speech-to-Text Service

## Выполненные задачи ✅
- [x] Создать структуру проекта speech-service/ с папками app/, tests/, docs/
- [x] Создать requirements.txt с dependency-injector, pydantic, structlog и другими зависимостями
- [x] Создать __init__.py файлы и базовую структуру
- [x] Создать app/models/ с Pydantic моделями AudioChunkModel, ProcessingResultModel
- [x] Создать app/interfaces/ с абстракциями для всех компонентов
- [x] Создать app/config.py с Settings классом на pydantic-settings
- [x] Реализовать app/events.py с EventBus интерфейсом и реализацией
- [x] Создать app/container.py с DI контейнером
- [x] Создать app/services/ с VAD, ASR, Diarization сервисами

## В процессе 🔄
- [ ] Реализовать app/workers/ с чистой архитектурой и DI
  - [x] VAD Worker
  - [x] ASR Worker (частично)
  - [ ] Diarization Worker
  - [ ] Тестирование workers

## Ожидающие задачи 📋
- [ ] Создать app/aggregator.py как domain service
- [ ] Реализовать WebSocket endpoint в app/main.py с DI
- [ ] Создать comprehensive тесты в tests/
- [ ] Написать подробную документацию во всех файлах docs/
- [ ] Создать Dockerfile и docker-compose.yml

## Следующие шаги (Agile/Scrum подход)

### Итерация 1: Тестирование базовых компонентов
1. ✅ Тест конфигурации (config.py) - ЗАВЕРШЕНО (7/7 тестов)
2. 🔄 Тест event bus - В РАБОТЕ (тесты созданы, заблокированы numpy)
3. ⏳ Тест моделей Pydantic - ОЖИДАЕТ
4. ⏳ Исправление найденных ошибок - ОЖИДАЕТ

**ТЕКУЩАЯ ВЕТКА**: `feature/testing-iteration-1-complete`
**ЦЕЛЬ**: Завершить Итерацию 1 полностью перед переходом к Итерации 2

### Итерация 2: Тестирование сервисов
1. Mock сервисы VAD/ASR/Diarization
2. Unit тесты для каждого сервиса
3. Исправление найденных ошибок

### Итерация 3: Тестирование workers
1. VAD worker с mock сервисом
2. ASR worker с mock сервисом
3. Исправление найденных ошибок

### Итерация 4: Интеграционные тесты
1. Event flow тестирование
2. End-to-end pipeline тест

## Принципы работы
- Маленькие итерации (1-2 часа каждая)
- Тестирование каждого компонента отдельно
- Исправление ошибок сразу при обнаружении
- Постепенное добавление функциональности
- Циклический подход: код → тест → исправление → следующий компонент

Общий план реализации Real-time Speech-to-Text сервиса (Senior Python Developer подход)

    1. Environment & Dependency Setup + Architecture Foundation

    1.1. Создать структуру проекта speech-service/ с папками app/, tests/, docs/
    1.2. Создать requirements.txt с зависимостями: fastapi, uvicorn, silero-vad, faster-whisper, pyannote.audio, pydantic, dependency-injector,
    pytest, pydantic-settings
    1.3. Настроить виртуальное окружение и установить зависимости
    1.4. Создать init.py файлы в app/ и app/workers/
    1.5. Создать docs/ARCHITECTURE.md для документации архитектурных решений
    1.6. Настроить structured логирование с использованием structlog/loguru

    2. Define Data Models & EventBus (Clean Architecture + Pydantic)

    2.1. В app/models/ создать Pydantic модели: AudioChunkModel, ProcessingResultModel, WebSocketResponseModel
    2.2. В app/events.py реализовать абстрактный EventBus интерфейс и конкретную реализацию
    2.3. Создать app/interfaces/ с абстракциями для всех компонентов (Protocol/ABC)
    2.4. В app/config.py создать Settings класс с pydantic-settings для конфигурации
    2.5. Добавить валидацию данных и error handling на уровне моделей
    2.6. Документировать все модели данных и события в docs/DATA_MODELS.md

    3. Implement Dependency Injection Container

    3.1. В app/container.py создать DI контейнер с dependency-injector
    3.2. Зарегистрировать все сервисы, репозитории и воркеры
    3.3. Настроить lifecycle management для ресурсов
    3.4. Создать factory методы для создания экземпляров
    3.5. Документировать DI архитектуру в docs/DEPENDENCY_INJECTION.md

    4. Implement Worker Components (Clean Code принципы)

    4.1. В app/workers/vad.py создать VADWorker с внедрением зависимостей через конструктор
    4.2. Выделить SileroVAD в отдельный сервис app/services/vad_service.py с интерфейсом
    4.3. В app/workers/asr.py создать ASRWorker с чистой архитектурой
    4.4. Выделить Faster-Whisper в app/services/asr_service.py с абстракцией
    4.5. В app/workers/diarization.py создать DiarizationWorker
    4.6. Выделить pyannote в app/services/diarization_service.py
    4.7. Каждый worker должен логировать операции с контекстом
    4.8. Документировать каждый компонент в docs/WORKERS.md

    5. Build ResultAggregator & WebSocket Integration (Domain Logic)

    5.1. В app/aggregator.py создать ResultAggregator как domain service
    5.2. Создать app/repositories/ для хранения состояния (in-memory + interface)
    5.3. В app/main.py создать FastAPI приложение с DI integration
    5.4. Реализовать WebSocket endpoint с внедрением зависимостей
    5.5. Создать app/handlers/ для WebSocket обработчиков
    5.6. Добавить middleware для логирования и обработки ошибок
    5.7. Документировать API в docs/API.md

    6. Write Comprehensive Tests (TDD подход)

    6.1. Создать mock реализации всех внешних зависимостей
    6.2. В tests/unit/ написать unit тесты для каждого компонента изолированно
    6.3. В tests/integration/ написать интеграционные тесты
    6.4. В tests/test_websocket.py создать e2e тесты с TestClient
    6.5. Настроить coverage reporting с минимальным порогом 90%
    6.6. Документировать тестовую стратегию в docs/TESTING.md

    7. Documentation & Code Quality

    7.1. Добавить docstrings ко всем классам и методам (Google/Sphinx style)
    7.2. Создать docs/README.md с описанием архитектуры и принципов
    7.3. Настроить pre-commit hooks с black, isort, flake8, mypy
    7.4. Добавить type hints везде с mypy в strict режиме
    7.5. Создать docs/DEVELOPMENT.md с руководством для разработчиков

    8. Dockerize & Deploy (Production Ready)

    8.1. Создать многостадийный Dockerfile с оптимизацией размера
    8.2. Добавить health checks и graceful shutdown
    8.3. Создать docker-compose.yml с мониторингом и логированием
    8.4. Документировать deployment в docs/DEPLOYMENT.md

    Ключевые принципы: Clean Code, Clean Architecture, SOLID, DRY, Dependency Injection, подробная документация, structured logging, type safety

