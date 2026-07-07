"""
app/types.py

Pydantic models and type definitions for FileOver microservice.
Defines data structures for authentication, sessions, and task management.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from __future__ import annotations
from typing import Any
from enum import Enum
from pydantic import BaseModel, Field
from dataclasses import dataclass, field

class SessionInitRequest(BaseModel):
    controller: str = Field(..., description="Endpoint controller name")
    identity: str | None = Field(None, description="Backend identity (if required by the controller)")
    password: str | None = Field(None, description="Password (if required by the controller)")
    server: str | None = Field(None, description="Backend server address (if required by the controller)")

    class Config:
        extra = "allow" 

class SessionResponse(BaseModel):
    """
    Response model for successful session creation or refresh.

    Attributes:
        session_id (str): Unique session identifier
        token (str): JWT token for authenticating subsequent requests
        expires_at (float): Session expiration time as a Unix timestamp
        identity (str | None): Backend identity associated with the session, if any
    """

    session_id: str
    token: str
    expires_at: float
    identity: str | None = None
    
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
        future (Any): Future used to deliver the assigned session.
    
    Note:
        The class is ordered by priority first, then timestamp.
        session_id, task, and future are excluded from comparison.
    """
    priority: int
    timestamp: float
    session_id: str = field(compare=False)
    task: Any = field(compare=False)
    future: Any = field(compare=False)