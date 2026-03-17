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
from typing import Any, Dict, List


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

    def __init__(self, backend_options: Dict[str, Dict[str, Any]], benchmark_spec: Dict[str, Any] | None = None,
                 hosts: List[str] | None = None) -> None:
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

        # If hosts not provided, extract from backend_options (any backend can have hosts)
        if hosts is None:
            hosts = self._extract_hosts_from_backend_options(backend_options)
        self.hosts = hosts or [platform.node()]

        # Will be set when compose() is called with backend_names
        self.mpiflags = ""
        self.tmp_path = "/tmp/"

        # Lazily created temporary directory for MPI outputs
        self.unique_tmp_dir: str | None = None

    def _extract_hosts_from_backend_options(self, backend_options: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Extract hosts from any backend that has a 'hosts' option.

        Searches all backends for 'hosts' configuration and returns the first found.
        Handles comma-separated string format and list format.

        Args:
            backend_options: Backend options dict

        Returns:
            List of hostnames, or empty list if none found
        """
        for backend_config in backend_options.values():
            if isinstance(backend_config, dict) and "hosts" in backend_config:
                hosts_value = backend_config["hosts"]
                if isinstance(hosts_value, list):
                    return hosts_value
                elif isinstance(hosts_value, str):
                    # Handle comma-separated hosts
                    return [h.strip() for h in hosts_value.split(",")]
        return []

    def _guess_backend_name(self, config: Dict[str, Any]) -> str:
        """
        Attempt to identify which backend this config belongs to.

        Searches backend_options to find a key whose value matches this config.
        Falls back to 'unknown' if no match found.

        Args:
            config: Backend configuration dict

        Returns:
            Backend name or 'unknown'
        """
        for name, backend_config in self.backend_options.items():
            if backend_config is config:
                return name
        return "unknown"

    def _get_command_template(self, config: Dict[str, Any], template_key: str = "run") -> str:
        """Get command template from backend config with backward compatibility.

        Args:
            config: Backend configuration dict
            template_key: Which template to use ('run' for normal commands, 'run_sys_spec' for system specs)

        Returns:
            Command template string

        Raises:
            ValueError: If required template is missing from backend config
        """
        # For backward compatibility, try command_template first, then the specified key
        result = config.get("command_template") or config.get(template_key)

        # Validate: all backends passed to CommandComposer MUST have the required template
        # Metric-only backends should never be passed to CommandComposer
        if not result and config:
            backend_name = self._guess_backend_name(config)
            raise ValueError(
                f"Backend '{backend_name}' is missing required '{template_key}' template. "
                f"Did you forget to load backends/{backend_name}.yaml? "
                f"Use: -f backends/{backend_name}.yaml -f your_config.yaml"
            )

        return str(result) if result else ""

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
            result = self._build_direct(copies)
        else:
            # Multiple backends: compose via chaining
            result = self._build_chained(copies)

        return result

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
        # Outer backends should NOT have args - they just wrap the nested command
        empty_benchmark_spec: Dict[str, Any] = {
            "task": "",
            "entry_point": "",
            "args": [],
        }

        for i in range(len(self.backend_names) - 2, -1, -1):
            outer_name = self.backend_names[i]

            # Create a temporary composer just for the outer backend
            # Use empty benchmark_spec so outer backends don't duplicate args
            outer_composer = CommandComposer(
                self.backend_options,
                empty_benchmark_spec,
                self.hosts
            )
            # Set backend_names and template_key for outer composer
            outer_composer.backend_names = [outer_name]
            outer_composer.template_key = getattr(self, 'template_key', 'run')

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
        template = self._get_command_template(config, template_key=template_key)

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
        run_cmd = self._get_command_template(config, template_key=template_key)

        # Determine which placeholder to use based on template key
        placeholder = "$SPEC_COMMAND" if template_key == "run_sys_spec" else "$CMD"

        if nested:
            # Wrapping: placeholder becomes the nested command
            cmd = run_cmd.replace(placeholder, nested)
        else:
            # Direct execution: placeholder becomes function call
            func_path = self.func
            # Don't include args here - they will be added via $ARGS placeholder expansion
            cmd = run_cmd.replace(placeholder, func_path)

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
            .replace("$TMP_PATH", self._resolve_tmp_path(src))
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

    def _resolve_tmp_path(self, command: str) -> str:
        """Ensure $TMP_PATH expands to an existing directory path ending with os.sep.

        Backend templates such as the MPI runner expect $TMP_PATH to reference a
        concrete directory (not just the configured base path) because they write
        per-rank files like ``$TMP_PATH$OMPI_COMM_WORLD_RANK`` and later run
        commands like ``cat $TMP_PATH*`` and ``rm -rf $TMP_PATH``. This helper
        therefore:

        1. Creates (or recreates) a unique temporary directory beneath the
           backend's configured ``tmp_path`` when the placeholder is used.
        2. Returns that directory with a trailing path separator so template
           expansions such as ``$TMP_PATH$OMPI_COMM_WORLD_RANK`` produce valid
           file paths without having to worry about missing slashes.
        """
        if "$TMP_PATH" not in command:
            return ""

        needs_dir = self.unique_tmp_dir is None or not os.path.isdir(self.unique_tmp_dir)
        if needs_dir:
            base_dir = (self.tmp_path or "/tmp/").rstrip(os.sep) or "/tmp"
            self.unique_tmp_dir = tempfile.mkdtemp(prefix="mpi-stats-", dir=base_dir)

        assert self.unique_tmp_dir is not None
        if not self.unique_tmp_dir.endswith(os.sep):
            self.unique_tmp_dir = f"{self.unique_tmp_dir}{os.sep}"

        return self.unique_tmp_dir
