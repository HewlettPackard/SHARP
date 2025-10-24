"""
Custom exceptions for benchmark packaging operations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""


class BuildError(Exception):
    """Raised when benchmark build fails."""

    pass


class SourceError(Exception):
    """Raised when source fetch/validation fails."""

    pass
