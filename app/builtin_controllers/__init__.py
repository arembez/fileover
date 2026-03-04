"""
app/builtin_controllers/__init__.py

Built-in controllers package initializer.
Exports available built-in controller implementations.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

from .smb import SMBController

__all__ = [
    'SMBController',
]

# Package metadata
__version__ = '1.0.2'
__author__ = 'Alex Rembez <arembez@gmail.com>'