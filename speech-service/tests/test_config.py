"""
Тесты для конфигурации приложения.

Проверяем что настройки корректно загружаются и валидируются.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings, VADSettings, ASRSettings, get_settings


def test_default_settings():
    """Тест создания настроек с дефолтными значениями."""
    settings = Settings()
    
    assert settings.app_name == "Speech-to-Text Service"
    assert settings.app_version == "1.0.0"
    assert settings.debug is False
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000


def test_vad_settings():
    """Тест настроек VAD."""
    vad_settings = VADSettings()
    
    assert vad_settings.model_name == "silero_vad"
    assert vad_settings.confidence_threshold == 0.5
    assert vad_settings.sample_rate == 16000
    assert 0.0 <= vad_settings.confidence_threshold <= 1.0


def test_vad_settings_validation():
    """Тест валидации настроек VAD."""
    # Проверяем что неправильные значения отклоняются
    with pytest.raises(ValidationError):
        VADSettings(confidence_threshold=1.5)  # Больше 1.0
    
    with pytest.raises(ValidationError):
        VADSettings(confidence_threshold=-0.1)  # Меньше 0.0


def test_asr_settings():
    """Тест настроек ASR."""
    asr_settings = ASRSettings()
    
    assert asr_settings.model_name == "base"
    assert asr_settings.compute_type == "float16"
    assert asr_settings.beam_size >= 1


def test_asr_settings_validation():
    """Тест валидации настроек ASR."""
    # Проверяем корректные модели
    valid_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    for model in valid_models:
        settings = ASRSettings(model_name=model)
        assert settings.model_name == model
    
    # Проверяем что неправильные модели отклоняются
    with pytest.raises(ValidationError):
        ASRSettings(model_name="invalid_model")


def test_get_settings():
    """Тест функции получения настроек."""
    settings1 = get_settings()
    settings2 = get_settings()
    
    # Должны получить те же экземпляры
    assert settings1 is settings2
    assert isinstance(settings1, Settings)


def test_cors_settings():
    """Тест настроек CORS."""
    settings = Settings()
    
    assert isinstance(settings.cors_origins, list)
    assert isinstance(settings.cors_methods, list)  
    assert isinstance(settings.cors_headers, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])