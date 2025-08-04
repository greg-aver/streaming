"""
Tests for DI Container lifecycle management.

Tests the ServiceLifecycleManager and container initialization/cleanup
for the Clean DI architecture implementation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from app.container import ServiceLifecycleManager, container


class TestContainerLifecycle:
    """Test cases for DI Container lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_service_lifecycle_manager_context(self):
        """Test ServiceLifecycleManager context manager."""
        with patch('app.container.container.vad_worker') as mock_vad:
            # Mock VAD worker to avoid abstract method error
            mock_vad_instance = AsyncMock()
            mock_vad_instance.set_event_bus = AsyncMock()
            mock_vad_instance.start = AsyncMock()
            mock_vad_instance.stop = AsyncMock()
            mock_vad.return_value = mock_vad_instance
            
            manager = ServiceLifecycleManager()
            
            # Test context manager lifecycle
            async with manager:
                # Should initialize all services
                assert mock_vad_instance.set_event_bus.called
                assert mock_vad_instance.start.called
            
            # Should cleanup all services on exit
            assert mock_vad_instance.stop.called
    
    @pytest.mark.asyncio
    async def test_asr_worker_container_creation(self):
        """Test ASR worker creation through container."""
        # Create ASR worker via container
        asr_worker = container.asr_worker()
        
        # Should be created successfully
        assert asr_worker is not None
        assert hasattr(asr_worker, 'set_event_bus')
        assert hasattr(asr_worker, 'start')
        assert hasattr(asr_worker, 'stop')
    
    @pytest.mark.asyncio
    async def test_asr_worker_full_lifecycle(self):
        """Test complete ASR worker lifecycle via container."""
        # Create components
        asr_worker = container.asr_worker()
        event_bus = container.event_bus()
        
        # Initialize
        await asr_worker.asr_service.initialize()
        asr_worker.set_event_bus(event_bus)
        
        # Start
        await asr_worker.start()
        assert asr_worker.is_running
        
        # Stop
        await asr_worker.stop()
        assert not asr_worker.is_running
    
    @pytest.mark.asyncio
    async def test_container_service_dependencies(self):
        """Test that container properly injects dependencies."""
        # Create worker and verify dependencies
        asr_worker = container.asr_worker()
        event_bus = container.event_bus()
        
        # Verify dependency injection - worker should have service
        assert asr_worker.asr_service is not None
        assert event_bus is not None
        
        # Services should be properly configured
        assert hasattr(asr_worker.asr_service, 'initialize')
        assert hasattr(asr_worker.asr_service, 'transcribe')
    
    @pytest.mark.asyncio
    async def test_container_singleton_behavior(self):
        """Test container singleton behavior for shared resources."""
        # Create multiple instances
        event_bus1 = container.event_bus()
        event_bus2 = container.event_bus()
        
        # Should be the same instance (singleton)
        assert event_bus1 is event_bus2
    
    @pytest.mark.asyncio 
    async def test_container_factory_behavior(self):
        """Test container factory behavior for workers."""
        # Create multiple worker instances
        asr_worker1 = container.asr_worker()
        asr_worker2 = container.asr_worker()
        
        # Should be different instances (factory)
        assert asr_worker1 is not asr_worker2
        
        # Services are also factory instances, so should be different
        assert asr_worker1.asr_service is not asr_worker2.asr_service
        
        # But should be same type
        assert type(asr_worker1.asr_service) is type(asr_worker2.asr_service)
    
    def test_container_configuration(self):
        """Test container configuration and providers."""
        # Container should have all necessary providers
        assert hasattr(container, 'event_bus')
        assert hasattr(container, 'asr_service')
        assert hasattr(container, 'asr_worker')
        assert hasattr(container, 'vad_service')
        assert hasattr(container, 'vad_worker')
        assert hasattr(container, 'diarization_service')
        assert hasattr(container, 'diarization_worker')
        assert hasattr(container, 'websocket_handler')
        assert hasattr(container, 'result_aggregator')
    
    @pytest.mark.asyncio
    async def test_error_handling_in_lifecycle(self):
        """Test error handling in service lifecycle."""
        with patch('app.container.initialize_services') as mock_init:
            # Mock initialization failure
            mock_init.side_effect = Exception("Service init failed")
            
            manager = ServiceLifecycleManager()
            
            # Should handle errors gracefully
            with pytest.raises(Exception, match="Service init failed"):
                async with manager:
                    pass
    
    @pytest.mark.asyncio
    async def test_partial_initialization_cleanup(self):
        """Test cleanup when initialization partially fails."""
        with patch('app.container.container.asr_worker') as mock_asr:
            # Mock ASR worker failure after other services succeed
            mock_asr.side_effect = Exception("ASR worker failed")
            
            manager = ServiceLifecycleManager()
            
            # Should attempt cleanup even on partial failure
            with pytest.raises(Exception):
                async with manager:
                    pass
            
            # Cleanup should have been attempted
            assert mock_asr.called