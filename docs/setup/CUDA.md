# Setup instructions for functions that can run CUDA code

These instructions roughly follow the steps [here](https://itnext.io/enabling-nvidia-gpus-on-k3s-for-cuda-workloads-a11b96f967b0).

We need to touch all layers of the stack:

1. Install drivers for the GPU on the host
1. Configure containers to run on GPUs
1. Configure `k3s` to use GPUs
1. Optional: extend Fission for GPU support (not implemented yet)

**Disclaimer:** There are leaky abstractions everywhere.
At the end of these instructions in their current form `k3s` does not really understand that it's supposed to schedule pods for GPUs for two reasons:
First, we do not have MIG set up here, so if we were to schedule a pod with a GPU "request", it would schedule exactly one pod and then block all the others as the GPU would already be occupied by that one pod.
Second, we only have one node in our setup, consequently each of the nodes in the cluster has a GPU (i.e., only one node).
A mixed cluster of nodes with and without GPUs does not work for us at the moment, because Fission does not understand GPUs at all, so there is no way we can tell it to schedule some functions for GPU and some not for GPU.
As a result, **every function has access to the GPU at the same time**!
It is, for now, up to us to limit the usage of GPUs.
If you use environments without CUDA installed, this should not be an issue, but keep it in mind for your CUDA applications.

## 1. Install Nvidia drivers

On your server machines, install the Nvidia drivers:

```sh
sudo apt install nvidia-headless-515-server nvidia-utils-515 # or whatever version
```

Alternatively, install the GUI version

```sh
sudo apt install nvidia-driver-515 nvidia-utils-515
```

Test it by running `nvidia-smi` and see if the output matches your hardware configuration.

## 2. Install the Nvidia container toolkit

Follow the [instructions](https://docs.nvidia.com/ai-enterprise/deployment-guide/dg-docker.html#enabling-the-docker-repository-and-installing-the-nvidia-container-toolkit) to install the container toolkit.
Specifically, add the repository and install `nvidia-container-toolkit`, then restart Docker and `k3s`:

```sh
# note that this is here for convenience: check the nvidia docs for any updates
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

sudo systemctl restart docker
# note that restarting k3s will also restart components such as containerd
sudo systemctl restart k3s
```

Technically, Docker is not even used in `k3s`, but it's helpful for debugging.
It also appears that this will implicitly install the GPU support for `containerd`.

You can test your installation with:

```sh
# running on the host
$ nvidia-smi
... this output should reflect the GPUs on the local machine

# running on docker
$ docker run --gpus all nvidia/cuda:11.7.0-devel-ubuntu20.04 nvidia-smi
... this output should match the output above

# running on containerd
# add /usr/local/bin to your PATH if it cannot find k3s
$ sudo k3s ctr run --gpus 0 -t docker.io/nvidia/cuda:11.7.0-devel-ubuntu20.04 cuda-ctr nvidia-smi
... should also see your GPUs
```

## 3. Configure K3s to use `nvidia-container-runtime`

We need to instruct the `k3s` agent to use `nvidia-container-runtime` as a `containerd` backend.
This is done in the configuration file for `containerd`, which probably does not exist for your system yet (if you have a local configuration, make sure to adapt it to the new format).

Download `sudo wget https://k3d.io/v4.4.8/usage/guides/cuda/config.toml.tmpl` and add it as `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl`, or paste from here:

```tmpl
[plugins.opt]
  path = "{{ .NodeConfig.Containerd.Opt }}"

[plugins.cri]
  stream_server_address = "127.0.0.1"
  stream_server_port = "10010"

{{- if .IsRunningInUserNS }}
  disable_cgroup = true
  disable_apparmor = true
  restrict_oom_score_adj = true
{{end}}

{{- if .NodeConfig.AgentConfig.PauseImage }}
  sandbox_image = "{{ .NodeConfig.AgentConfig.PauseImage }}"
{{end}}

{{- if not .NodeConfig.NoFlannel }}
[plugins.cri.cni]
  bin_dir = "{{ .NodeConfig.AgentConfig.CNIBinDir }}"
  conf_dir = "{{ .NodeConfig.AgentConfig.CNIConfDir }}"
{{end}}

[plugins.cri.containerd.runtimes.runc]
  # ---- changed from 'io.containerd.runc.v2' for GPU support
  runtime_type = "io.containerd.runtime.v1.linux"

# ---- added for GPU support
[plugins.linux]
  runtime = "nvidia-container-runtime"

{{ if .PrivateRegistryConfig }}
{{ if .PrivateRegistryConfig.Mirrors }}
[plugins.cri.registry.mirrors]{{end}}
{{range $k, $v := .PrivateRegistryConfig.Mirrors }}
[plugins.cri.registry.mirrors."{{$k}}"]
  endpoint = [{{range $i, $j := $v.Endpoints}}{{if $i}}, {{end}}{{printf "%q" .}}{{end}}]
{{end}}

{{range $k, $v := .PrivateRegistryConfig.Configs }}
{{ if $v.Auth }}
[plugins.cri.registry.configs."{{$k}}".auth]
  {{ if $v.Auth.Username }}username = "{{ $v.Auth.Username }}"{{end}}
  {{ if $v.Auth.Password }}password = "{{ $v.Auth.Password }}"{{end}}
  {{ if $v.Auth.Auth }}auth = "{{ $v.Auth.Auth }}"{{end}}
  {{ if $v.Auth.IdentityToken }}identitytoken = "{{ $v.Auth.IdentityToken }}"{{end}}
{{end}}
{{ if $v.TLS }}
[plugins.cri.registry.configs."{{$k}}".tls]
  {{ if $v.TLS.CAFile }}ca_file = "{{ $v.TLS.CAFile }}"{{end}}
  {{ if $v.TLS.CertFile }}cert_file = "{{ $v.TLS.CertFile }}"{{end}}
  {{ if $v.TLS.KeyFile }}key_file = "{{ $v.TLS.KeyFile }}"{{end}}
{{end}}
{{end}}
{{end}}
```

This keeps most of your existing configurations but adds the plugin for `nvidia-container-runtime`.

## 4. Install Nvidia device plugin for K8s

Although `containerd` now knows to use the Nvidia container runtime, we still need to add GPU support to `k3s` by adding the `nvidia-device-plugin`:

```sh
cat <<EOF | kubectl apply -f -
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: nvidia-device-plugin
  namespace: kube-system
spec:
  chart: nvidia-device-plugin
  repo: https://nvidia.github.io/k8s-device-plugin
EOF
```

## 5. Test a CUDA-enabled pod

We can try to run a CUDA-enabled pod called `gpu-pod` on `k3s` now:

```sh
$ kubectl run gpu-pod --image nvidia/cuda:11.4.1-base-ubuntu20.04 --command -- /bin/bash -c -- "while true; do sleep 30; done;"
pod/gpu-pod created
```

Once that pod is running, try `nvidia-smi` within it:

```sh
$ kubectl exec gpu-pod -- nvidia-smi
.. GPU should appear in the output
```

Clean up with `kubectl delete pod gpu-pod`.

## 6. Create custom images for Fission

For now, we have a `cuda-env` and `cuda-builder` environment for Fission that supports Python.
It works just like the normal Python environment but has CUDA support and is based on Ubuntu 20.04.
Check the [`../fission-environments/nvidia-cuda`](../fission-environments/nvidia-cuda) directory for this.

Note that as with Python environments, you can only use the builder for `pip` dependencies.
If you want to install software, you need to add it directly to the environment image by using the base environment as a base image:

```Dockerfile
# this is the nvidia-cuda environment image
FROM bd-harbor-registry.mip.storage.hpecorp.net/hsa/fission/cuda-env-3.9

# run additional setup
RUN apt update && \
    apt install curl -y

# do not add custom CMD or ENTRYPOINT directives as this would overwrite those of the base
```

If you need the dependencies for both environment and builder, do this for both images.

## 7. Create a custom environment for Fission functions

To create a custom environment for Fission with our `nvidia-cuda` base images:

```sh
fission env create --name cudasrc \
      --image bd-harbor-registry.mip.storage.hpecorp.net/hsa/fission/cuda-env-3.9 \
      --builder bd-harbor-registry.mip.storage.hpecorp.net/hsa/fission/cuda-builder-3.9 \
      --mincpu 40 --maxcpu 48000 \
      --minmemory 64 --maxmemory 168000 \
      --poolsize 2
```

(This command can be run by calling `make cudasrc-env` from `fns/`, after you've updated image locations.)
You should now be ready to package and run Fission functions using CUDA.
