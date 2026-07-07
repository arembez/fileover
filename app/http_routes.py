"""
app/http_routes.py

HTTP API routes for FileOver microservice.
Provides REST endpoints for all file operations defined in EndpointController.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import os
from fastapi import APIRouter, HTTPException, Header, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional
from urllib.parse import quote

from app.types import SessionInitRequest, SessionResponse, ErrorResponse
from app.auth import auth
from app.sessions_collection import sessions

router = APIRouter()


# ----------------------------------------------------------------------
# Session management
# ----------------------------------------------------------------------

@router.post("/init", 
             response_model=SessionResponse,
             responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def init_session(request: SessionInitRequest):
    """
    Initialize a new session with the specified controller.
    
    Creates a new session using the provided credentials and controller type.
    Returns a JWT token for authenticating subsequent requests.
    
    Args:
        request (SessionInitRequest): Session initialization parameters including
                                    username, password, server, and controller type
                                    
    Returns:
        SessionResponse: Contains session ID, JWT token, expiry time, and identity info
        
    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If session initialization fails due to server error
    """
    try:        
        session = await sessions.add(request)
        return SessionResponse(
            session_id=session.id,
            token=session.token,
            expires_at=session.expires_at,
            identity=session.identity
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Session initialization failed: {str(e)}"
        )
        
@router.post("/close")
async def close(authorization: Optional[str] = Header(None)):
    """
    Close an existing session by invalidating the provided JWT token.
    
    Terminates the session associated with the bearer token included in the Authorization header.
    After successful logout, the token will no longer be accepted for subsequent requests.
    
    Args:
        authorization (Optional[str]): The Authorization header containing a Bearer token.
                                    Automatically extracted from the request header.
    
    Returns:
        dict: A success response with `success: True` and a confirmation message.
    
    Raises:
        HTTPException 401: If the Authorization header is missing, invalid, 
                        or the token is expired/invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    closed = await sessions.close_session_by_token(token)
    if not closed:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {"success": True, "message": "Session closed"}

# ----------------------------------------------------------------------
# File operations (matching EndpointController methods)
# ----------------------------------------------------------------------

@router.get("/files")
@router.get("/files/{path:path}")
@auth.context
async def list_directory(path: str = "", authorization: Optional[str] = Header(None), session = None):
    """
    List contents of a directory.
    
    Requires valid session token.
    
    Args:
        path: Directory path relative to root (default: "").
        
    Returns:
        dict: Success status and list of items with metadata.
    """
    files = session.controller.list_directory(path)
    return {"success": True, "data": files}


@router.get("/download/{path:path}")
@auth.context
async def download(
    path: str,
    offset: int = Query(0, ge=0, description="Starting byte offset"),
    length: Optional[int] = Query(None, gt=0, description="Number of bytes to download"),
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Download a file (optionally a byte range).
    
    Requires valid session token.
    
    Args:
        path: Path to the file.
        offset: Starting byte offset.
        length: Number of bytes to download (None = until EOF).
        
    Returns:
        StreamingResponse: File content.
        
    Raises:
        404: If file not found.
        416: If range not satisfiable.
    """
    try:
        file_data = session.controller.download(path, offset, length)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if "range" in str(e).lower() or "offset" in str(e).lower():
            raise HTTPException(status_code=416, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    filename = os.path.basename(path)
    encoded_filename = quote(filename)

    return StreamingResponse(
        file_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(file_data.getbuffer().nbytes)
        }
    )


@router.post("/upload/{path:path}")
@auth.context
async def upload(
    path: str,
    file: UploadFile = File(..., description="File to upload"),
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Upload a file. Overwrites if exists.
    
    Requires valid session token.
    
    Args:
        path: Destination path.
        file: File to upload.
        
    Raises:
        400: If file type not allowed.
    """
    try:
        contents = await file.read()
        from io import BytesIO
        data = BytesIO(contents)
        session.controller.upload(path, data)
    except Exception as e:
        if "not allowed" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "File uploaded successfully"}


