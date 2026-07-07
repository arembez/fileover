"""
app/builtin_controllers/local.py

Local filesystem controller implementation.

Copyright: (c) 2026
MIT License
"""

import pwd
import os
import shutil
import time

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.base import EndpointController
from app.exceptions import (
    PathNotFoundError,
    NotADirectoryError,
    IsADirectoryError,
    FileTypeNotAllowedError,
    FileSizeExceededError,
)

from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class LocalControllerParams(BaseModel):
    root_path: str = Field(..., description="Relative path inside /mnt")
    max_file_size: Optional[int] = Field(None, gt=0)
    allowed_extensions: Optional[List[str]] = Field(None)

    @field_validator('root_path')
    @classmethod
    def validate_root_path(cls, v: str) -> str:
        base = Path("/mnt")
        v = v.lstrip('/')
        resolved = (base / v).resolve()
        
        try:
            resolved.relative_to(base)
        except ValueError:
            raise ValueError(f"Path '{v}' must be inside /mnt, resolved to {resolved}")
        
        if not resolved.exists():
            raise ValueError(f"Path '{resolved}' does not exist")
        if not resolved.is_dir():
            raise ValueError(f"Path '{resolved}' is not a directory")
        
        return str(resolved)
    
class LocalController(EndpointController):
    """
    Local filesystem implementation of EndpointController.
    """

    @classmethod
    def get_parameter_model(cls):
        return LocalControllerParams

    def __init__(
        self,
        root_path: str,
        max_file_size: Optional[int] = None,
        allowed_extensions: Optional[List[str]] = None
    ):
        
        self.root_path = Path(root_path)
        self.max_file_size = max_file_size or 100 * 1024 * 1024
        self.allowed_extensions = allowed_extensions

        self._connected = True
        self.last_used = time.time()
        self.identity = self._get_current_user()

    @staticmethod
    def _get_current_user() -> str:
        """Return the name of the user running the current process."""
        try:
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            return os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if not self.root_path.exists():
            raise PathNotFoundError(f"Root path does not exist: {self.root_path}")

        if not self.root_path.is_dir():
            raise NotADirectoryError(str(self.root_path))

        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def _ensure_connected(self):
        if not self._connected:
            self.connect()
        self.last_used = time.time()

    def _build_path(self, path: str) -> Path:
        p = (self.root_path / path).resolve()

        # Prevent escaping root
        if not str(p).startswith(str(self.root_path)):
            raise PermissionError("Access outside root directory is forbidden")

        return p

    def _check_file_allowed(self, filename: str):
        if not self.allowed_extensions:
            return

        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in self.allowed_extensions:
            raise FileTypeNotAllowedError(filename)

    # ---------------------------------------------------------------------
    # EndpointController implementation
    # ---------------------------------------------------------------------

    def list_directory(self, path: str = "") -> List[Dict[str, Any]]:
        self._ensure_connected()

        directory = self._build_path(path)

        if not directory.exists():
            raise PathNotFoundError(path)

        if not directory.is_dir():
            raise NotADirectoryError(path)

        result = []

        for entry in directory.iterdir():
            stat = entry.stat()

            result.append(
                {
                    "name": entry.name,
                    "is_directory": entry.is_dir(),
                    "size": 0 if entry.is_dir() else stat.st_size,
                    "modified": stat.st_mtime,
                    "path": os.path.join(path, entry.name) if path else entry.name,
                }
            )

        return result

    def download(
        self,
        path: str,
        offset: int = 0,
        length: Optional[int] = None,
    ) -> BytesIO:
        self._ensure_connected()

        file_path = self._build_path(path)

        if not file_path.exists():
            raise PathNotFoundError(path)

        if file_path.is_dir():
            raise IsADirectoryError(path)

        self._check_file_allowed(file_path.name)

        size = file_path.stat().st_size

        if length is None:
            length = size - offset

        if length > self.max_file_size:
            raise FileSizeExceededError(size, self.max_file_size)

        data = BytesIO()

        with open(file_path, "rb") as f:
            f.seek(offset)
            data.write(f.read(length))

        data.seek(0)

        return data

    def upload(self, path: str, data: BytesIO):
        self._ensure_connected()

        file_path = self._build_path(path)

        self._check_file_allowed(file_path.name)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(data.read())

    def create_directory(self, path: str):
        self._ensure_connected()

        self._build_path(path).mkdir(parents=True, exist_ok=True)

    def delete(self, path: str):
        self._ensure_connected()

        p = self._build_path(path)

        if not p.exists():
            raise PathNotFoundError(path)

        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

    def rename(self, path: str, new_name: str):
        self._ensure_connected()

        src = self._build_path(path)
        dst = src.parent / new_name

        src.rename(dst)

    def copy(self, source: str, destination: str):
        self._ensure_connected()

        src = self._build_path(source)
        dst = self._build_path(destination)

        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def get_metadata(self, path: str) -> Dict[str, Any]:
        self._ensure_connected()

        p = self._build_path(path)

        if not p.exists():
            raise PathNotFoundError(path)

        stat = p.stat()

        return {
            "name": p.name,
            "is_directory": p.is_dir(),
            "size": stat.st_size,
            "last_modified": stat.st_mtime,
            "created": stat.st_ctime,
            "path": path,
            "full_path": str(p),
        }

    def set_metadata(self, path: str, metadata: Dict[str, Any]):
        raise NotImplementedError()

    def get_storage_info(self, path: str = "") -> Dict[str, int]:
        p = self._build_path(path)

        usage = shutil.disk_usage(p)

        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        }

    def path_exists(self, path: str) -> bool:
        return self._build_path(path).exists()

    def is_directory(self, path: str) -> bool:
        return self._build_path(path).is_dir()

    def get_size(self, path: str) -> int:
        p = self._build_path(path)

        if not p.exists():
            return 0

        return p.stat().st_size

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()