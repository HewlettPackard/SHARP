"""
Singleton decorator for creating single-instance classes.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Type, TypeVar


T = TypeVar('T')


def singleton(cls: Type[T]) -> Type[T]:
    """
    Decorator that converts a class into a singleton.

    Usage:
        @singleton
        class MyClass:
            def __init__(self):
                pass

        obj1 = MyClass()
        obj2 = MyClass()
        assert obj1 is obj2  # Same instance

    Args:
        cls: The class to make into a singleton

    Returns:
        The decorated class with singleton behavior
    """
    class SingletonWrapper:
        _instances = {}

        def __call__(self, *args: Any, **kwargs: Any) -> T:
            if cls not in self._instances:
                self._instances[cls] = cls(*args, **kwargs)
            return self._instances[cls]

        def __getattr__(self, name: str) -> Any:
            return getattr(cls, name)

        def reset(self) -> None:
            """Reset singleton instance (useful for testing)."""
            self._instances.clear()

    wrapper = SingletonWrapper()
    # Preserve the original class's name and docstring
    wrapper.__name__ = cls.__name__  # type: ignore
    wrapper.__doc__ = cls.__doc__

    return wrapper  # type: ignore
