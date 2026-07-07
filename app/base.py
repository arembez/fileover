"""
app/base.py

Abstract base classes for FileOver microservice.
Defines the interface that all endpoint controllers must implement.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type
from io import BytesIO
from pydantic import BaseModel


class EndpointController(ABC):
    """
    Abstract base class for all endpoint controllers.
    
    Defines the interface for file operations across different protocols.
    All concrete controller implementations must inherit from this class
    and implement all abstract methods.
    
    The controller manages a connection to a remote resource and provides
    methods for file system operations like listing, downloading, uploading,
    and managing files and directories.
    """
    
    @classmethod
    def get_required_params(cls) -> List[str]:
        """
        Return a list of required parameter names.
        Override this if you want simple presence validation without Pydantic.
        """
        return []
    
    @classmethod
    def get_parameter_model(cls) -> Optional[Type[BaseModel]]:
        """
        Return a Pydantic model class for validating initialization parameters.
        Override in subclasses to define specific validation requirements.
        
        If returns None, parameters are accepted without validation.
        """
        return None
    
    @abstractmethod
    def __init__(self, **kwargs):
        """
        Initialize the controller with connection parameters.
        
        Args:
            **kwargs: Protocol‑specific connection parameters.
        """
        pass

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the resource.
        
        Returns:
            bool: True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def disconnect(self):
        """
        Close connection and release resources.
        Should be called when the controller is no longer needed.
        """
        pass

    @property
    @abstractmethod
    def connected(self) -> bool:
        """
        Get the current connection state.
        
        Returns:
            bool: True if connected to the resource, False otherwise.
        """
        pass

    @abstractmethod
    def list_directory(self, path: str = "") -> List[Dict[str, Any]]:
        """
        List contents of a directory.
        
        Args:
            path: Directory path relative to resource root (default: "").
            
        Returns:
            List[Dict[str, Any]]: List of items with metadata:
                - name (str): Item name
                - is_directory (bool): Whether item is a directory
                - size (int): File size in bytes (0 for directories)
                - modified (float): Last modification timestamp
                - path (str): Full path to the item
        """
        pass

    @abstractmethod
    def download(self, path: str, offset: int = 0, length: Optional[int] = None) -> BytesIO:
        """
        Download file content as BytesIO.
        
        Args:
            path: Path to the file to download.
            offset: Starting byte offset (default: 0).
            length: Number of bytes to download.
                   If None, download from offset to end of file.
            
        Returns:
            BytesIO: File content as a bytes buffer.
            
        Raises:
            Exception: If file not found, download fails, or offset/length invalid.
        """
        pass

    @abstractmethod
    def upload(self, path: str, data: BytesIO) -> None:
        """
        Upload data to a file. Overwrites if exists.
        
        Args:
            path: Path where to upload the file.
            data: File content to upload.
            
        Raises:
            Exception: If upload fails.
        """
        pass

    @abstractmethod
    def create_directory(self, path: str):
        """
        Create a new directory.
        
        Args:
            path: Path where to create the directory.
            
        Raises:
            Exception: If directory creation fails or path already exists.
        """
        pass

    @abstractmethod
    def delete(self, path: str):
        """
        Delete a file or empty directory.
        
        Args:
            path: Path to the item to delete.
            
        Raises:
            Exception: If deletion fails or directory is not empty.
        """
        pass

    @abstractmethod
    def rename(self, path: str, new_name: str):
        """
        Rename or move a file/directory within the same resource.
        
        Args:
            path: Current path of the item.
            new_name: New name for the item.
            
        Raises:
            Exception: If rename fails or destination already exists.
        """
        pass

    @abstractmethod
    def copy(self, source: str, destination: str) -> None:
        """
        Copy a file or directory from source to destination within the same resource.
        
        Args:
            source: Source path.
            destination: Destination path.
            
        Raises:
            NotImplementedError: If the underlying protocol doesn't support copying.
            Exception: If copy fails.
        """
        raise NotImplementedError("Copy operation not supported by this controller")

    @abstractmethod
    def get_metadata(self, path: str) -> Dict[str, Any]:
        """
        Get metadata of a file or directory.
        
        Args:
            path: Path to the item.
            
        Returns:
            Dict[str, Any]: Item metadata with protocol-dependent keys/values.
                
        Raises:
            Exception: If item not found.
        """
        pass

    @abstractmethod
    def set_metadata(self, path: str, metadata: Dict[str, Any]) -> None:
        """
        Set metadata attributes for a file or directory.
        
        Args:
            path: Path to the item.
            metadata: Dictionary of metadata keys/values to set.
                      Supported keys are protocol‑dependent.
            
        Raises:
            NotImplementedError: If metadata operations are not supported.
            Exception: If setting metadata fails.
        """
        raise NotImplementedError("Metadata operations not supported by this controller")

    @abstractmethod
    def get_storage_info(self, path: str = "") -> Dict[str, int]:
        """
        Get storage capacity information for the resource.
        
        Args:
            path: Optional path to a directory to get info for a specific mount point.
                 If empty, returns info for the root of the resource.
            
        Returns:
            Dict[str, int]: Dictionary with keys:
                - total (int): Total space in bytes
                - free (int): Available space in bytes
                - used (int): Used space in bytes (total - free)
                
        Raises:
            NotImplementedError: If storage info is not supported.
            Exception: If info retrieval fails.
        """
        raise NotImplementedError("Storage info not supported by this controller")

    @abstractmethod
    def path_exists(self, path: str) -> bool:
        """
        Check if path exists on the resource.
        
        Args:
            path: Path to check.
            
        Returns:
            bool: True if path exists, False otherwise.
        """
        pass

    @abstractmethod
    def is_directory(self, path: str) -> bool:
        """
        Check if path is a directory.
        
        Args:
            path: Path to check.
            
        Returns:
            bool: True if path exists and is a directory, False otherwise.
        """
        pass

    @abstractmethod
    def get_size(self, path: str) -> int:
        """
        Get size of file in bytes.
        
        Args:
            path: Path to the file.
            
        Returns:
            int: File size in bytes, 0 if path is directory or doesn't exist.
        """
        pass