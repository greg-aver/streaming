"""
Configuration management for the speech-to-text service.

This module handles all application configuration using Pydantic Settings,
following Clean Architecture principles with environment-based configuration.
"""

from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
from pathlib import Path
import logging


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    
    # For future extensibility (Redis, PostgreSQL, etc.)
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL for caching/state storage"
    )
    
    redis_max_connections: int = Field(
        default=10,
        description="Maximum Redis connection pool size"
    )
    
    class Config:
        env_prefix = "DB_"


class VADSettings(BaseSettings):
    """Voice Activity Detection configuration."""
    
    model_name: str = Field(
        default="silero_vad",
        description="VAD model to use (silero_vad, webrtc_vad)"
    )
    
    confidence_threshold: float = Field(
        default=0.5,
        description="Confidence threshold for speech detection",
        ge=0.0,
        le=1.0
    )
    
    frame_duration_ms: int = Field(
        default=30,
        description="Frame duration in milliseconds",
        ge=10,
        le=100
    )
    
    sample_rate: int = Field(
        default=16000,
        description="Expected audio sample rate in Hz"
    )
    
    class Config:
        env_prefix = "VAD_"


class ASRSettings(BaseSettings):
    """Automatic Speech Recognition configuration."""
    
    model_name: str = Field(
        default="base",
        description="Whisper model size (tiny, base, small, medium, large)"
    )
    
    model_path: Optional[str] = Field(
        default=None,
        description="Custom model path if not using default"
    )
    
    language: Optional[str] = Field(
        default=None,
        description="Language hint for transcription (auto-detect if None)"
    )
    
    beam_size: int = Field(
        default=5,
        description="Beam size for decoding",
        ge=1,
        le=10
    )
    
    best_of: int = Field(
        default=5,
        description="Number of candidates to generate",
        ge=1,
        le=10
    )
    
    temperature: float = Field(
        default=0.0,
        description="Temperature for sampling",
        ge=0.0,
        le=1.0
    )
    
    compute_type: str = Field(
        default="float16",
        description="Compute type for inference (float16, int8, float32)"
    )
    
    @field_validator('model_name')
    @classmethod
    def validate_model_name(cls, v):
        """Validate Whisper model name."""
        valid_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
        if v not in valid_models:
            raise ValueError(f"Model name must be one of {valid_models}")
        return v
    
    @field_validator('compute_type')
    @classmethod
    def validate_compute_type(cls, v):
        """Validate compute type."""
        valid_types = ["float16", "int8", "float32"]
        if v not in valid_types:
            raise ValueError(f"Compute type must be one of {valid_types}")
        return v
    
    class Config:
        env_prefix = "ASR_"


class DiarizationSettings(BaseSettings):
    """Speaker Diarization configuration."""
    
    model_name: str = Field(
        default="pyannote/speaker-diarization-3.1",
        description="Diarization model from Hugging Face"
    )
    
    auth_token: Optional[str] = Field(
        default=None,
        description="Hugging Face auth token for model access"
    )
    
    min_speakers: int = Field(
        default=1,
        description="Minimum number of speakers to detect",
        ge=1
    )
    
    max_speakers: int = Field(
        default=10,
        description="Maximum number of speakers to detect",
        ge=1
    )
    
    clustering_method: str = Field(
        default="centroid",
        description="Clustering method for speaker separation"
    )
    
    class Config:
        env_prefix = "DIARIZATION_"


