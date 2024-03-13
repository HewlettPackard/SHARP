# Set-up Knative

* Knative requires at least one-node cluster that has 3 CPUs and 4 GB of memory. Follow the instructions from [here](https://knative.dev/docs/install/) to install Knative (prefered version: 1.11.0).

* Create and test a simple "Hello world" Knative Service using the tutorial [here](https://knative.dev/docs/getting-started/first-service/)

* Using custom python functions given in the framework:
In the fns directory,open the Makefile and update the value of the IMAGE_REPO parameter to the image repository you want to use. Remember to perform `docker login` to the repo to enable pushing and pulling of images.
* Run `make prep-knative FNS="sleep/"` to deploy sleep as a knative function. Test the function using the command `make test-knative FNS="sleep/`. The function should print the total time taken to perform sleep for 2 seconds. Delete the function using the command `make clean-knative FNS="sleep/`.

* If you want to recreate all the knative function images required by this benchmark suite, go to `fns/` and run `make clean-knative`. Then you can run `make prep-knative` to prepare all the functions.


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
