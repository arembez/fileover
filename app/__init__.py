"""
app/__init__.py

Root package initializer for FileOver microservice.
Exposes the main public API: controllers and sessions singletons,
health checker, base classes, types, and authentication decorator.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from .base import EndpointController
from .types import (
    SessionInitRequest, 
    SessionStatus, 
    SessionResponse, 
    SessionPriorityTask,
    Credentials,
    ErrorResponse
)
from .controllers_collection import controllers
from .sessions_collection import sessions
from .auth import auth
from .health import health, ServiceStatus, HealthCheckResponse, ComponentHealth

__all__ = [
    # Base class for endpoint controllers
    'EndpointController',
    
    # Singleton instances (main API)
    'controllers',
    'sessions',
    'health',  
    
    # Types
    'Credentials',
    'SessionInitRequest',
    'SessionStatus',
    'SessionResponse',
    'SessionPriorityTask',
    'ErrorResponse',
    
    # Health check types
    'ServiceStatus',
    'HealthCheckResponse',
    'ComponentHealth',
    
    # Auth decorator
    'auth',
]

# Package metadata
__title__ = "fileover"
__version__ = '1.2.5'
__description__ = "REST API Gateway for file operations"
__author__ = 'Alex Rembez <arembez@gmail.com>'