# app/exceptions.py
class ControllerError(Exception):
    """Base exception for controller errors."""
    pass

class PathNotFoundError(ControllerError):
    """Path does not exist."""
    pass

class NotADirectoryError(ControllerError):
    """Path is not a directory when directory was expected."""
    pass

class IsADirectoryError(ControllerError):
    """Path is a directory when file was expected."""
    pass

class PermissionDeniedError(ControllerError):
    """Permission denied for the operation."""
    pass

class FileTypeNotAllowedError(ControllerError):
    """File extension is not allowed."""
    pass

class FileSizeExceededError(ControllerError):
    """File size exceeds maximum allowed."""
    pass

class ConnectionError(ControllerError):
    """Connection to server failed."""
    pass

class OperationNotSupportedError(ControllerError):
    """Operation is not supported by this controller."""
    pass