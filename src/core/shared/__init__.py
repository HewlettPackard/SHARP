"""
Shared utilities: global settings singleton, custom exceptions, common helpers.
"""

from .settings import Settings
from .singleton import singleton

__all__ = ['Settings', 'singleton']
