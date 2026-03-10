"""
AppImage artifact builder.

Creates self-contained AppImage bundles for benchmark executables.
AppImages are portable Linux application packages that run on any
distribution without installation.

Build Process:
1. Create AppDir structure with benchmark files
2. Install Python requirements (if any)
3. Run build commands (Makefile or custom commands)
4. Bundle built shared libraries (.so files only)
5. Package with appimagetool

Portability Strategy:
- System libraries (glibc, libm, etc.): Link STATICALLY (-static-libgcc -static-libstdc++)
- Libraries built from source: Link DYNAMICALLY, bundle .so files with rpath
- Only .so files are bundled, not source code or object files
- Use -Wl,-rpath,'$ORIGIN/../lib' so binary finds bundled .so at runtime

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.core.config.schema import BenchmarkConfig
from src.core.packaging.errors import BuildError


class AppImageBuilder:
    """
    Build AppImage artifacts from benchmark configurations.

    Creates portable Linux application packages using appimagetool.
    The resulting AppImage contains all dependencies and can run
    on any compatible Linux distribution.

    Portability Strategy:
    - Static link with system libs: -static-libgcc -static-libstdc++
    - Dynamic link with source-built libs, bundle only .so files
    - Set rpath for runtime library discovery: -Wl,-rpath,'$ORIGIN/../lib'

    Attributes:
        output_dir: Directory for built AppImages (default: build/appimages)
        appimagetool: Path to appimagetool binary
        verbose: If True, stream build output to terminal
    """

    def __init__(self, output_dir: Path | None = None,
                 appimagetool: str | None = None,
                 verbose: bool = False):
        """Initialize AppImage builder.

        Args:
            output_dir: Output directory for AppImages
                        (default: build/appimages in project root)
            appimagetool: Path to appimagetool binary
                          (default: search PATH)
            verbose: If True, stream build output to terminal
        """
        self._output_dir = output_dir
        self._appimagetool = appimagetool or self._find_appimagetool()
        self._verbose = verbose

    def _find_appimagetool(self) -> str:
        """Find appimagetool binary in PATH or common locations."""
        # Check PATH first
        which_result = shutil.which('appimagetool')
        if which_result:
            return which_result

        # Check common locations
        common_paths = [
            '/usr/local/bin/appimagetool',
            os.path.expanduser('~/bin/appimagetool'),
            os.path.expanduser('~/.local/bin/appimagetool'),
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        # Return default name (will fail with clear error if not found)
        return 'appimagetool'

    def _get_output_dir(self) -> Path:
        """Get output directory, creating if needed."""
        if self._output_dir is None:
            from src.core.config.include_resolver import get_project_root
            self._output_dir = get_project_root() / 'build' / 'appimages'
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    def build(self, benchmark: BenchmarkConfig, sources_dir: Path,
              benchmark_name: str) -> Path:
        """
        Build AppImage from benchmark configuration.

        Creates an AppDir structure, installs dependencies, runs build
        commands, and packages into an AppImage.

        Args:
            benchmark: Benchmark configuration
            sources_dir: Path to prepared sources
            benchmark_name: Name of the benchmark

        Returns:
            Path to the built AppImage file

        Raises:
            BuildError: If build fails at any stage
        """
        entry = benchmark.benchmarks[benchmark_name]
        build_config = entry.build

        # Check for AppImage-specific config
        appimage_config = build_config.appimage or {}

        # Get requirements from unified 'requires' field or legacy fields
        requires = build_config.requires
        if requires:
            # Use unified declarative requirements
            python_reqs = requires.python
            system_deps = requires.system
        else:
            # Fall back to legacy fields or AppImage-specific overrides
            python_reqs = appimage_config.get('requirements', []) or build_config.requirements
            system_deps = appimage_config.get('system_deps', []) or build_config.system_deps

        appimage_build_commands = appimage_config.get('build_commands', []) or build_config.build_commands

        # Get benchmark directory (where benchmark.yaml lives) for local source files
        benchmark_dir = None
        if hasattr(benchmark, '_config_path') and benchmark._config_path:
            benchmark_dir = Path(benchmark._config_path).parent

        # Create temporary AppDir structure
        output_dir = self._get_output_dir()
        appdir = output_dir / f'{benchmark_name}.AppDir'

        try:
            # Clean previous build
            if appdir.exists():
                shutil.rmtree(appdir)

            # Create AppDir structure
            self._create_appdir_structure(appdir, benchmark_name)

            # Copy sources to AppDir (external sources + local benchmark files)
            self._copy_sources(sources_dir, appdir, entry.sources, benchmark_dir)

            # Run pre_build hook (before dependencies)
            if build_config.pre_build:
                self._run_hook(appdir, build_config.pre_build, 'pre_build')

            # Install requirements (and warn about system deps)
            self._install_dependencies(appdir, python_reqs, system_deps)

            # Run build commands
            self._run_build_commands(appdir, appimage_build_commands, build_config.makefile)

            # Run post_build hook (after build)
            if build_config.post_build:
                self._run_hook(appdir, build_config.post_build, 'post_build')

            # Copy any libraries built during build phase
            self._copy_built_libraries(appdir)

            # Create AppRun script
            self._create_apprun(appdir, entry.entry_point, entry.args)

            # Create desktop file and icon
            self._create_desktop_entry(appdir, benchmark_name)

            # Package with appimagetool
            appimage_path = self._package_appimage(appdir, benchmark_name)

            return appimage_path

        except Exception as e:
            if isinstance(e, BuildError):
                raise
            raise BuildError(f"AppImage build failed: {e}")

    def _create_appdir_structure(self, appdir: Path, benchmark_name: str) -> None:
        """Create standard AppDir directory structure."""
        (appdir / 'usr' / 'bin').mkdir(parents=True, exist_ok=True)
        (appdir / 'usr' / 'lib').mkdir(parents=True, exist_ok=True)
        (appdir / 'usr' / 'share' / 'applications').mkdir(parents=True, exist_ok=True)
        (appdir / 'usr' / 'share' / 'icons').mkdir(parents=True, exist_ok=True)

    def _copy_sources(self, sources_dir: Path, appdir: Path,
                      sources: list[Any], benchmark_dir: Path | None = None) -> None:
        """Copy source files to AppDir.

        Copies both external sources (downloaded/fetched) and local benchmark
        files (from the benchmark.yaml directory) to the AppDir.

        Args:
            sources_dir: Directory containing fetched external sources
            appdir: AppDir structure to copy into
            sources: List of source specifications (to check if external)
            benchmark_dir: Directory containing benchmark.yaml and local files
        """
        dest = appdir / 'usr' / 'bin'

        # Helper to copy files/dirs
        def copy_item(item: Path, target_dir: Path) -> None:
            # Skip hidden files, benchmark.yaml, and build directories
            if item.name.startswith('.'):
                return
            if item.name in ('benchmark.yaml', '__pycache__', 'build'):
                return

            target = target_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
                # Preserve executable permission
                if os.access(item, os.X_OK):
                    target.chmod(target.stat().st_mode | 0o111)
            elif item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)

        # Copy external sources (downloaded tarballs, git repos, etc.)
        if sources and sources_dir.exists() and sources_dir.is_dir():
            for item in sources_dir.iterdir():
                copy_item(item, dest)

        # Copy local benchmark files (C source, Makefile, Python scripts, etc.)
        if benchmark_dir and benchmark_dir.exists() and benchmark_dir.is_dir():
            for item in benchmark_dir.iterdir():
                copy_item(item, dest)

    def _run_hook(self, appdir: Path, hook_script: str, hook_name: str) -> None:
        """Run a build hook script.

        Args:
            appdir: Path to AppDir structure
            hook_script: Shell command to execute
            hook_name: Name of hook for error messages ('pre_build' or 'post_build')

        Raises:
            BuildError: If hook script fails
        """
        workdir = appdir / 'usr' / 'bin'

        try:
            if self._verbose:
                print(f"  Running {hook_name} hook: {hook_script}")
                result = subprocess.run(
                    hook_script,
                    shell=True,
                    cwd=str(workdir),
                    text=True,
                    timeout=300
                )
            else:
                result = subprocess.run(
                    hook_script,
                    shell=True,
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=300
                )

            if result.returncode != 0:
                stderr = getattr(result, 'stderr', '')
                raise BuildError(f"{hook_name} hook failed: {stderr}")

        except subprocess.TimeoutExpired:
            raise BuildError(f"{hook_name} hook timeout (300s)")
        except Exception as e:
            if isinstance(e, BuildError):
                raise
            raise BuildError(f"{hook_name} hook error: {e}")

    def _install_dependencies(self, appdir: Path, requirements: list[str],
                              system_deps: list[str]) -> None:
        """Install Python requirements into AppDir.

        Args:
            appdir: Path to AppDir structure
            requirements: List of Python packages to install via pip
            system_deps: List of system packages (informational - guides build)
        """
        dest = appdir / 'usr'

        # Install Python requirements using pip with target directory
        if requirements:
            try:
                # Create target directory
                python_lib = dest / 'lib' / 'python'
                python_lib.mkdir(parents=True, exist_ok=True)

                cmd = [
                    'pip', 'install',
                    '--target', str(python_lib),
                ] + requirements

                if self._verbose:
                    print(f"  Running: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        text=True,
                        timeout=300
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                if result.returncode != 0:
                    raise BuildError(f"pip install failed: {getattr(result, 'stderr', '')}")
            except subprocess.TimeoutExpired:
                raise BuildError("pip install timeout")
            except FileNotFoundError:
                raise BuildError("pip not found - install Python pip")

        # System dependencies guidance for AppImage portability
        if system_deps:
            import sys
            print(
                f"Note: System dependencies {system_deps} for AppImage build.\n"
                "  For maximum portability, your build_commands should:\n"
                "  1. Link statically with system libraries: -static-libgcc -static-libstdc++\n"
                "  2. Build library dependencies from source (add tarballs to 'sources')\n"
                "  3. Link dynamically with source-built libs using rpath: -Wl,-rpath,'$ORIGIN/../lib'\n"
                "  4. Copy only the .so files to lib/ (auto-moved to usr/lib in AppImage)\n"
                "  Example: gcc -static-libgcc -I./mylib/include -o app app.c -L./mylib/lib -lmylib -Wl,-rpath,'$ORIGIN/../lib'\n"
                "  See docs/packaging.md for complete examples.",
                file=sys.stderr
            )

    def _run_build_commands(self, appdir: Path, build_commands: list[str],
                            makefile: str | None) -> None:
        """Run Makefile or custom build commands.

        Args:
            appdir: Path to AppDir structure
            build_commands: List of shell commands to run
            makefile: Optional Makefile path
        """
        workdir = appdir / 'usr' / 'bin'

        # Run Makefile if specified
        if makefile:
            makefile_path = workdir / makefile
            if makefile_path.exists():
                try:
                    if self._verbose:
                        print(f"  Running: make -f {makefile_path}")
                        result = subprocess.run(
                            ['make', '-f', str(makefile_path)],
                            cwd=str(workdir),
                            text=True,
                            timeout=600
                        )
                    else:
                        result = subprocess.run(
                            ['make', '-f', str(makefile_path)],
                            cwd=str(workdir),
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                    if result.returncode != 0:
                        raise BuildError(f"make failed: {getattr(result, 'stderr', '')}")
                except subprocess.TimeoutExpired:
                    raise BuildError("make timeout")

        # Run custom build commands
        for cmd in build_commands:
            try:
                if self._verbose:
                    print(f"  Running: {cmd}")
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        cwd=str(workdir),
                        text=True,
                        timeout=600
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        cwd=str(workdir),
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                if result.returncode != 0:
                    raise BuildError(f"Build command failed: {cmd}\n{getattr(result, 'stderr', '')}")
            except subprocess.TimeoutExpired:
                raise BuildError(f"Build command timeout: {cmd}")

    def _copy_built_libraries(self, appdir: Path) -> None:
        """Copy libraries built during build phase to usr/lib.

        Build commands may create a 'lib' directory in usr/bin with
        shared libraries. Move these to usr/lib for proper AppImage structure.
        """
        bin_lib = appdir / 'usr' / 'bin' / 'lib'
        usr_lib = appdir / 'usr' / 'lib'

        if bin_lib.exists() and bin_lib.is_dir():
            for item in bin_lib.iterdir():
                target = usr_lib / item.name
                if item.is_file():
                    shutil.copy2(item, target)
                elif item.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
            # Remove the lib directory from bin after copying
            shutil.rmtree(bin_lib)

    def _create_apprun(self, appdir: Path, entry_point: str,
                       args: list[str]) -> None:
        """Create AppRun script for the AppImage."""
        apprun_path = appdir / 'AppRun'

        # Determine interpreter based on entry point
        if entry_point.endswith('.py'):
            interpreter = 'python3'
        else:
            interpreter = ''

        # Default args are only used if no command-line args are provided
        default_args_str = ' '.join(args) if args else ''

        script = f'''#!/bin/bash
# AppRun script for SHARP benchmark
HERE="$(dirname "$(readlink -f "${{0}}")")"
export PATH="$HERE/usr/bin:$PATH"
export PYTHONPATH="$HERE/usr/lib/python:$PYTHONPATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"

# Change to binary directory (matches build environment working directory)
cd "$HERE/usr/bin"

ENTRY_POINT="{entry_point}"
DEFAULT_ARGS="{default_args_str}"

# Use command-line args if provided, otherwise use defaults
if [ $# -gt 0 ]; then
    ARGS="$@"
else
    ARGS="$DEFAULT_ARGS"
fi

if [ -n "{interpreter}" ]; then
    exec {interpreter} "$ENTRY_POINT" $ARGS
else
    exec "./$ENTRY_POINT" $ARGS
fi
'''
        apprun_path.write_text(script)
        apprun_path.chmod(0o755)

    def _create_desktop_entry(self, appdir: Path, benchmark_name: str) -> None:
        """Create .desktop file and placeholder icon."""
        # Desktop entry
        desktop_path = appdir / f'{benchmark_name}.desktop'
        desktop_content = f'''[Desktop Entry]
Name={benchmark_name}
Exec=AppRun
Icon={benchmark_name}
Type=Application
Categories=Development;Science;
'''
        desktop_path.write_text(desktop_content)

        # Placeholder icon (256x256 PNG would be ideal, but SVG works)
        icon_path = appdir / f'{benchmark_name}.png'
        # Create a minimal 1x1 PNG placeholder
        # In production, benchmarks should provide their own icons
        if not icon_path.exists():
            # Create minimal placeholder (empty file as fallback)
            icon_path.touch()

    def _package_appimage(self, appdir: Path, benchmark_name: str) -> Path:
        """Package AppDir into AppImage using appimagetool."""
        output_dir = self._get_output_dir()
        appimage_path = output_dir / f'{benchmark_name}-x86_64.AppImage'

        try:
            # Check if appimagetool is available
            if not shutil.which(self._appimagetool):
                raise BuildError(
                    f"appimagetool not found at '{self._appimagetool}'. "
                    "Install from https://github.com/AppImage/AppImageKit/releases"
                )

            result = subprocess.run(
                [self._appimagetool, str(appdir), str(appimage_path)],
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'ARCH': 'x86_64'}
            )

            if result.returncode != 0:
                raise BuildError(f"appimagetool failed: {result.stderr}")

            # Make executable
            appimage_path.chmod(0o755)

            return appimage_path

        except subprocess.TimeoutExpired:
            raise BuildError("appimagetool timeout")
        except FileNotFoundError:
            raise BuildError(
                f"appimagetool not found at '{self._appimagetool}'. "
                "Install from https://github.com/AppImage/AppImageKit/releases"
            )
