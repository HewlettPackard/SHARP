# Set-up Docker

* Follow the instructions [here](https://docs.docker.com/desktop/install/linux-install/) to install docker.

* Set up user: `sudo usermod -aG docker $USER && newgrp docker`

* Run it: `sudo systemcl start docker && systemctl enable docker`

* Log in: `docker login`

* Using custom python functions given in the framework:
In the fns directory,open the Makefile and update the value of the IMAGE_REPO parameter to the image repository you want to use. Remember to perform `docker login` to the repo to enable pushing and pulling of images.
* Run `make prep-docker FNS="sleep/"` to deploy sleep as a docker image. Test the function using the command `make test-docker FNS="sleep/`. The function should print the total time taken to perform sleep for 2 seconds. Delete the function using the command `make clean-docker FNS="sleep/`.

* If you want to recreate all the docker function images required by this benchmark suite, go to `fns/` and run `make clean-docker`. Then you can run `make prep-docker` to prepare all the functions.


## Troubleshooting

* To see if container creation was successful: `docker ps | grep <function name>`. Since we use the same Dockerfile used for creating docker images for knative, the image name would look like `knative-<function name>`.
* To look at the function's container log, use: `docker logs <function name>`.