@router.post("/directory")
@auth.context
async def create_directory(
    path: str = Query(..., description="Path where to create the directory"),
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Create a new directory.
    
    Requires valid session token.
    
    Raises:
        400: If directory already exists or path invalid.
    """
    try:
        session.controller.create_directory(path)
    except Exception as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "Directory created successfully"}


@router.delete("/{path:path}")
@auth.context
async def delete(path: str, authorization: Optional[str] = Header(None), session = None):
    """
    Delete a file or empty directory.
    
    Requires valid session token.
    
    Raises:
        404: If item not found.
    """
    try:
        session.controller.delete(path)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "Item deleted successfully"}


@router.put("/rename/{path:path}")
@auth.context
async def rename(
    path: str,
    new_name: str = Query(..., description="New name for the item"),
    authorization: Optional[str] = Header(None), 
    session = None
):
    """
    Rename or move an item within the same resource.
    
    Requires valid session token.
    
    Raises:
        404: If source not found.
        400: If destination already exists.
    """
    try:
        session.controller.rename(path, new_name)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "Item renamed successfully"}


@router.post("/copy")
@auth.context
async def copy(
    source: str = Query(..., description="Source path"),
    destination: str = Query(..., description="Destination path"),
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Copy a file or directory within the same resource.
    
    Requires valid session token.
    
    Raises:
        501: If copy not supported by this controller.
    """
    try:
        session.controller.copy(source, destination)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Copy not supported by this controller")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "Copied successfully"}


@router.get("/metadata/{path:path}")
@auth.context
async def get_metadata(path: str, authorization: Optional[str] = Header(None), session = None):
    """
    Get detailed metadata of a file or directory.
    
    Requires valid session token.
    
    Returns:
        dict: Success status and metadata (name, is_directory, size, last_modified, etc.).
        
    Raises:
        404: If item not found.
    """
    try:
        metadata = session.controller.get_metadata(path)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "data": metadata}


@router.post("/metadata/{path:path}")
@auth.context
async def set_metadata(
    path: str,
    metadata: dict,
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Set metadata attributes for a file or directory.
    
    Requires valid session token. The metadata format is controller‑dependent.
    
    Raises:
        501: If setting metadata not supported.
    """
    try:
        session.controller.set_metadata(path, metadata)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Setting metadata not supported by this controller")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": "Metadata updated"}


@router.get("/storage-info")
@auth.context
async def get_storage_info(
    path: str = Query("", description="Optional path to get info for a specific mount point"),
    authorization: Optional[str] = Header(None),
    session = None
):
    """
    Get storage capacity information.
    
    Requires valid session token.
    
    Returns:
        dict: Success status and storage info (total, free, used).
        
    Raises:
        501: If not supported.
    """
    try:
        info = session.controller.get_storage_info(path)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Storage info not supported by this controller")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "data": info}


@router.get("/exists/{path:path}")
@auth.context
async def path_exists(path: str, authorization: Optional[str] = Header(None), session = None):
    """
    Check if a path exists.
    
    Requires valid session token.
    
    Returns:
        dict: Success status and boolean result.
    """
    exists = session.controller.path_exists(path)
    return {"success": True, "exists": exists}


@router.get("/is-directory/{path:path}")
@auth.context
async def is_directory(path: str, authorization: Optional[str] = Header(None), session = None):
    """
    Check if a path is a directory.
    
    Requires valid session token.
    
    Returns:
        dict: Success status and boolean result.
    """
    is_dir = session.controller.is_directory(path)
    return {"success": True, "is_directory": is_dir}


@router.get("/size/{path:path}")
@auth.context
async def get_size(path: str, authorization: Optional[str] = Header(None), session = None):
    """
    Get size of a file in bytes (returns 0 for directories or non‑existent paths).
    
    Requires valid session token.
    
    Returns:
        dict: Success status and size in bytes.
    """
    size = session.controller.get_size(path)
    return {"success": True, "size": size}


# ----------------------------------------------------------------------
# Health check
# ----------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and current session count.
    """
    return {
        "status": "healthy",
        "sessions": len(sessions._session_stack)
    }