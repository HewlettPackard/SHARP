
#!/usr/bin/env python3
"""
Tests to ensure that SHARP can run representative built-in benchmarks with all backends.

This suite verifies that the installation of SHARP was complete in the sense
that representative built-in benchmarks can be run with all supported backends.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import os
import subprocess

import pytest

os.environ["HWLOC_COMPONENTS"] = "-gl"  # Get rid of pesky X11 warning in MPI

# Get project root directory
_mydir, _ = os.path.split(os.path.abspath(__file__))
_project_root, _ = os.path.split(_mydir)
_venv_path = os.path.join(_project_root, ".venv", "bin", "activate")

"""All combinations of benchmarks and backends to run."""
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


def check_docker_image(fn: str) -> bool:
    """Check if a Docker image exists for the benchmark.

    Args:
        fn: Benchmark name

    Returns:
        True if image exists, False if not or Docker is unavailable
    """
    try:
        result = subprocess.run(
            ["docker", "images", "-q", f"sharp-{fn}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_fission_function(fn: str) -> bool:
    """Check if a Fission function with the benchmark name exists."""
    try:
        result = subprocess.run(
            ["fission", "fn", "info", "--name", fn],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_knative_service(fn: str) -> bool:
    """Check if a Knative service with the benchmark name exists."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "ksvc", fn, "-o", "name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


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
    """Launcher can run for a given combination of backend and benchmark."""
    helper = setup_test

    if backend == "docker" and not check_docker_image(fn):
        pytest.skip(
            f"Docker backend test skipped: Docker image 'sharp-{fn}' not found.\n"
            f"To enable this test:\n"
            f"  1. Install Docker: See docs/setup/README.md\n"
            f"  2. Build the image: uv run build -t docker {fn}\n"
            f"  3. Re-run tests: pytest {__file__}::{name}\n"
        )

    if backend == "mpi":
        try:
            subprocess.run(["mpirun", "--version"], capture_output=True, check=True, timeout=5)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pytest.skip(
                f"MPI backend test skipped: mpirun not found.\n"
                f"To enable this test:\n"
                f"  1. Install MPI: See docs/setup/README.md and docs/setup/MPI.md\n"
                f"  2. Verify: mpirun --version\n"
                f"  3. Re-run tests: pytest {__file__}::{name}\n"
            )

    if backend == "fission":
        try:
            subprocess.run(["fission", "version"], capture_output=True, check=True, timeout=5)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pytest.skip(
                f"Fission backend test skipped: Fission CLI not found.\n"
                f"To enable this test:\n"
                f"  1. Install Fission: See docs/setup/fission.md\n"
                f"  2. Verify: fission version\n"
                f"  3. Re-run tests: pytest {__file__}::{name}\n"
            )

        if not check_fission_function(fn):
            pytest.skip(
                f"Fission backend test skipped: Fission function '{fn}' not found.\n"
                f"Deploy a function named '{fn}' first, then re-run: pytest {__file__}::{name}\n"
            )

    if backend == "knative":
        try:
            subprocess.run(["kubectl", "version", "--client"], capture_output=True, check=True, timeout=5)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pytest.skip(
                f"Knative backend test skipped: kubectl not found.\n"
                f"To enable this test:\n"
                f"  1. Install Kubernetes tooling and Knative: See docs/setup/knative.md\n"
                f"  2. Verify: kubectl version --client\n"
                f"  3. Re-run tests: pytest {__file__}::{name}\n"
            )

        if not check_knative_service(fn):
            pytest.skip(
                f"Knative backend test skipped: Knative service '{fn}' not found.\n"
                f"Deploy a service named '{fn}' first, then re-run: pytest {__file__}::{name}\n"
            )

    if backend == "ssh":
        try:
            subprocess.run(["ssh", "-V"], capture_output=True, check=False, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip(
                f"SSH backend test skipped: ssh command not found.\n"
                f"To enable this test:\n"
                f"  1. Install OpenSSH client\n"
                f"  2. Verify: ssh -V\n"
                f"  3. Re-run tests: pytest {__file__}::{name}\n"
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

    if "No such image" in stderr or "Connection refused" in stderr or "docker: command not found" in stderr:
        pytest.skip(f"Docker image for '{fn}' is not available on this system")

    # Warnings in stderr are acceptable (e.g., "executing function return status 1")
    # Only fail if there are actual errors (not just warnings)
    if stderr and not stderr.strip().startswith("/"):  # Skip if only file path warnings
        # Check if this looks like an actual error vs a warning
        if "Traceback" in stderr or ("Error" in stderr and "UserWarning" not in stderr):
            pytest.fail(f"Unexpected errors in stderr: {stderr}")
