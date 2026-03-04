"""
app/auth.py

Authentication decorator for FastAPI endpoints.
Provides session validation via JWT tokens and injects the session object
into the decorated route handler.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from functools import wraps
from typing import Callable
from fastapi import HTTPException

from app.sessions_collection import sessions


class auth:
    """
    Authentication decorator collection.
    
    Contains decorators for protecting FastAPI endpoints with session-based
    authentication using JWT tokens.
    """
    
    @staticmethod
    def context(func: Callable) -> Callable:
        """
        Decorator that validates the session token and injects the session.
        
        Expects an `authorization` keyword argument containing a Bearer token.
        Validates the token with the sessions collection and, if valid,
        adds a `session` keyword argument with the corresponding Session object.
        
        Args:
            func: The FastAPI endpoint function to decorate.
            
        Returns:
            Callable: Wrapped function that performs authentication before
                      calling the original endpoint.
                      
        Raises:
            HTTPException 401: If the Authorization header is missing, malformed,
                               empty, or if the token is invalid/expired, or if
                               the session cannot be found.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            authorization = kwargs.get('authorization')
            try:
                # Validate header presence and format
                if not authorization or not authorization.startswith('Bearer '):
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid authorization header. Expected 'Bearer <token>'",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                jwt_token = authorization[7:].strip()

                if not jwt_token:
                    raise HTTPException(
                        status_code=401,
                        detail="Empty JWT token",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                # Validate token and get session ID
                session_id = await sessions.validate_session(jwt_token)
                if not session_id:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid or expired JWT token",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                # Retrieve full session object
                session = await sessions.get_session_by_token(jwt_token)
                if not session:
                    raise HTTPException(
                        status_code=401,
                        detail="Session not found",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                # Inject session into the endpoint's keyword arguments
                kwargs['session'] = session
            
            except Exception:
                # Catch-all for any unexpected error during authentication
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Basic"}
                )
            
            return await func(*args, **kwargs)
        
        return wrapper