"""
app/__init__.py

Root package initializer for FileOver microservice.
Exposes the main public API: controllers and sessions singletons,
base classes, types, and authentication decorator.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from .base import EndpointController
from .types import SessionInitRequest, SessionStatus, SessionResponse, SessionPriorityTask
from .controllers_collection import controllers
from .sessions_collection import sessions
from .auth import auth

__all__ = [
    # Base classes (needed for extending)
    'EndpointController',
    
    # Singleton instances (main API)
    'controllers',
    'sessions',
    
    # Types (needed for type hints and API contracts)
    'SessionInitRequest',
    'SessionStatus',
    'SessionResponse',
    'SessionPriorityTask',
    
    # Auth decorator
    'auth',
]

# Package metadata
__version__ = '1.2.3'
__author__ = 'Alex Rembez <arembez@gmail.com>'