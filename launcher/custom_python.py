#!/usr/bin/env python3
"""
Custom Python launcher implementation.

This launcher loads and uses Python backend classes directly from Python files.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from launcher import Launcher
from typing import Dict, Any, List, Type, cast, Optional
import os
import importlib.util


class CustomPythonLauncher(Launcher):
    """A launcher that loads its implementation from a Python file.

    This class serves as a wrapper around other Python launcher implementations.
    Instead of implementing launcher functionality directly, it:
    1. Dynamically loads a Python file containing a launcher implementation
    2. Instantiates the launcher class from that file
    3. Delegates all operations to that instance
    """

    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """Initialize Python backend launcher.

        Args:
            backend: identifier of current backend
            options: dictionary of all options
        """
        super().__init__(backend, options)
        self._impl: Launcher

        bopts: Dict[str, Any] = options.get("backend_options", {})
        assert backend in bopts, f"Can't have a custom backend {backend} without an options section for it"

        backend_config = bopts[backend]
        assert "file_path" in backend_config, f"Python backend {backend} requires a file_path"

        try:
            file_path = backend_config["file_path"]

            # Get module name from file path
            module_name = os.path.splitext(os.path.basename(file_path))[0]

            # Load the module from file path
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise Exception(f"Could not load {file_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Try different class name variations
            class_names = [
                backend,  # exact backend name
                backend + "Launcher"  # backend name with Launcher suffix
            ]

            # Find and instantiate the launcher class
            impl_class: Optional[Type[Launcher]] = None

            for class_name in class_names:
                if hasattr(module, class_name):
                    impl_class = cast(Type[Launcher], getattr(module, class_name))
                    break

            if impl_class is None:
                raise Exception(f"Backend class {backend} not found in {file_path}")

            self._impl = impl_class(backend, options)

        except Exception as e:
            raise Exception(f"Failed to load Python backend from {file_path}: {str(e)}")

    def reset(self) -> None:
        """Reset the backend state."""
        self._impl.reset()

    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """Return execution string from current and nested commands."""
        return self._impl.run_commands(copies, nested)

    def sys_spec_commands(self) -> Dict[str, str]:
        """Return system specification commands."""
        return self._impl.sys_spec_commands()
