# Setup instructions for SHARP

To run this benchmark, you'll need one or more hosts (physical or virtual), running one or more job-launching backend. This guide provides instructions for a few alternatives for the backends. Docker is assumed for all FaaS alternatives, but can probably be switched for other container systems supported by the backend.

## Get host(s)

* Provision physical hosts or VMs with any of the supported accelerators.
* The rest of the instructions assume Ubuntu 20.04 as the OS on these hosts. The python interpreter should be version 3.9 or higher.
* Install general prerequisites:

  ```sh
  sudo apt install make \
        llvm \
        g++ \
        golang \
        python3-pip \
        python3-venv \
        apt-transport-https \
        libopenmpi-dev \
        libev-dev \
        ca-certificates \
        libfontconfig1-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libtiff-dev \
        libblas-dev liblapack-dev \
        libcurl4-openssl-dev curl \
        rename \
        docker.io  # If required for FaaS
  ```

* To run CUDA functions, set up the docker utilities for Nvidia [here](https://docs.nvidia.com/ai-enterprise/deployment-guide/dg-docker.html).

There may be other application-specific prerequsites, documented in their setup guides.

## Set up proxy

* Add the following to `~/.bashrc`:

  ```sh
  export HTTP_PROXY=http://web-proxy.labs.hpecorp.net:8080/
  export HTTPS_PROXY=http://web-proxy.labs.hpecorp.net:8080/
  export NO_PROXY=localhost,127.0.0.1,10.96.0.0/12,192.168.59.0/24,192.168.39.0/24,192.168.49.0/24
  ```

* Add the following line to `~/.curlrc`:

  ```sh
  proxy=http://web-proxy.labs.hpecorp.net:8080/
  ```

* Create `~/.docker/config.json` with:

  ```json
  {
  "proxies":
  {
    "default":
    {
      "httpProxy":"http://web-proxy.labs.hpecorp.net:8080/",
      "httpsProxy": "http://web-proxy.labs.hpecorp.net:8080/",
      "noProxy": "*.test.example.com,.example2.com,127.0.0.0/8"
    }
  }
  }

  ```

* Run: `sudo mkdir -p /etc/systemd/system/docker.service.d`
* If using a privte docker repository,
* Edit (or create) `/etc/systemd/system/docker.service.d/http-proxy.conf` to include these lines:

  ```conf
  [Service]
  Environment="HTTP_PROXY=http://web-proxy.labs.hpecorp.net:8080/"
  Environment="HTTPS_PROXY=http://web-proxy.labs.hpecorp.net:8080/"
  ```

## Configure Docker

* Set up user: `sudo usermod -aG docker $USER && newgrp docker`
* Run it: `sudo systemcl start docker && systemctl enable docker`
* Log in: `docker login`

Please follow the instructions [here](./docker.md) to use docker as a backend to launch different functions.

## Set up Kubernetes

There are several alternatives here, depending on the scale and complexity of your cluster. Follow the link to configure one of these:

1. [minikube](./minikube.md): A small, self-contained, and relatively simple Kubernetes sandbox for one node.

2. [k3s](./3s.md): Lightweight Kubernetes distribution that skips many components and bundles everything into a single executable.

3. [k8s](./k8s.md): Full Kubernetes deployment.

If using a private docker repository, you may want to set up access like this:

```sh
kubectl create secret docker-registry docker-registry-secret --docker-server=[...] --docker-username=[...] --docker-password=[...] --docker-email=[...]
```


## Set up FaaS

Choose one or more of the following FaaS frameworks and install it:

1. [Fission](./fission.md)
2. [Knative](./knative.md)
3. [Docker](./docker.md)   -- Technically, not serverless, but lets you run functions locally in a container without additional hosts or prerequisites.

## Install Python packages

SHARP requires a few Python packages to be installed, found in the `requirements.txt` file. You can install them all using:

```sh
cd sharp
python3 -m venv venv-sharp
source venv-sharp/bin/activate
venv-sharp/bin/pip3 install -r requirements.txt
```

In addition, some of the benchmarking functions have their own prerequisites that need to be installed *at all the hosts you are benchmarking*, that is, not necessarily the same host you're running SHARP from. Depending on which functions and which backend you're planning to run in your benchmarks, you may need to install some or all of the prerequisites.

## Prepare FaaS containers/pods for functions

From the `fns` directory, run `make prep-*`, where `*` stands for the framework you've installed and want to run on. For example, `make prep-fission`, `make prep-knative`, or `make prep-docker`. Ensure no errors occurred.
You can then try to test-run any function by going to its subdirectory and running `make test-*`, using the same framework list as above, e.g., `make test-docker`.


## Create a container for report creation

From the `examples` directory, run this command to build the `reporter` image that is used to convert raw benchmark outputs into human-readable reports:

```sh
docker build --network=host -t report .
```

## Set up MPI

This step is optional and is only required to run MPI application benchmark. Please follow the instructions [here](./MPI.md).
