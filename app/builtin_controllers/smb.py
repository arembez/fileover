"""
app/builtin_controllers/smb.py

SMB protocol controller implementation.
Provides file operations over SMB/CIFS shares using smbprotocol library.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import os
import time
import logging
import smbclient
from io import BytesIO
from typing import List, Dict, Optional, Any, Type
from pydantic import BaseModel, Field

from app.base import EndpointController
from app.exceptions import (
    PathNotFoundError, NotADirectoryError, IsADirectoryError,
    PermissionDeniedError, FileTypeNotAllowedError, FileSizeExceededError,
    ConnectionError, OperationNotSupportedError
)

# Suppress verbose smbprotocol logging unless DEBUG is enabled
if not (os.getenv("DEBUG", "false").lower() == "true"):
    logging.getLogger("smbprotocol").setLevel(logging.WARNING)
    logging.getLogger("smbprotocol.transport").setLevel(logging.WARNING)
    logging.getLogger("smbprotocol.session").setLevel(logging.WARNING)
    logging.getLogger("smbprotocol.tree").setLevel(logging.WARNING)
    logging.getLogger("smbprotocol.open").setLevel(logging.WARNING)
    logging.getLogger("smbprotocol.connection").setLevel(logging.WARNING)

class SMBControllerParams(BaseModel):
    server: str = Field(..., min_length=1)
    share: str = Field(..., min_length=1)
    identity: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    port: int = Field(445, ge=1, le=65535)
    root_path: str = Field("")
    max_file_size: Optional[int] = Field(None, gt=0)
    allowed_extensions: Optional[List[str]] = Field(None)

class SMBController(EndpointController):
    """
    SMB protocol implementation of EndpointController.
    Provides file operations on SMB/CIFS shares.
    """

    def __init__(
        self,
        server: str,
        share: str,
        identity: str,
        password: str,
        port: int = 445,
        root_path: str = "",
        max_file_size: Optional[int] = None,
        allowed_extensions: Optional[List[str]] = None
    ):
        """
        Initialize SMB controller with connection parameters.

        Args:
            server: SMB server hostname or IP.
            share: Share name.
            identity: Authentication identity.
            password: Authentication password.
            port: SMB port (default 445).
            root_path: Optional base path within the share.
            max_file_size: Maximum allowed file size for downloads (bytes).
            allowed_extensions: List of allowed file extensions (lowercase, no dot).
        """
        self.server = server
        self.share = share
        self.identity = identity
        self.password = password
        self.port = port
        self.root_path = root_path.strip("/")
        self.max_file_size = max_file_size or 100 * 1024 * 1024
        self.allowed_extensions = allowed_extensions

        self._connected = False
        self.last_used = time.time()

    @classmethod
    def get_parameter_model(cls) -> Optional[Type[BaseModel]]:
        return SMBControllerParams
    
    @property
    def connected(self) -> bool:
        """Return current connection state."""
        return self._connected

    def connect(self) -> bool:
        """Establish connection to the SMB server."""
        try:
            smbclient.ClientConfig(username=self.identity, password=self.password)
            smbclient.register_session(
                server=self.server,
                username=self.identity,
                password=self.password,
                port=self.port,
                connection_timeout=30,
            )
            # Verify connectivity by checking root path
            smbclient.path.exists(self._build_full_path(""))
            self._connected = True
        except Exception as e:
            self._connected = False
            print(f"Connection error for {self.identity}@{self.server}: {e}")
        return self._connected

    def disconnect(self):
        """Close connection and release resources."""
        try:
            smbclient.reset_connection_cache()
        except Exception:
            pass
        finally:
            self._connected = False

    def _build_full_path(self, path: str) -> str:
        """
        Convert a virtual path to a full SMB path.

        Args:
            path: Virtual path relative to root_path.

        Returns:
            Full SMB path suitable for smbclient.
        """
        norm_path = path.strip("/").replace("/", "\\")
        if self.root_path:
            full_relative = os.path.join(self.root_path, norm_path).replace("/", "\\")
        else:
            full_relative = norm_path
        full_path = f"\\\\{self.server}\\{self.share}"
        if full_relative:
            full_path += f"\\{full_relative}"
        return full_path

    def _check_file_allowed(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        if not self.allowed_extensions:
            return True
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        return ext in self.allowed_extensions

    def _ensure_connected(self):
        """Ensure connection is active; reconnect if needed."""
        if not self._connected:
            if not self.connect():
                raise Exception("Lost connection to SMB server")
        self.last_used = time.time()

    # ----------------------------------------------------------------------
    # EndpointController interface implementation
    # ----------------------------------------------------------------------

    def list_directory(self, path: str = "") -> List[Dict[str, Any]]:
        """
        List contents of a directory.
        
        Args:
            path: Directory path relative to root.
        
        Returns:
            List of items with metadata.
        
        Raises:
            PathNotFoundError: If path doesn't exist.
            NotADirectoryError: If path is not a directory.
            ConnectionError: If connection fails.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)
        
        # Check if path exists
        if not smbclient.path.exists(full_path):
            raise PathNotFoundError(f"Path does not exist: {path}")
        
        # Check if it's a directory
        if not smbclient.path.isdir(full_path):
            raise NotADirectoryError(f"Path is not a directory: {path}")
        
        files = []
        try:
            entries = smbclient.scandir(full_path)
            for entry in entries:
                try:
                    stat = entry.stat()
                    files.append(
                        {
                            "name": entry.name,
                            "is_directory": entry.is_dir(),
                            "size": stat.st_size if not entry.is_dir() else 0,
                            "modified": stat.st_mtime,
                            "path": os.path.join(path, entry.name) if path else entry.name,
                        }
                    )
                except Exception as e:
                    print(f"Error processing entry {entry.name}: {e}")
                    continue
        except Exception as e:
            raise ConnectionError(f"Error listing directory {full_path}: {e}")
        
        return files
    
    def download(
        self, path: str, offset: int = 0, length: Optional[int] = None
    ) -> BytesIO:
        """
        Download file content as BytesIO, optionally a byte range.

        Args:
            path: Path to the file.
            offset: Starting byte offset.
            length: Number of bytes to download (None = until EOF).

        Returns:
            BytesIO containing the requested bytes.

        Raises:
            Exception: If file not found, size exceeds limit, or range invalid.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)

        # Check file type allowed
        if not self._check_file_allowed(os.path.basename(path)):
            raise Exception(f"File type not allowed: {os.path.basename(path)}")

        # Get file size and validate range
        try:
            file_stat = smbclient.stat(full_path)
        except Exception as e:
            if "The system cannot find the file specified" in str(e):
                raise Exception(f"File not found: {path}")
            raise e

        file_size = file_stat.st_size
        if offset < 0 or offset >= file_size:
            raise Exception(f"Invalid offset {offset}, file size is {file_size}")

        if length is None:
            length = file_size - offset
        else:
            if length <= 0:
                raise Exception("Length must be positive")
            if offset + length > file_size:
                raise Exception(
                    f"Requested range exceeds file size: offset {offset}, "
                    f"length {length}, file size {file_size}"
                )

        # Enforce max file size if downloading whole file (or large portion)
        if length > self.max_file_size:
            raise Exception(
                f"Requested size ({length} bytes) exceeds maximum allowed "
                f"({self.max_file_size} bytes)"
            )

        # Read the range
        file_bytes = BytesIO()
        try:
            with smbclient.open_file(full_path, mode="rb") as f:
                f.seek(offset)
                file_bytes.write(f.read(length))
        except Exception as e:
            raise Exception(f"Error downloading file: {e}")

        file_bytes.seek(0)
        return file_bytes

    def upload(self, path: str, data: BytesIO) -> None:
        """
        Upload data to a file. Overwrites if exists.

        Args:
            path: Path where to upload the file.
            data: File content to upload.

        Raises:
            Exception: If upload fails.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)
        if not self._check_file_allowed(os.path.basename(path)):
            raise Exception(f"File type not allowed: {os.path.basename(path)}")
        try:
            with smbclient.open_file(full_path, mode="wb") as f:
                f.write(data.read())
        except Exception as e:
            raise Exception(f"Error uploading file: {e}")

    def create_directory(self, path: str):
        """
        Create a new directory.

        Args:
            path: Path where to create the directory.

        Raises:
            Exception: If creation fails.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            smbclient.mkdir(full_path)
        except Exception as e:
            raise Exception(f"Error creating directory: {e}")

    def delete(self, path: str):
        """
        Delete a file or empty directory.

        Args:
            path: Path to the item to delete.

        Raises:
            Exception: If deletion fails.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            smbclient.remove(full_path)
        except Exception as e:
            # If remove fails, try rmdir (for directories)
            try:
                smbclient.rmdir(full_path)
            except Exception:
                raise Exception(f"Error deleting item: {e}")

    def rename(self, path: str, new_name: str):
        """
        Rename or move an item within the same share.

        Args:
            path: Current path.
            new_name: New name (within the same parent directory).

        Raises:
            Exception: If rename fails.
        """
        self._ensure_connected()
        old_full_path = self._build_full_path(path)
        parent_dir = os.path.dirname(path)
        if parent_dir:
            new_path = os.path.join(parent_dir, new_name)
        else:
            new_path = new_name
        new_full_path = self._build_full_path(new_path)
        try:
            smbclient.rename(old_full_path, new_full_path)
        except Exception as e:
            raise Exception(f"Error renaming item: {e}")

    def copy(self, source: str, destination: str) -> None:
        """
        Copy a file or directory within the same share.

        This implementation performs a naive copy by reading the source
        and writing to the destination. For directories, it recursively
        copies contents. May be inefficient for large files.

        Args:
            source: Source path.
            destination: Destination path.

        Raises:
            Exception: If copy fails.
        """
        self._ensure_connected()
        src_full = self._build_full_path(source)
        dst_full = self._build_full_path(destination)

        # Check if source exists
        if not smbclient.path.exists(src_full):
            raise Exception(f"Source not found: {source}")

        # If source is a directory, create destination and copy recursively
        if smbclient.path.isdir(src_full):
            smbclient.mkdir(dst_full)
            for entry in smbclient.scandir(src_full):
                entry_name = entry.name
                src_child = os.path.join(source, entry_name)
                dst_child = os.path.join(destination, entry_name)
                self.copy(src_child, dst_child)
        else:
            # Copy file
            with smbclient.open_file(src_full, mode="rb") as src_f:
                with smbclient.open_file(dst_full, mode="wb") as dst_f:
                    # Copy in chunks to avoid memory issues
                    while True:
                        chunk = src_f.read(65536)
                        if not chunk:
                            break
                        dst_f.write(chunk)

    def get_metadata(self, path: str) -> Dict[str, Any]:
        """
        Get metadata of a file or directory.

        Args:
            path: Path to the item.

        Returns:
            Dictionary with metadata.
        """
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            stat = smbclient.stat(full_path)
            is_dir = smbclient.path.isdir(full_path)
            return {
                "name": os.path.basename(path),
                "is_directory": is_dir,
                "size": stat.st_size,
                "last_modified": stat.st_mtime,
                "created": getattr(stat, "st_ctime", None),
                "path": path,
                "full_path": full_path,
            }
        except Exception as e:
            raise Exception(f"Error getting metadata: {e}")

    def set_metadata(self, path: str, metadata: Dict[str, Any]) -> None:
        """
        Set metadata attributes.

        SMB protocol does not support arbitrary metadata via smbprotocol.
        This implementation raises NotImplementedError.

        Args:
            path: Path to the item.
            metadata: Dictionary of metadata to set.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Metadata operations are not supported by SMBController"
        )

    def get_storage_info(self, path: str = "") -> Dict[str, int]:
        """
        Get storage capacity information.

        Not implemented due to lack of smbprotocol support for disk free space.

        Args:
            path: Optional path (ignored).

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Storage info is not supported by SMBController"
        )

    def path_exists(self, path: str) -> bool:
        """Check if path exists."""
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            return smbclient.path.exists(full_path)
        except Exception:
            return False

    def is_directory(self, path: str) -> bool:
        """Check if path is a directory."""
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            return smbclient.path.isdir(full_path)
        except Exception:
            return False

    def get_size(self, path: str) -> int:
        """Get size of file in bytes."""
        self._ensure_connected()
        full_path = self._build_full_path(path)
        try:
            stat = smbclient.stat(full_path)
            return stat.st_size
        except Exception:
            return 0

    # Context manager support
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()