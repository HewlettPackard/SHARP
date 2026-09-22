# Setup instructions for SHARP

To run SHARP, you'll need one or more hosts or VMs plus at least one execution backend. This guide covers the common host setup first, then links to backend-specific setup notes.

## Get host(s)

* Provision physical hosts or VMs with any of the supported accelerators.
* The rest of the instructions assume a recent Ubuntu-based distribution on those hosts.

## Install uv and Python dependencies

Install `uv`, then create the project environment from the repository root:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
cd sharp
uv sync --extra dev
```

This creates `.venv/` and installs the Python packages pinned in `uv.lock`. The supported Python version is defined in `pyproject.toml`.

## Install host packages

Install the packages needed on the control host for common SHARP workflows:

  ```sh
  sudo apt install curl git make rename
  ```

Install additional system packages only for the features you plan to use:

  ```sh
  # Docker backend or container-based FaaS backends
  sudo apt install docker.io

  # AppImage packaging or local AppImage execution
  sudo apt install fuse libfuse2 appimagetool

  # Native builds for compiled benchmarks
  sudo apt install build-essential

  # MPI backend or MPI benchmarks
  sudo apt install openmpi-bin libopenmpi-dev

  # Specific benchmarks that need extra system libraries
  sudo apt install libcurl4-openssl-dev
  ```

* To run CUDA functions, set up the docker utilities for Nvidia [here](https://docs.nvidia.com/ai-enterprise/deployment-guide/dg-docker.html).

There may be other benchmark-specific prerequisites, documented in each suite's setup guide.

## Configure Docker

* Set up user: `sudo usermod -aG docker $USER && newgrp docker`
* Run it: `sudo systemctl start docker && sudo systemctl enable docker`
* Log in: `docker login`

Please follow the instructions [here](./docker.md) to use Docker as a backend or as the image runtime for packaged functions.

## Set up Kubernetes

This step is only needed for Kubernetes-based backends such as Fission and Knative. Choose one of these:

1. [k3s](./k3s.md): Lightweight Kubernetes distribution for simple single-node or small-cluster deployments.
2. [k8s](./k8s.md): Full Kubernetes deployment.

If using a private docker repository, you may want to set up access like this:

```sh
kubectl create secret docker-registry docker-registry-secret --docker-server=[...] --docker-username=[...] --docker-password=[...] --docker-email=[...]
```


## Set up FaaS

Choose one or more of the following execution environments and install it:

1. [Fission](./fission.md)
2. [Knative](./knative.md)
3. [Docker](./docker.md) for local containerized execution without Kubernetes

## Build benchmark artifacts

SHARP now packages benchmarks from the YAML definitions under `benchmarks/`.

For local artifact creation, use the build tool:

```sh
uv run build -t appimage sleep
uv run build -t docker sleep

# Build an entire suite
uv run build -t docker benchmarks/micro/cpu
```

If you want to push a Docker image to a registry for later deployment, add `--registry`:

```sh
uv run build -t docker --registry <registry> sleep
```

Fission and Knative no longer use a repo-managed deployment directory inside this repository. Instead, deploy the function or service yourself, using the same name as the benchmark you will launch from SHARP. A Docker image built with `uv run build -t docker` can serve as the starting point for those deployments.

Some benchmark implementations also need extra software on the hosts being measured, not just on the control host where you launch SHARP. Check the relevant benchmark suite documentation before running large experiments.

## Set up MPI

This step is optional and only required for MPI benchmarks or the MPI backend. Please follow the instructions [here](./MPI.md).
