# Set-up Fission

* Fission requires a persistent volume of 8gb (which minikube sets up automatically, but k8s doesn't). If you need to add one, run: `kubectl apply -f pv.yaml`, where `pv.yaml` looks like this:


```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv0001
spec:
  accessModes:
    - ReadWriteOnce
  capacity:
    storage: 8Gi
  hostPath:
    path: /data/pv0001/
```

* Follow the instructions from [here](https://fission.io/docs/installation/#install-fission) to install Fission:

    First set up Fission on your cluster:

    ```sh
    kubectl create -k "github.com/fission/fission/crds/v1?ref=v1.19.0"
    export FISSION_NAMESPACE="fission"
    kubectl create namespace $FISSION_NAMESPACE
    kubectl config set-context --current --namespace=$FISSION_NAMESPACE
    kubectl apply -f https://github.com/fission/fission/releases/download/v1.19.0/fission-all-v1.19.0.yaml
    kubectl config set-context --current --namespace=default
    ```

    Then install the `fission` CLI:

    ```sh
    curl -Lo fission https://github.com/fission/fission/releases/download/v1.19.0/fission-v1.19.0-linux-amd64 \
      && chmod +x fission && sudo mv fission /usr/local/bin/
    ```

* Create and test a simple FaaS "hello world":

    ```sh
    cat << EOF > hello.py
    def main():
        return "Hello, world!\n"
    EOF

    fission env create --name python --image fission/python-env
    fission function create --name hello-py --env python --code hello.py
    fission function test --name hello-py
    ```

* Cleanup test:

  ```sh
  fission fn delete --name hello-py
  fission env delete --name python
  ```

* Create a new builder environment:

    ```sh
    fission env create --name python-src --image fission/python-env:latest \
                    --builder fission/python-builder:latest \
                    --mincpu 40 --maxcpu 48000 \
                    --minmemory 64 --maxmemory 168000 \
                    --poolsize 2
    ```

    Note that you must set `--mincpu`, `--minmemory`, and `--poolsize` in such a way that Kubernetes can still schedule your function environments!
    For example, if you set `--mincpu 1000` and `--poolsize 10`, Kubernetes will need 10 CPUs available or run into errors.
    Note that CPUs are in milli-CPUs and memory is in MB.
    You can reproduce this step by running `make python-src` from `fns/`. You may have to edit the Makefile to point at the correct Docker registry.
    If you're accessing docker images via a k8s secret, as explained in the [README](./README.md), you'll need to add `--imagepullsecret=docker-registry-secret` to this command line and to the Makefile.

* Test a more complicated Python program with dependencies and paramemters:

    ```sh
    fission fn create --name matmul --env python-src
    fission fn test --name matmul -b '100'
    kubectl logs --namespace fission-function -l environmentName=python-src --tail -1 # to check logs
    ```
* Make changes to `matmul/user.py` and retry, if you like: `make prep-fission`.

* To build the environment images and push them to the required docker repository, go to `fns/`, update the Makefile variable `IMAGE_REPO` to the desired repository and run `make deploy`.

* If you want to recreate all the fission environments required by this benchmark suite, go to `fns/` and run `make fission-env-clean fission-env`. Then you can run `make prep-fission` to prepare all the functions.


## Troubleshooting

* If the function times out, try to delete it and recreate it.
* To look at the function's log, use: `kubectl logs -n fission-function --tail -1 -l environmentName=python-src` (replace with your own environment).
* To look at fission's pod, which also shows CPU/mem limits: `kubectl describe pod -n fission-function`
* To see if environment creation was successful: `kubectl get pods -n fission-function`
* To look at the build process log: `fission pkg info --name swapbytes-pkg`
* If environment fails to pull from docker, try a manual pull (see below).
* Look also [here](https://fission.io/docs/trouble-shooting/setup/) for troubleshooting advice.
* Consider using a different python environment than the default alpine, such as debian. For example, numpy runs single-threaded on the former. This would require [cloning](https://fission.io/docs/usage/languages/python) the environment, changing the Dockerfile, and building and pushing a new image to dockerhub, as described next.

## Using a custom environment

The default Python environment uses `alpine` as a base image, which can lead to issues with any dependencies that might a) depend on glibc or b) not be available as precompiled from PyPi for non-glibc distributions.
Thankfully, Fission also provides a Dockerfile Debian-based Python environment, although we have not found an on-demand built image.
Instead, we can build one ourselves:

```sh
git clone git@github.com:fission/environments.git
cd environments/python
# feel free to replace PY_BASE_IMG with a different one
docker build -t fission-python-buster -f Dockerfile-buster --build-arg PY_BASE_IMG=python:3.9-buster .
```

That should give you a new environment image to use when you create a Fission environment!
If you would like to add dependencies such as `numpy` to this base image without creating a whole deployment package, you can do so by creating additional images on top:

```Dockerfile
FROM fission-python-buster

RUN python3 -m pip install numpy
```

Make sure those images are available to your Fission instance somehow (push to a registry for minikube or have available locally for `k3s`).

The only caveat is that functions without a deployment package must have a `main` method and Fission appears to ignore the `--entrypoint` parameter.

### Using a Python Debian environment

Use the updated Fission environments (included in this repository as a submodule) to run a Debian builder and environment.
If you have not yet checked out the submodules, use `git submodule update --init` to do so.

Then follow the instructions in `fission-environments/python` to build the debian images (it's just `make`).

### Using a custom builder

Note that these are special instructions that should only be applied if the default alpine and Debian (see above) environments are insufficient!
If you want to install additional software to your environment, use a deployment package.

You can also use a custom build image if you want to run your functions from deployment packages.
Note that this is only really necessary if you want your function to run using a non-alpine or non-debian distribution.

Create a `Dockerfile-buster` next to the default Python builder:

```sh
cd environments/python/builder
touch Dockerfile-buster
```

These contents are based on the existing alpine Dockerfile, replacing `apk` commands with those for Debian `apt`:

```Dockerfile
ARG BUILDER_IMAGE=fission/builder
ARG PY_BASE_IMG

FROM ${BUILDER_IMAGE}
FROM python:${PY_BASE_IMG}

COPY --from=0 /builder /builder
# the previous alpine command installed the necessary dependencies, we'll do the same
# RUN apk add --update --no-cache python3-dev build-base gcc bash
RUN apt-get update && \
        apt-get install python3-dev build-essential gcc -y

ADD defaultBuildCmd /usr/local/bin/build

EXPOSE 8001
```

And then build and tag this image:

```sh
docker build -t builder-python-buster -f Dockerfile-buster --build-arg PY_BASE_IMG=3.9-buster .
```

You can then create a new environment that uses a custom builder and execution environment:

```sh
fission env create --name python-src \
      --image bd-harbor-registry.mip.storage.hpecorp.net/hsa/fission/python-env-buster \
      --builder bd-harbor-registry.mip.storage.hpecorp.net/hsa/fission/python-builder-buster \
      --mincpu 40 --maxcpu 48000 \
      --minmemory 64 --maxmemory 168000 \
      --poolsize 2
```

(This command can be run by calling `make pythonrc-src` from `fns/`, after you've updated image locations.)
Note that you don't necessarily have to add your dependencies to the execution environment if you have it install during your package build.

## Debugging Fission

Your best option to debug Fission is to look at the Kubernetes logs for the pods that Fission uses.
There are three main namespaces that you may want to look at:

```sh
# this will give you the main pods that fission uses internally, such as the request endpoint or pool manager
$ kubectl get pods -n fission

NAME                              READY   STATUS    RESTARTS   AGE
timer-5dd7d7fb69-r46xl            1/1     Running   0          18h
kubewatcher-8688df66c5-hkx7d      1/1     Running   0          18h
router-77966569c4-x2mfg           1/1     Running   0          18h
buildermgr-648dc8bc4-pt7h5        1/1     Running   0          18h
controller-5b9d8f7c76-hr4j8       1/1     Running   0          18h
mqtrigger-keda-5b8749f5bb-xb8fg   1/1     Running   0          18h
executor-7bf4f9d9c9-7xltq         1/1     Running   0          18h
storagesvc-78fd7f867b-pnp5j       1/1     Running   0          18h

# this gives you the pods that are used to build package
$ kubectl get pods -n fission-builder

NAME                              READY   STATUS    RESTARTS   AGE
pythonsrc-15704-d94cdc6f9-x5bm6   2/2     Running   0          3m44s

# this gives you the pods that are used to run your functions
$ kubectl get pods -n fission-function

NAME                                                       READY   STATUS         RESTARTS   AGE
poolmgr-python-buster-numpy-default-1981-d8c49475f-g4z9d   2/2     Running        0          17h
poolmgr-python-buster-numpy-default-1981-d8c49475f-xrwg7   2/2     Running        0          17h
poolmgr-python-buster-numpy-default-1981-d8c49475f-zhj8f   2/2     Running        0          17h
poolmgr-pythonsrc-default-15704-574d9b57b8-hdkcd           1/2     ErrImagePull   0          3m30s
poolmgr-pythonsrc-default-15704-574d9b57b8-pj72d           1/2     ErrImagePull   0          3m30s
poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24           1/2     ErrImagePull   0          3m30s
```

In the last example, you can see that we have a pool of pods for the `python-buster-numpy` environment and one for the `pythonsrc` environment.
The `pythonsrc` ones give an error, indicating that something is wrong.
In this case, the error is `ErrImagePull`, likely indicating that it had trouble pulling from Docker Hub (which happens a lot).
Let's investigate by describing one of the pods in more detail:

```sh
$ kubectl describe pod -n fission-function poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24

Name:         poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24
Namespace:    fission-function
Priority:     0
Node:         etc1/10.93.232.57
Start Time:   Thu, 21 Jul 2022 09:28:05 -0700
Labels:       environmentName=pythonsrc
              environmentNamespace=default
              environmentUid=554a67af-e14d-425a-946b-48ef59d95a45
              executorType=poolmgr
              managed=true
              pod-template-hash=574d9b57b8
Annotations:  <none>
Status:       Pending
IP:           10.42.0.37
IPs:
  IP:           10.42.0.37
Controlled By:  ReplicaSet/poolmgr-pythonsrc-default-15704-574d9b57b8
Containers:
  pythonsrc:
    Container ID:
    Image:          fission/python-env:latest
    Image ID:
    Ports:          8000/TCP, 8888/TCP
    Host Ports:     0/TCP, 0/TCP
    State:          Waiting
      Reason:       ImagePullBackOff
    Ready:          False
    Restart Count:  0
    Limits:
      cpu:     48
      memory:  168000Mi
    Requests:
      cpu:        40m
      memory:     64Mi
    Environment:  <none>
    Mounts:
      /configs from configmaps (rw)
      /etc/podinfo from podinfo (rw)
      /secrets from secrets (rw)
      /userfunc from userfunc (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-5pmvs (ro)
  fetcher:
    Container ID:  docker://22331384d90b66ab50911c55632ab7ddc6bd5e0262ea3033632c0622ead20b36
    Image:         fission/fetcher:v1.16.0
    Image ID:      docker-pullable://fission/fetcher@sha256:9a8175176ec8c0b87207465fc4c2f9458451fc7428b44287607d42fe3fad6ea8
    Port:          <none>
    Host Port:     <none>
    Command:
      /fetcher
      -secret-dir
      /secrets
      -cfgmap-dir
      /configs
      -jaeger-collector-endpoint

      /userfunc
    State:          Running
      Started:      Thu, 21 Jul 2022 09:28:09 -0700
    Ready:          True
    Restart Count:  0
    Requests:
      cpu:      10m
      memory:   16Mi
    Liveness:   http-get http://:8000/healthz delay=1s timeout=1s period=5s #success=1 #failure=3
    Readiness:  http-get http://:8000/readiness-healthz delay=1s timeout=1s period=1s #success=1 #failure=30
    Environment:
      OTEL_EXPORTER_OTLP_INSECURE:  true
      OTEL_TRACES_SAMPLER_ARG:      0.1
      OTEL_EXPORTER_OTLP_ENDPOINT:
      OTEL_TRACES_SAMPLER:          parentbased_traceidratio
      OTEL_PROPAGATORS:             tracecontext,baggage
    Mounts:
      /configs from configmaps (rw)
      /etc/podinfo from podinfo (rw)
      /secrets from secrets (rw)
      /userfunc from userfunc (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-5pmvs (ro)
Conditions:
  Type              Status
  Initialized       True
  Ready             False
  ContainersReady   False
  PodScheduled      True
Volumes:
  userfunc:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  secrets:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  configmaps:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  podinfo:
    Type:  DownwardAPI (a volume populated by information about the pod)
    Items:
      metadata.name -> name
      metadata.namespace -> namespace
  kube-api-access-5pmvs:
    Type:                    Projected (a volume that contains injected data from multiple sources)
    TokenExpirationSeconds:  3607
    ConfigMapName:           kube-root-ca.crt
    ConfigMapOptional:       <nil>
    DownwardAPI:             true
QoS Class:                   Burstable
Node-Selectors:              <none>
Tolerations:                 node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
Events:
  Type     Reason     Age                    From               Message
  ----     ------     ----                   ----               -------
  Normal   Scheduled  5m23s                  default-scheduler  Successfully assigned fission-function/poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24 to etc1
  Normal   Pulled     5m19s                  kubelet            Container image "fission/fetcher:v1.16.0" already present on machine
  Normal   Created    5m19s                  kubelet            Created container fetcher
  Normal   Started    5m19s                  kubelet            Started container fetcher
  Normal   Pulling    4m34s (x3 over 5m22s)  kubelet            Pulling image "fission/python-env:latest"
  Warning  Failed     4m32s (x3 over 5m19s)  kubelet            Failed to pull image "fission/python-env:latest": rpc error: code = Unknown desc = Error response from daemon: toomanyrequests: You have reached your pull rate limit. You may increase the limit by authenticating and upgrading: https://www.docker.com/increase-rate-limit
  Warning  Failed     4m32s (x3 over 5m19s)  kubelet            Error: ErrImagePull
  Warning  Failed     4m6s (x6 over 5m18s)   kubelet            Error: ImagePullBackOff
  Normal   BackOff    18s (x22 over 5m18s)   kubelet            Back-off pulling image "fission/python-env:latest"
```

Always make sure to specify the right namespace with the `-n` flag!
We have again reached our Docker Hub rate limit.
K3s fails to use our credentials, so let's manually pull that image:

```sh
$ docker pull fission/python-env:latest
...

# you may need to wait a few minutes to see the effects if k3s backs off from image pulling
$ kubectl get pods -n fission-function
NAME                                                       READY   STATUS        RESTARTS   AGE
poolmgr-python-buster-numpy-default-1981-d8c49475f-g4z9d   2/2     Running       0          17h
poolmgr-python-buster-numpy-default-1981-d8c49475f-xrwg7   2/2     Running       0          17h
poolmgr-python-buster-numpy-default-1981-d8c49475f-zhj8f   2/2     Running       0          17h
poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24           2/2     Running       0          15m
poolmgr-pythonsrc-default-15704-574d9b57b8-hdkcd           2/2     Running       0          15m
poolmgr-pythonsrc-default-15704-574d9b57b8-96rh7           2/2     Running       0          15m
```

(If you have to pull manually from bd-harbor, it's a bit more involved. Log in to [bd-harbor's website](https://bd-harbor-registry.mip.storage.hpecorp.net/harbor/projects), find the project and image, click on it, then click on pull command and paste it in the terminal.)

Similarly, you can also see the logs of a function by looking at container logs:

```sh
$ kubectl logs -n fission-function poolmgr-pythonsrc-default-15704-574d9b57b8-7nc24
<log-output>
```

That will give you the output for only one pod of your executor pool!
As you don't know which container executed your function, you might want to get all logs for a specific environment output together:

```sh
$ kubectl logs -n fission-function --tail -1 -l environmentName=pythonsrc
<more log output>
```

These logs might not be in chronological order, but you have timestamps!
Note that `--tail -1` is required to get all logs.
Use the `-f` flags to follow logs.

Similarly, you can also check for build errors (and status!) by checking logs of your build environments:

```sh
$ kubectl get pods -n fission-builder

NAME                              READY   STATUS    RESTARTS   AGE
pythonsrc-15704-d94cdc6f9-x5bm6   2/2     Running   0          3m44s

$ kubectl logs -n fission-builder pythonsrc-15704-d94cdc6f9-x5bm6
<build log output>
```

You can also shell into the container:

```sh
kubectl exec -n fission-builder pythonsrc-15704-d94cdc6f9-x5bm6 -it -- /bin/sh
```

## Additional resources

* [How to create a Fission function](https://fission.io/docs/usage/function/functions/)
* [Function workflows](https://github.com/fission/fission-workflows/blob/master/Docs/functions.md)
* [Fission reference card](https://platform9.com/wp-content/uploads/2019/03/dzone-refcard-fissionio.pdf)
* [Python examples](https://github.com/fission/examples/tree/main/python)
