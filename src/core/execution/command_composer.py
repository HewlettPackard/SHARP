"""
Command composer for benchmark execution.

Translates backend configurations and benchmark arguments into shell commands,
with support for macro expansion, backend chaining (MPI + profiling tools),
and host round-robin for SSH-like backends.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import os
import platform
import tempfile
from typing import Any, Dict, List, Optional


class CommandComposer:
    """
    Composes shell commands from backend configurations and benchmark specifications.

    Public interface:
    - compose(backends, copies): Main entry point for command generation
    - Supports single, MPI, parallel, and chained (composed) backends

    Handles:
    - Macro expansion ($CMD, $MPL, $ARGS, $TASK, $FN, $HOST, $MPIFLAGS, $TMP_PATH)
    - Backend chaining (outer/left backends wrap inner/right backends, forming composition)
    - MPI vs non-MPI backend detection and command generation
    - Host round-robin for SSH-like backends
    """

    def __init__(self, backend_options: Dict[str, Dict[str, Any]], benchmark_spec: Optional[Dict[str, Any]] = None,
                 hosts: Optional[List[str]] = None) -> None:
        """
        Initialize command builder from backend options and benchmark specifications.

        Args:
            backend_options: Dict mapping backend name to config {name: {command_template, ...}}
            benchmark_spec: Optional benchmark specification with new schema:
                {entry_point: str, args: list, task: str}
                Can be None for sys spec collection.
            hosts: List of hosts for round-robin (defaults to localhost)
        """
        self.backend_options = backend_options
        benchmark_spec = benchmark_spec or {}
        self.task = benchmark_spec.get("task", "")
        self.func = benchmark_spec.get("entry_point", "")
        args_value = benchmark_spec.get("args", [])
        self.args = " ".join(args_value) if isinstance(args_value, list) else str(args_value)
        self.hosts = hosts or [platform.node()]

        # Will be set when compose() is called with backend_names
        self.mpiflags = ""
        self.tmp_path = "/tmp/"

        # Create unique temporary directory for MPI outputs if needed later
        self.unique_tmp_dir = tempfile.mkdtemp(prefix="mpi-stats-")

    def _get_command_template(self, config: Dict[str, Any], default: str = "", template_key: str = "run") -> str:
        """Get command template from backend config with backward compatibility.

        Args:
            config: Backend configuration dict
            default: Default template if none found
            template_key: Which template to use ('run' for normal commands, 'run_sys_spec' for system specs)

        Returns:
            Command template string
        """
        # For backward compatibility, try command_template first, then the specified key
        result = config.get("command_template") or config.get(template_key, default)
        return str(result) if result else default

    def compose(self, backend_names: List[str], copies: int = 1, template_key: str = "run") -> List[str]:
        """
        Main entry point: compose commands from backends (handles all variants).

        Automatically detects:
        - Single backend: generate direct or MPI command
        - Multiple backends: compose via chaining (outer/left wraps inner/right)

        Args:
            backend_names: List of backend names to compose (left=outermost, right=innermost)
            copies: Number of parallel executions
            template_key: Which backend template to use ('run' for normal commands, 'run_sys_spec' for system specs)

        Returns:
            List of commands ready to execute
        """
        if not backend_names:
            return []

        # Store backend_names and template_key for use in helper methods
        self.backend_names = backend_names
        self.template_key = template_key

        # Update mpiflags and tmp_path from innermost backend
        innermost_name = backend_names[-1]
        innermost_config = self.backend_options.get(innermost_name, {})
        self.mpiflags = innermost_config.get("mpiflags", "")
        self.tmp_path = innermost_config.get("tmp_path", "/tmp/")

        if len(backend_names) == 1:
            # Single backend: direct execution (MPI or parallel)
            return self._build_direct(copies)

        # Multiple backends: compose via chaining
        return self._build_chained(copies)

    def _build_direct(self, copies: int, nested: str = "") -> List[str]:
        """
        Build commands for a single backend (no chaining).

        Chooses between MPI (single command) and parallel (multiple commands).

        Args:
            copies: Number of parallel executions
            nested: Optional nested command to wrap (for backend chaining)
        """
        if self._is_mpi():
            # MPI backend: single command manages concurrency internally
            cmd = self._build_base_command(copies, nested)
            cmd = self._expand_macros(cmd, mpl=copies)
            return [cmd]
        else:
            # Non-MPI backend: multiple commands for parallelism
            commands = []
            for i in range(copies):
                cmd = self._build_base_command(1, nested)
                cmd = self._expand_macros(cmd, copy_index=i, mpl=1)
                commands.append(cmd)
            return commands

    def _build_chained(self, copies: int) -> List[str]:
        """
        Build commands with backend chaining (composition).

        Backends are composed outer-to-inner (left-to-right in list):
        - backend_names[0] is outermost/leftmost (wraps others)
        - backend_names[-1] is innermost/rightmost (direct execution)

        Example: [perf, local] → perf stat -- <local-cmd>
        where local is the innermost (executes the benchmark),
        and perf is the outermost (wraps/profiles the execution)
        """
        # Build innermost command using compose()
        innermost_name = self.backend_names[-1]
        benchmark_spec: Dict[str, Any] = {
            "task": self.task,
            "entry_point": self.func,
            "args": self.args.split() if self.args else [],
        }

        inner_composer = CommandComposer(
            self.backend_options,
            benchmark_spec,
            self.hosts
        )
        # Set backend_names and template_key for inner composer
        inner_composer.backend_names = [innermost_name]
        inner_composer.template_key = getattr(self, 'template_key', 'run')

        # Compose the innermost backend
        inner_commands = inner_composer.compose([innermost_name], copies=copies, template_key=inner_composer.template_key)
        nested_cmd = inner_commands[0] if inner_commands else ""

        # Wrap with outer backends (right-to-left)
        for i in range(len(self.backend_names) - 2, -1, -1):
            outer_name = self.backend_names[i]
            outer_config = self.backend_options.get(outer_name, {})

            # Create a temporary composer just for the outer backend
            outer_composer = CommandComposer(
                self.backend_options,
                benchmark_spec,
                self.hosts
            )
            # Set backend_names and template_key for outer composer
            outer_composer.backend_names = [outer_name]
            outer_composer.template_key = getattr(self, 'template_key', 'run')

            # Get outer backend command template
            outer_template = outer_composer._get_command_template(outer_config, template_key=outer_composer.template_key)

            if i == 0:
                # Outermost: generate final command list
                return outer_composer._build_direct(copies, nested_cmd)
            else:
                # Middle layers: wrap and continue
                wrapped = outer_composer._build_base_command(1, nested_cmd)
                nested_cmd = outer_composer._expand_macros(wrapped, copy_index=0, mpl=1)

        return []

    def _is_mpi(self) -> bool:
        """Check if this backend uses MPI for concurrency."""
        # Get innermost backend config
        if not self.backend_names:
            return False

        innermost_name = self.backend_names[-1]
        config = self.backend_options.get(innermost_name, {})
        template_key = getattr(self, 'template_key', 'run')
        template = self._get_command_template(config, "", template_key=template_key)

        return "mpirun" in template or "mpiexec" in template or "$MPL" in template

    def _build_base_command(self, copies: int, nested: str = "") -> str:
        """
        Build base command with $CMD/$SPEC_COMMAND, $MPL placeholders and optional nested wrapper.

        Replaces:
        - $CMD/$SPEC_COMMAND with nested command (or function call if no nested)
        - $MPL with number of copies for MPI
        """
        # Get innermost backend config
        if not self.backend_names:
            return f"{self.func} {self.args}".strip()

        innermost_name = self.backend_names[-1]
        config = self.backend_options.get(innermost_name, {})
        template_key = getattr(self, 'template_key', 'run')
        run_cmd = self._get_command_template(config, "$CMD", template_key=template_key)

        # Determine which placeholder to use based on template key
        placeholder = "$SPEC_COMMAND" if template_key == "run_sys_spec" else "$CMD"

        if nested:
            # Wrapping: placeholder becomes the nested command
            cmd = run_cmd.replace(placeholder, nested)
        else:
            # Direct execution: placeholder becomes function call
            # Path handling follows standard shell behavior:
            # - Absolute path (/bin/echo) → use as-is
            # - Relative path (./nope.py, ../bin/app) → use as-is
            # - Command name (echo) → search PATH (use as-is, shell will find it)
            # This means we ONLY prepend "./" if the name looks like a local file
            # (contains no path separators and isn't meant to be in PATH)
            # For benchmarks, they should explicitly use "./script.py"
            func_path = self.func
            func_call = f"{func_path} {self.args}".strip()
            cmd = run_cmd.replace(placeholder, func_call)

        # Placeholder for MPL (MPI concurrency) - will be replaced in _expand_macros
        cmd = cmd.replace("$MPL", str(copies))
        return cmd

    def _expand_macros(self, src: str, copy_index: int = 0, mpl: int = 1) -> str:
        """
        Replace all special macros in command string.

        Supported macros:
        - $TASK, $FN, $ARGS: Benchmark identifiers
        - $HOST: Round-robin host selection (by copy_index)
        - $HOST0, $HOST1, etc.: Specific host by index
        - $MPIFLAGS: MPI flags from backend config
        - $TMP_PATH: Temporary directory for outputs
        - $MPL: MPI concurrency level
        """
        result = (
            src.replace("$TASK", self.task)
            .replace("$FN", self.func)
            .replace("$ARGS", self.args)
            .replace("$MPIFLAGS", self.mpiflags)
            .replace("$TMP_PATH", self.unique_tmp_dir)
            .replace("$MPL", str(mpl))
        )

        # Host round-robin: $HOST rotates through self.hosts based on copy_index
        if "$HOST" in result:
            host = self.hosts[copy_index % len(self.hosts)] if self.hosts else "localhost"
            result = result.replace("$HOST", host)

        # Specific host indices: $HOST0, $HOST1, etc.
        for i, host in enumerate(self.hosts):
            result = result.replace(f"$HOST{i}", host)

        return result