class WebSocketSettings(BaseSettings):
    """WebSocket configuration."""
    
    max_connections: int = Field(
        default=100,
        description="Maximum concurrent WebSocket connections"
    )
    
    max_message_size: int = Field(
        default=1024 * 1024,  # 1MB
        description="Maximum message size in bytes"
    )
    
    ping_interval: int = Field(
        default=20,
        description="WebSocket ping interval in seconds"
    )
    
    ping_timeout: int = Field(
        default=20,
        description="WebSocket ping timeout in seconds"
    )
    
    close_timeout: int = Field(
        default=10,
        description="WebSocket close timeout in seconds"
    )
    
    class Config:
        env_prefix = "WS_"


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    
    level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    format: str = Field(
        default="json",
        description="Log format (json, text)"
    )
    
    output: str = Field(
        default="stdout",
        description="Log output (stdout, file)"
    )
    
    file_path: Optional[str] = Field(
        default=None,
        description="Log file path if output is file"
    )
    
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum log file size in bytes"
    )
    
    backup_count: int = Field(
        default=5,
        description="Number of backup log files to keep"
    )
    
    @field_validator('level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()
    
    @field_validator('format')
    @classmethod
    def validate_log_format(cls, v):
        """Validate log format."""
        valid_formats = ["json", "text"]
        if v not in valid_formats:
            raise ValueError(f"Log format must be one of {valid_formats}")
        return v
    
    class Config:
        env_prefix = "LOG_"


class ProcessingSettings(BaseSettings):
    """Audio processing configuration."""
    
    max_concurrent_workers: int = Field(
        default=4,
        description="Maximum concurrent processing workers per type"
    )
    
    chunk_timeout_seconds: int = Field(
        default=30,
        description="Timeout for processing a single chunk"
    )
    
    max_chunk_size_bytes: int = Field(
        default=512 * 1024,  # 512KB
        description="Maximum audio chunk size in bytes"
    )
    
    result_cache_ttl_seconds: int = Field(
        default=300,  # 5 minutes
        description="Time to live for cached processing results"
    )
    
    enable_vad: bool = Field(
        default=True,
        description="Enable Voice Activity Detection"
    )
    
    enable_asr: bool = Field(
        default=True,
        description="Enable Automatic Speech Recognition"
    )
    
    enable_diarization: bool = Field(
        default=True,
        description="Enable Speaker Diarization"
    )
    
    class Config:
        env_prefix = "PROCESSING_"


class Settings(BaseSettings):
    """
    Main application settings.
    
    Aggregates all configuration sections and provides
    application-wide settings management.
    """
    
    # Application metadata
    app_name: str = Field(
        default="Speech-to-Text Service",
        description="Application name"
    )
    
    app_version: str = Field(
        default="1.0.0",
        description="Application version"
    )
    
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    
    # Server configuration
    host: str = Field(
        default="0.0.0.0",
        description="Server bind host"
    )
    
    port: int = Field(
        default=8000,
        description="Server bind port",
        ge=1,
        le=65535
    )
    
    # CORS settings
    cors_origins: List[str] = Field(
        default=["*"],
        description="CORS allowed origins"
    )
    
    cors_methods: List[str] = Field(
        default=["*"],
        description="CORS allowed methods"
    )
    
    cors_headers: List[str] = Field(
        default=["*"],
        description="CORS allowed headers"
    )
    
    # Component settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    asr: ASRSettings = Field(default_factory=ASRSettings)
    diarization: DiarizationSettings = Field(default_factory=DiarizationSettings)
    websocket: WebSocketSettings = Field(default_factory=WebSocketSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    
    @field_validator('cors_origins', 'cors_methods', 'cors_headers', mode='before')
    @classmethod
    def parse_cors_lists(cls, v):
        """Parse CORS configuration from environment variables."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(',')]
        return v
    
    def get_log_config(self) -> Dict[str, Any]:
        """
        Get logging configuration dictionary.
        
        Returns:
            Dictionary suitable for logging.config.dictConfig
        """
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                    "class": "pythonjsonlogger.jsonlogger.JsonFormatter"
                },
                "text": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": self.logging.format,
                    "stream": "ext://sys.stdout"
                }
            },
            "root": {
                "level": self.logging.level,
                "handlers": ["console"]
            }
        }
        
        if self.logging.output == "file" and self.logging.file_path:
            config["handlers"]["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": self.logging.format,
                "filename": self.logging.file_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count
            }
            config["root"]["handlers"] = ["file"]
        
        return config
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Example environment variables
        schema_extra = {
            "example": {
                "APP_NAME": "Speech-to-Text Service",
                "DEBUG": "false",
                "HOST": "0.0.0.0",
                "PORT": "8000",
                "ASR_MODEL_NAME": "base",
                "VAD_CONFIDENCE_THRESHOLD": "0.5",
                "LOG_LEVEL": "INFO",
                "PROCESSING_MAX_CONCURRENT_WORKERS": "4"
            }
        }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """
    Get application settings instance.
    
    This function can be used for dependency injection
    and testing with different configurations.
    
    Returns:
        Settings instance
    """
    return settings