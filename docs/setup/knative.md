# Set-up Knative

* Knative requires at least one-node cluster that has 3 CPUs and 4 GB of memory. Follow the instructions from [here](https://knative.dev/docs/install/) to install Knative (prefered version: 1.11.0).

* Create and test a simple "Hello world" Knative Service using the tutorial [here](https://knative.dev/docs/getting-started/first-service/)

## Using SHARP benchmarks with Knative

SHARP no longer ships repo-managed Knative service manifests. To run a benchmark with the Knative backend, deploy a Knative service yourself and give it the same name as the benchmark you will launch from SHARP.

For example, to run `uv run launch -b knative sleep 2`, make sure a Knative service named `sleep` already exists and accepts the request format expected by that benchmark.

If you need a container image for the service, build it from the benchmark definition:

```sh
uv run build -t docker --registry <registry> sleep
```

Then point your `ksvc` at the resulting image and verify the deployment:

```sh
kubectl get ksvc sleep
```


## Troubleshooting

* If the function times out, try to delete it and recreate it.
* To look at the function's log, use: `kubectl logs -n --tail -1 -l <pod name>` (replace with your own environment).
* To look at knative's pod, which also shows CPU/mem limits: `kubectl describe pod <pod name>`.
* To see if environment creation was successful: `kubectl get pods`.

## Debugging Knative

Your best option to debug Knative is to look at the Kubernetes logs for the pods that it uses.
There are two main namespaces that you may want to look at:

```sh
# this will give you the main pods that knative uses internally, such as the request endpoint or pool manager
$ kubectl get pods -n knative-serving
```

```sh
# Knative by default deploys the functions in the default namesapce. These functions can be viewed by using either of the follwoing commands:
$ kubectl get pods -n default
$ kubectl get ksvc
