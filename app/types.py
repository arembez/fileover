"""
app/types.py

Pydantic models and type definitions for FileOver microservice.
Defines data structures for authentication, sessions, and task management.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from typing import Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass, field


class Credentials(BaseModel):
    """
    Base credentials model for authentication.
    
    Attributes:
        username (str): User name for authentication (minimum 1 character)
        password (str): Password for authentication (minimum 1 character)
    """
    username: str = Field(..., min_length=1, description="User name")
    password: str = Field(..., min_length=1, description="Password")
    
    class Config:
        validate_assignment = True
        str_strip_whitespace = True
    
    @field_validator('username', 'password')
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        """
        Validate that fields are not empty after stripping whitespace.
        
        Args:
            v (str): The value to validate
            
        Returns:
            str: The stripped value
            
        Raises:
            ValueError: If the value is empty after stripping
        """
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()


class SessionInitRequest(Credentials):
    """
    Request model for initializing a new session.
    Extends Credentials with server and controller information.
    
    Attributes:
        server (str): Server name or address to connect to
        controller (str): Name of the controller class to use (e.g., 'SMBController')
    
    Note:
        Extra fields are allowed (via Config.extra = "allow") to pass
        controller-specific parameters.
    """
    server: str = Field(..., min_length=1, description="Server name")
    controller: str = Field(..., description="Name of the controller class")
    
    class Config:
        extra = "allow"

    @field_validator('server')
    @classmethod
    def check_server(cls, v: str) -> str:
        """
        Validate that server field is not empty after stripping whitespace.
        
        Args:
            v (str): The server value to validate
            
        Returns:
            str: The stripped server value
            
        Raises:
            ValueError: If the server value is empty after stripping
        """
        if not v or not v.strip():
            raise ValueError('Server name cannot be empty')
        return v.strip()
    

class SessionResponse(BaseModel):
    """
    Response model for successful session creation.
    
    Attributes:
        success (bool): Always True for successful responses
        token (str): JWT token for authenticating subsequent requests
    """
    success: bool
    token: str
    

class ErrorResponse(BaseModel):
    """
    Standard error response model.
    
    Attributes:
        detail (str): Human-readable error description
    """
    detail: str
    
    class Config:
        str_strip_whitespace = True  


class SessionStatus(str, Enum):
    """
    Enumeration of possible session states.
    
    Values:
        IDLE: Session is active but not processing any task
        BUSY: Session is currently processing a task
        ERROR: Session encountered an error and needs recreation
        CLOSED: Session has been terminated
    """
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    CLOSED = "closed"
    

@dataclass(order=True)
class SessionPriorityTask:
    """
    Priority task item for session task queue.
    Uses dataclass with ordering for priority queue implementation.
    
    Attributes:
        priority (int): Task priority (lower number = higher priority)
        timestamp (float): Time when task was created (for FIFO within same priority)
        session_id (str): ID of the session this task belongs to
        task (Any): The actual task to execute
        future (Any): Future object for task result
    
    Note:
        The class is ordered by priority first, then timestamp.
        session_id, task, and future are excluded from comparison.
    """
    priority: int
    timestamp: float
    session_id: str = field(compare=False)
    task: Any = field(compare=False)
    future: Any = field(compare=False)