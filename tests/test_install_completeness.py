
#!/usr/bin/env python3
"""
Tests to ensure that SHARP can run representative built-in function with all backends.

This suite verifies that the installation of SHARP was complete in the sense
that all of its built-in functions can be run with all of its backends.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import unittest
import os
import subprocess
from parameterized import parameterized
try:
    from tests.command_test_case import CommandTestCase  # type: ignore
except:
    from command_test_case import CommandTestCase  # type: ignore

os.environ["HWLOC_COMPONENTS"] = "-gl" # Get rid of pesky X11 warning in MPI

"""
All combinations of functions and backends to run
"""
fn_combinations = [
        { "fn": "nope", "args": "", "backends": [ "local", "docker", "knative", "fission", "mpi", "ssh"] },
        { "fn": "bounce", "args": "hello world", "backends": [ "local" ] },
        { "fn": "mpi-pingpong-single", "args": "1000", "backends": [ "mpi" ] },
        { "fn": "cuda-inc", "args": "10000", "backends": [ "local", "docker", "knative" ] },
        { "fn": "rodinia-omp", "args": "backprop", "backends": [ "docker" ] },
        { "fn": "ollama", "args": "hello world", "backends": [ "docker" ] }
]

backend_opts = {
        "local": "",
        "docker": "-f backends/docker.yaml",
        "fission": "-f backends/fission.yaml",
        "knative": "-f backends/knative.yaml",
        "mpi": "-f backends/mpi.yaml -j '{ \"backend_options\": { \"mpi\": { \"mpiflags\": \"--host localhost:4\" } } }' --mpl 2",
        "ssh": "-f backends/ssh.yaml -j '{ \"backend_options\": { \"ssh\": { \"hosts\": \"localhost\", \"run\": \"ssh $HOST \\\"source /home/frachten/sharp/venv-sharp/bin/activate && $CMD $ARGS\\\"\\n\" } } }'"
}


class CompleteFunctionTests(CommandTestCase):
    """Tests to ensure launcher.py can run all built-in functions with all backends."""
    all_combinations = [ (f"{_['fn']}_{backend}", backend, _['fn'], _['args']) \
            for _ in fn_combinations for backend in _["backends"] ]

    def check_docker_container(self, fn: str) -> bool:
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

    @parameterized.expand(all_combinations)
    def test_install(self, name, backend, fn, args):
        """Test that launcher can run for a given combination of backend and function."""
        # Check if Docker container exists when using docker backend
        if backend == "docker" and not self.check_docker_container(fn):
            self.skipTest(
                f"Docker container '{fn}' is not running. "
                f"Start it with: cd fns/{fn} && make prep-docker"
            )

        task_name = self.get_task_name()
        # Use parameterized test name as part of task name for uniqueness
        unique_task = f"{task_name}_{name}"
        # sys_spec.yaml is auto-loaded, backend opts may be empty for local
        includes = backend_opts[backend] if backend_opts[backend] else ""
        cmd = f"-v {includes} -e {self._expname} -t {unique_task} -b {backend} {fn} {args}"
#        print("\n./launcher/launch.py", cmd)
        stdout, stderr, returncode = self.run_launcher(cmd)
        self.assert_command_success(stdout, returncode, expect_output=True)
        self.assertEqual(stderr, "", "Expected empty stderr")



#####################################################################
if __name__ == "__main__":
    unittest.main()
