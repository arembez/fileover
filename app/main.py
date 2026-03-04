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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app import __version__
from app.http_routes import router
from app.sessions_collection import sessions


# Configure logging format
logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Set logging level based on DEBUG environment variable
if (os.getenv("DEBUG", "false").lower() == "true"):
    logging.basicConfig(level=logging.DEBUG, format=logging_format)
else:
    logging.basicConfig(level=logging.INFO, format=logging_format)
    
logger = logging.getLogger(__name__)

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
        sessions.stop_maintenance()
        sessions.clear()
        logger.info("Clients disconnected")


# Initialize FastAPI application with metadata
app = FastAPI(
    title="fileOver",
    description="REST API Gateway for file operations",
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