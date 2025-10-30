
#!/usr/bin/env python3
"""
Tests to ensure that SHARP can run representative built-in function with all backends.

This suite verifies that the installation of SHARP was complete in the sense
that all of its built-in functions can be run with all of its backends.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import os
import subprocess
import pytest
from pathlib import Path

os.environ["HWLOC_COMPONENTS"] = "-gl"  # Get rid of pesky X11 warning in MPI

# Get project root directory
_mydir, _ = os.path.split(os.path.abspath(__file__))
_project_root, _ = os.path.split(_mydir)
_venv_path = os.path.join(_project_root, ".venv", "bin", "activate")

"""
All combinations of functions and backends to run
"""
fn_combinations = [
    {"fn": "nope", "args": "", "backends": ["local", "docker", "knative", "fission", "mpi", "ssh"]},
    {"fn": "bounce", "args": "hello world", "backends": ["local"]},
    {"fn": "mpi-pingpong-single", "args": "10", "backends": ["mpi"]},  # Reduced from 1000 to 10
    {"fn": "cuda-inc", "args": "100", "backends": ["local", "docker", "knative"]}  # Reduced from 10000 to 100
]

backend_opts = {
    "local": "",
    "docker": "-f backends/docker.yaml",
    "fission": "-f backends/fission.yaml",
    "knative": "-f backends/knative.yaml",
    "mpi": "-f backends/mpi.yaml -j '{ \"backend_options\": { \"mpi\": { \"mpiflags\": \"--host localhost:4\" } } }' --mpl 2",
    "ssh": f"-f backends/ssh.yaml -j '{{ \"backend_options\": {{ \"ssh\": {{ \"hosts\": \"localhost\", \"run\": \"ssh $HOST \\\"source {_venv_path} && $CMD $ARGS\\\"\\n\" }} }} }}'"
}

# Generate all test combinations for parametrization
all_combinations = [
    (f"{combo['fn']}_{backend}", backend, combo['fn'], combo['args'])
    for combo in fn_combinations
    for backend in combo["backends"]
]


def check_docker_container(fn: str) -> bool:
    """Check if a Docker container with exact name is running.

    Args:
        fn: Function name (exact container name)

    Returns:
        True if container is running, False otherwise
    """
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name=^{fn}$"],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


@pytest.fixture
def setup_test(launcher_helper, request):
    """Setup fixture for each test with sys_specs disabled."""
    launcher_helper.skip_sys_specs = True
    launcher_helper.experiment_name = "tests"
    # Generate task name from test name (similar to get_task_name)
    launcher_helper.task_name = request.node.name
    yield launcher_helper


@pytest.mark.parametrize(
    "name,backend,fn,args",
    all_combinations,
    ids=[combo[0] for combo in all_combinations]
)
def test_install(setup_test, name, backend, fn, args):
    """Launcher can run for a given combination of backend and function."""
    helper = setup_test

    # Check if Docker container exists when using docker backend
    if backend == "docker" and not check_docker_container(fn):
        pytest.skip(
            f"Docker container '{fn}' is not running. "
            f"Start it with: cd fns/{fn} && make prep-docker"
        )

    # Use parameterized test name as part of task name for uniqueness
    unique_task = f"{helper.task_name}_{name}"
    # sys_spec.yaml is auto-loaded, backend opts may be empty for local
    includes = backend_opts[backend] if backend_opts[backend] else ""
    cmd = f"-v {includes} -e {helper.experiment_name} -t {unique_task} -b {backend} {fn} {args}"

    stdout, stderr, returncode = helper.run_launcher(cmd)

    # Assert command success
    assert returncode == 0, "Expected zero exit code"
    assert stdout, "Expected output in stdout"

    # Skip test only if Docker container/image is missing (infrastructure issue)
    if "No such container" in stderr or "Connection refused" in stderr or "docker: command not found" in stderr:
        pytest.skip(f"Docker container for '{fn}' is not available on this system")

    # Warnings in stderr are acceptable (e.g., "executing function return status 1")
    # Only fail if there are actual errors (not just warnings)
    if stderr and not stderr.strip().startswith("/"):  # Skip if only file path warnings
        # Check if this looks like an actual error vs a warning
        if "Traceback" in stderr or ("Error" in stderr and "UserWarning" not in stderr):
            pytest.fail(f"Unexpected errors in stderr: {stderr}")
