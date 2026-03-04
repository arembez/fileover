"""
app/sessions_collection.py

Session management system for FileOver microservice.
Manages user sessions, controller instances, authentication tokens,
and background maintenance tasks.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import asyncio
import time
import heapq
import uuid
import jwt
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import deque
from typing import Dict, Optional

from app.base import EndpointController
from app.types import SessionInitRequest, SessionStatus, SessionResponse, SessionPriorityTask
from app.controllers_collection import controllers


@dataclass
class Session:
    """
    Represents an active user session with a controller instance.
    
    Attributes:
        id (str): Unique session identifier
        username (str): Username associated with the session
        controller (EndpointController): Controller instance for file operations
        created_at (float): Unix timestamp when session was created
        expires_at (float): Unix timestamp when session expires
        last_used (float): Unix timestamp of last session activity
        status (SessionStatus): Current session state
        token (str): JWT token for session authentication
    """
    id: str
    username: str
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
                idle_timeout: int = 300, 
                task_timeout: int = 30,
                jwt_secret: str = None,
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
        
        self._session_stack: Dict[str, 'Session'] = {}
        self.idle_sessions: deque = deque()
        self.task_queue: list = []
        self.lock = asyncio.Lock()
        
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self._maintenance_task = None

    def _generate_jwt_secret(self) -> str:
        """
        Generate a cryptographically secure random JWT secret.
        
        Returns:
            str: URL-safe random token (32 bytes)
        """
        import secrets
        return secrets.token_urlsafe(32)
    
    def _create_session_token(self, session_id: str, username: str, expires_at: float) -> str:
        """
        Create a JWT token for session authentication.
        
        Args:
            session_id: Unique session identifier
            username: Username associated with the session
            expires_at: Token expiration timestamp
            
        Returns:
            str: Encoded JWT token
        """
        payload = {
            'session_id': session_id,
            'username': username,
            'exp': datetime.fromtimestamp(expires_at),
            'iat': datetime.now(timezone.utc),
            'type': 'session'
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def _verify_session_token(self, token: str) -> Optional[Dict]:
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
        except jwt.ExpiredSignatureError:
            return None
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
        if not controller.connect():
            raise ConnectionError("Failed to connect to SMB server")
        
        session_id = str(uuid.uuid4())
        created_at = time.time()
        expires_at = created_at + self.idle_timeout
        
        token = self._create_session_token(session_id, controller.username, expires_at)
        
        session = Session(
            id=session_id,
            username=controller.username,
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
    
    async def validate_session(self, token: str) -> Optional[str]:
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
            if not session or session.status == SessionStatus.ERROR:
                return None
            
            if time.time() > session.expires_at:
                return None
            
            return session_id
    
    async def refresh_session(self, token: str) -> Optional[SessionResponse]:
        """
        Refresh an existing session, extending its expiration.
        
        Args:
            token: Current session token
            
        Returns:
            Optional[SessionResponse]: New session data if successful, None otherwise
        """
        session_id = await self.validate_session(token)
        if not session_id:
            return None
        
        async with self.lock:
            session = self._session_stack.get(session_id)
            if not session:
                return None
            
            new_expires_at = time.time() + self.idle_timeout
            session.expires_at = new_expires_at
            session.last_used = time.time()
            
            new_token = self._create_session_token(session_id, session.username, new_expires_at)
            session.token = new_token
            
            return SessionResponse(
                session_id=session_id,
                token=new_token,
                expires_at=new_expires_at,
                username=session.username,
                server=session.controller.server,
                share=session.controller.share
            )
    
    async def get_session_by_token(self, token: str) -> Optional[Session]:
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
    
    async def _wait_for_session(self, priority: int) -> 'Session':
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
                                # Create new controller instance
                                new_controller = controller_class(**controller_params)
                                
                                # Create new session request
                                request = SessionInitRequest(
                                    controller=session.controller.__class__.__name__,
                                    **controller_params
                                )
                                
                                # Add new session
                                await self.add(request)
                                print(f"Successfully recreated session for {session.username}")
                    except Exception as e:
                        print(f"Failed to recreate session {session_id}: {e}")
                        # Session is already removed by _close_session
    
    async def _close_session(self, session_id: str):
        """
        Close and remove a session.
        
        Args:
            session_id: ID of the session to close
        """
        if session_id in self._session_stack:
            try:
                await self._session_stack[session_id].controller.disconnect()
            except:
                pass
            del self._session_stack[session_id]


# Singleton instance for global use
sessions = SessionsCollection()