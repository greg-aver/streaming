# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project called "Streaming" set up with a virtual environment.

## Development Setup

- Virtual environment is located in `.venv/`
- Activate the virtual environment before development:
  - Windows: `.venv\Scripts\activate`
  - Unix/macOS: `source .venv/bin/activate`

## Common Commands

### Environment Management
```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Activate virtual environment (Unix/macOS)  
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Generate requirements file
pip freeze > requirements.txt
```

### Development Commands
```bash
# Run the main application (when main.py exists)
python main.py

# Run tests (when test files exist)
python -m pytest

# Run a specific test file
python -m pytest tests/test_filename.py

# Run with coverage
python -m pytest --cov=src

# Format code (if black is installed)
black .

# Lint code (if flake8 is installed)
flake8 .

# Type checking (if mypy is installed)
mypy .
```

## ТЕКУЩИЙ СТАТУС РАЗРАБОТКИ

### Последняя сессия - DI Container Implementation

**ЧТО СДЕЛАНО:**
1. ✅ Интеграционные тесты (3/5 проходят) - test_integration_pipeline.py
2. ✅ REST API endpoints (32/32 тестов проходят) - /health, /sessions, /stats  
3. ✅ Рефакторинг VADWorker с Clean DI подходом - app/workers/vad.py
4. ✅ Создан новый ASRWorker с Clean DI подходом - app/workers/asr_new.py
5. ✅ Обновлен container.py с реальными провайдерами и lifecycle management

**ЧТО В ПРОЦЕССЕ (ПРЕРВАНО):**
- Замена старого ASRWorker на новый DI worker
- Рефакторинг DiarizationWorker

**СЛЕДУЮЩИЕ ШАГИ:**
1. ВЫСОКИЙ ПРИОРИТЕТ:
   - Заменить app/workers/asr.py на app/workers/asr_new.py
   - Рефакторить DiarizationWorker по образцу VAD/ASR workers
   - Обновить container.py initialization для использования новых DI workers
   
2. СРЕДНИЙ ПРИОРИТЕТ:
   - Создать тесты для нового DI container
   - Обновить main.py для интеграции с DI container
   - Исправить failing интеграционные тесты (2/5)

### Архитектурные решения - Senior подход:

**1. Clean DI Pattern без mixins:**
```python
class Worker(IWorker):
    def __init__(self, service: IService, config: Settings):
        # Direct dependency injection
        
    def set_event_bus(self, event_bus: IEventBus) -> None:
        # Setter injection для избежания circular dependencies
```

**2. Two-phase initialization в container.py:**
```python
# Phase 1: Create workers
worker = container.worker()
# Phase 2: Configure event bus
worker.set_event_bus(event_bus)
await worker.start()
```

**3. Graceful shutdown с proper resource cleanup:**
- Обратный порядок остановки (WebSocket → Workers → Services)
- Timeout для завершения задач + force cancellation
- Graceful degradation при ошибках cleanup

### Файлы для изучения следующей сессии:

1. **app/workers/asr_new.py** - новый Clean DI ASR worker (готов к замене)
2. **app/workers/vad.py** - пример Clean DI подхода
3. **app/container.py** - DI container с lifecycle management
4. **app/workers/diarization.py** - требует рефакторинга
5. **tests/test_integration_pipeline.py** - интеграционные тесты

## Project Structure

```
speech-service/
├── app/
│   ├── workers/          # Event-driven workers (VAD, ASR, Diarization)
│   ├── services/         # Business logic services
│   ├── api/             # REST API endpoints 
│   ├── interfaces/       # Abstract interfaces
│   ├── models/          # Pydantic models
│   ├── events.py        # Event system
│   ├── container.py     # DI Container
│   └── config.py        # Configuration
├── tests/               # Test files
└── requirements.txt     # Dependencies
```