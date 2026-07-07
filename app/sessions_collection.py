"""
app/sessions_collection.py

Session management system for FileOver microservice.
Manages user sessions, controller instances, authentication tokens,
and background maintenance tasks.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""
from __future__ import annotations
import asyncio
import time
import heapq
import uuid
import jwt
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import deque
from typing import Dict, Optional

from app.base import EndpointController
from app.types import SessionInitRequest, SessionStatus, SessionResponse, SessionPriorityTask
from app.controllers_collection import controllers

logger = logging.getLogger(__name__)

@dataclass
class Session:
    """
    Represents an active user session with a controller instance.
    
    Attributes:
        id (str): Unique session identifier
        identity (Optional[str]): Backend identity associated with the session, if applicable.
        controller (EndpointController): Controller instance for file operations
        created_at (float): Unix timestamp when session was created
        expires_at (float): Unix timestamp when session expires
        last_used (float): Unix timestamp of last session activity
        status (SessionStatus): Current session state
        token (str): JWT token for session authentication
    """
    id: str
    identity: str | None
    controller: EndpointController
    created_at: float
    expires_at: float 
    last_used: float
    status: SessionStatus
    token: str


class SessionsCollection:
    """
    Manages all active sessions, including creation, validation, cleanup,
    and task queuing.
    
    This class implements a singleton pattern through the 'sessions' instance.
    It handles session lifecycle, maintains idle session pools, and runs
    background maintenance tasks.
    
    Attributes:
        max_sessions (int): Maximum number of concurrent sessions
        idle_timeout (int): Seconds before an idle session expires
        task_timeout (int): Maximum seconds for task execution
        jwt_secret (str): Secret key for JWT token signing
        jwt_algorithm (str): Algorithm used for JWT tokens
        _session_stack (Dict[str, Session]): All active sessions by ID
        idle_sessions (deque): Queue of idle sessions for quick assignment
        task_queue (list): Priority queue of pending tasks
        lock (asyncio.Lock): Async lock for thread-safe operations
        total_tasks (int): Counter for total tasks processed
        completed_tasks (int): Counter for successfully completed tasks
        failed_tasks (int): Counter for failed tasks
        _maintenance_task (Optional[asyncio.Task]): Background maintenance task
    """
    
    def __init__(self, max_sessions: int = 20, 
                idle_timeout: int = 900, 
                task_timeout: int = 30,
                jwt_secret: str | None = None,
                jwt_algorithm: str = "HS256"):
        """
        Initialize the sessions collection.
        
        Args:
            max_sessions: Maximum concurrent sessions (default: 20)
            idle_timeout: Session idle timeout in seconds (default: 300)
            task_timeout: Task execution timeout in seconds (default: 30)
            jwt_secret: Secret for JWT signing (auto-generated if None)
            jwt_algorithm: JWT signing algorithm (default: "HS256")
        """
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.task_timeout = task_timeout
        self.jwt_secret = jwt_secret or self._generate_jwt_secret()
        self.jwt_algorithm = jwt_algorithm
        
        self._session_stack: Dict[str, Session] = {}
        self.idle_sessions: deque = deque()
        self.task_queue: list = []
        self.lock = asyncio.Lock()
        
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self._maintenance_task: asyncio.Task | None = None

    def get_available_controllers(self) -> list:
        """
        Return a list of names of all available endpoint controllers.

        Returns:
            list: A list of controller class names as strings.
        """
        return list(controllers.controllers.keys())

    def _generate_jwt_secret(self) -> str:
        """
        Generate a cryptographically secure random JWT secret.
        
        Returns:
            str: URL-safe random token (32 bytes)
        """
        import secrets
        return secrets.token_urlsafe(32)
    
    def _create_session_token(
        self,
        session_id: str,
        identity: str | None,
    ) -> str:
        """
        Create a JWT token for session authentication.

        Args:
            session_id: Unique session identifier
            identity: Backend identity associated with the session, if any
            expires_at: Token expiration timestamp

        Returns:
            str: Encoded JWT token
        """
        payload = {
            "session_id": session_id,
            "iat": datetime.now(timezone.utc),
            "type": "session",
        }

        if identity is not None:
            payload["identity"] = identity

        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def _verify_session_token(self, token: str) -> Dict | None:
        """
        Verify and decode a session JWT token.
        
        Args:
            token: JWT token to verify
            
        Returns:
            Optional[Dict]: Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            if payload.get('type') != 'session':
                return None
            return payload
        except jwt.InvalidTokenError:
            return None
    
    async def add(self, request: SessionInitRequest) -> Session:
        """
        Create a new session from a request.
        
        Args:
            request: Session initialization parameters
            
        Returns:
            Session: Newly created session
            
        Raises:
            ConnectionError: If controller connection fails
        """
        controller = controllers[request]
        if controller is None:
            raise ValueError(f"Unknown controller: {request.controller}")
            
        if not controller.connect():
            raise ConnectionError(f"Failed to connect to {request.server} by {request.controller}")
        
        session_id = str(uuid.uuid4())
        created_at = time.time()
        expires_at = created_at + self.idle_timeout
        identity = getattr(controller, 'identity', None)

        token = self._create_session_token(session_id, identity)
        
        session = Session(
            id=session_id,
            identity=identity,
            controller=controller,
            created_at=created_at,
            expires_at=expires_at,
            last_used=created_at,
            status=SessionStatus.IDLE,
            token=token  
        )
        
        async with self.lock:
            self._session_stack[session_id] = session
            self.idle_sessions.append(session)
        
        return session
    
    async def validate_session(self, token: str) -> str | None:
        """
        Validate a session token and return the session ID if valid.
        
        Args:
            token: JWT token to validate
            
        Returns:
            Optional[str]: Session ID if valid, None otherwise
        """
        payload = self._verify_session_token(token)
        if not payload:
            return None
        
        session_id = payload.get('session_id')
        if not session_id:
            return None
        
        async with self.lock:
            session = self._session_stack.get(session_id)
            if not session or session.status in (SessionStatus.ERROR, SessionStatus.CLOSED):
                return None
            
            if time.time() > session.expires_at:
                return None
            
            new_expires_at = time.time() + self.idle_timeout
            session.expires_at = new_expires_at
            session.last_used = time.time()

            return session_id
    
    async def get_session_by_token(self, token: str) -> Session | None:
        """
        Retrieve a session object by its token.
        
        Args:
            token: JWT session token
            
        Returns:
            Optional[Session]: Session object if valid, None otherwise
        """
        session_id = await self.validate_session(token)
        if not session_id:
            return None
        
        async with self.lock:
            return self._session_stack.get(session_id)
        
    async def close_session_by_token(self, token: str) -> bool:
        """
        Mark a session as closed by its token. The session will be removed
        by the background maintenance task.
        
        Args:
            token: JWT session token
            
        Returns:
            bool: True if session was marked closed, False otherwise
        """
        session_id = await self.validate_session(token)
        if not session_id:
            return False
        async with self.lock:
            session = self._session_stack.get(session_id)
            if session and session.status != SessionStatus.CLOSED:
                # Remove from idle queue if present
                if session in self.idle_sessions:
                    self.idle_sessions.remove(session)
                session.status = SessionStatus.CLOSED
                session.expires_at = time.time()
                return True
        return False
    
    async def clear(self):
        """
        Clear all sessions and pending tasks.
        Used during application shutdown.
        """
        async with self.lock:
            for task in self.task_queue:
                if not task.future.done():
                    task.future.set_exception(
                        RuntimeError("Session pool is being cleared")
                    )
            self.task_queue.clear()
        
            self.idle_sessions.clear()
            
            close_tasks = []
            for session_id in list(self._session_stack.keys()):
                close_tasks.append(self._close_session(session_id))
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
            self.total_tasks = 0
            self.completed_tasks = 0
            self.failed_tasks = 0

    def start_maintenance(self):
        """
        Start the background maintenance task if not already running.
        
        Returns:
            asyncio.Task: The maintenance task
        """
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        return self._maintenance_task

    async def stop_maintenance(self):
        """
        Stop the background maintenance task.
        """
        if self._maintenance_task and not self._maintenance_task.done():
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass            
    
    async def _wait_for_session(self, priority: int) -> Session:
        """
        Wait for an available session with given priority.
        
        Args:
            priority: Task priority (lower = higher priority)
            
        Returns:
            Session: An available session
            
        Raises:
            asyncio.CancelledError: If waiting is cancelled
        """
        future = asyncio.Future()
        task = SessionPriorityTask(
            priority=priority,
            timestamp=time.time(),
            session_id="",
            task=None,
            future=future
        )
        heapq.heappush(self.task_queue, task)
        
        try:
            return await future
        except asyncio.CancelledError:
            if task in self.task_queue:
                self.task_queue.remove(task)
                heapq.heapify(self.task_queue)
            raise
    
    async def _process_task(self, task: SessionPriorityTask):
        """
        Process a task by assigning it an idle session.
        
        Args:
            task: The task to process
        """
        if self.idle_sessions:
            session = self.idle_sessions.popleft()
            session.status = SessionStatus.BUSY
            task.future.set_result(session)
    
    async def _maintenance_loop(self):
        """
        Background maintenance loop that runs periodically.
        Cleans up idle sessions and attempts to recreate error sessions.
        """
        while True:
            await asyncio.sleep(60) 
            logger.debug("Maintenance loop running")
            await self._cleanup_closed_sessions()
            await self._cleanup_idle_sessions()
            await self._recreate_error_sessions()
    
    async def _cleanup_idle_sessions(self):
        """
        Remove and close sessions that have exceeded their expiration time.
        """
        current_time = time.time()
        async with self.lock:
            to_remove = []
            for session in list(self.idle_sessions):
                if current_time > session.expires_at:
                    to_remove.append(session)
                    self.idle_sessions.remove(session)
            if to_remove:
                logger.info(
                    "Removing %d expired sessions: %s",
                    len(to_remove),
                    to_remove,
                )
        for session in to_remove:
            await self._close_session(session.id)
    
    async def _cleanup_closed_sessions(self):
        """
        Remove closed sessions.
        """
        async with self.lock:
            to_remove = []
            for session_id, session in list(self._session_stack.items()):
                if session.status == SessionStatus.CLOSED:
                    to_remove.append(session)
            if to_remove:
                logger.info(
                    "Removing %d closed sessions: %s",
                    len(to_remove),
                    to_remove,
                )
        for session in to_remove:
            await self._close_session(session.id)
    
    async def _recreate_error_sessions(self):
        """
        Attempt to recreate sessions that are in ERROR state.
        
        Safely extracts controller parameters without assuming knowledge
        of controller implementation details.
        """
        async with self.lock:
            for session_id, session in list(self._session_stack.items()):
                if session.status == SessionStatus.ERROR:
                    # Store controller parameters before closing
                    controller_params = {}
                    
                    # Safely extract parameters from controller without knowing its structure
                    if hasattr(session.controller, '__dict__'):
                        # Get all public attributes (non-callable, not starting with '_')
                        for key, value in session.controller.__dict__.items():
                            if not key.startswith('_') and not callable(value):
                                controller_params[key] = value
                    
                    # Close the old session
                    await self._close_session(session_id)
                    
                    try:
                        # Try to recreate using stored parameters
                        if controller_params:
                            # Get the controller class
                            controller_class = controllers[session.controller.__class__.__name__]
                            if controller_class:                               
                                # Create new session request
                                request = SessionInitRequest(
                                    controller=session.controller.__class__.__name__,
                                    **controller_params
                                )
                                
                                # Add new session
                                await self.add(request)
                                logger.info(
                                    "Successfully recreated session %s (identity=%s)",
                                    session_id,
                                    session.identity or "<none>",
                                )
                    except Exception as e:
                        logger.error(
                            "Failed to recreate session %s: %s",
                            session_id,
                            e,
                        )
                        # Session is already removed by _close_session
    
    async def _close_session(self, session_id: str):
        logger.debug(f"_close_session called for {session_id}, stack keys: {list(self._session_stack.keys())}")
        if session_id in self._session_stack:
            try:
                self._session_stack[session_id].controller.disconnect()
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
            try:
                del self._session_stack[session_id]
                logger.debug(
                    "Successfully removed expired session: %s",
                    session_id,
                )
            except Exception as e:
                logger.error(f"Failed to delete {session_id}: {e}")
        else:
            logger.warning(f"Session {session_id} not found in stack")


# Singleton instance for global use
sessions = SessionsCollection()