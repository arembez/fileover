"""
app/main.py

Main entry point for FileOver microservice.
Initializes FastAPI application, configures CORS, sets up routes,
and manages application lifecycle.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from app import __title__, __version__, __description__
from app.http_routes import router
from app.sessions_collection import sessions
from app.exceptions import (
    ControllerError, PathNotFoundError, NotADirectoryError, IsADirectoryError,
    PermissionDeniedError, FileTypeNotAllowedError, FileSizeExceededError,
    ConnectionError, OperationNotSupportedError
)

# Configure logging format
logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Set logging level based on DEBUG environment variable
if (os.getenv("DEBUG", "false").lower() == "true"):
    logging.basicConfig(level=logging.DEBUG, format=logging_format)
else:
    logging.basicConfig(level=logging.INFO, format=logging_format)
    
logger = logging.getLogger(__name__)


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to catch all exceptions and return clean responses.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            # Map controller exceptions to HTTP responses
            if isinstance(exc, PathNotFoundError):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, NotADirectoryError):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, IsADirectoryError):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, (PermissionDeniedError, FileTypeNotAllowedError)):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, FileSizeExceededError):
                return JSONResponse(
                    status_code=413,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, ConnectionError):
                return JSONResponse(
                    status_code=503,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, OperationNotSupportedError):
                return JSONResponse(
                    status_code=501,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": str(exc)}
                )
            elif isinstance(exc, ControllerError):
                # Catch-all for other controller errors
                logger.warning(f"Controller error: {exc}")
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": str(exc)}
                )
            
            # For unexpected errors, log and return generic error
            logger.error(f"Unexpected error: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"}
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown lifecycle events.
    
    Args:
        app (FastAPI): The FastAPI application instance
        
    Yields:
        None: Control returns to FastAPI during normal operation
        
    Handles:
        - Startup: Logs service info and starts session maintenance
        - Shutdown: Stops maintenance and clears all sessions
        - Errors: Logs failures without breaking the application
    """
    try:
        logger.info(f"Starting up {app.title} v{app.version}")
        logger.info(f"{app.description}")
        sessions.start_maintenance()
        yield
    except Exception as e:
        logger.error(f"{app.title} failed: {e}")
        yield
    finally:
        logger.info("Shutting down clients...")
        await sessions.stop_maintenance()
        await sessions.clear()
        logger.info("Clients disconnected")


# Initialize FastAPI application with metadata
app = FastAPI(
    title=__title__,
    description=__description__,
    version=__version__,  
    lifespan=lifespan
)


# Configure CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # Allow all origins
    allow_credentials=True,         # Allow cookies in cross-origin requests
    allow_methods=["*"],            # Allow all HTTP methods
    allow_headers=["*"],            # Allow all headers
)

# Add exception handler middleware to catch all exceptions
app.add_middleware(ExceptionHandlerMiddleware)


# Include all API routes from http_routes module
app.include_router(router)


@app.get("/")
async def root():
    """
    Root endpoint providing basic service information and listing all available endpoints.
    """
    # Collect all routes for documentation (excluding the root itself to avoid recursion)
    endpoints = []
    for route in app.routes:
        if route.path != "/":
            endpoints.append({
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods) if hasattr(route, "methods") else ["GET"]
            })
    
    return {
        "service": app.title,
        "version": app.version,
        "status": "running",
        "endpoints": endpoints
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "healthy",
        "sessions": len(sessions._session_stack)
    }