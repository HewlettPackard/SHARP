# Set-up Docker

* Follow the instructions [here](https://docs.docker.com/desktop/install/linux-install/) to install docker.

* Set up user: `sudo usermod -aG docker $USER && newgrp docker`

* Run it: `sudo systemctl start docker && sudo systemctl enable docker`

* Log in: `docker login`

* Build a Docker image for a benchmark from its YAML definition:

	```sh
	uv run build -t docker sleep
	```

	This produces an image tagged `sharp-sleep:latest` and a manifest under `build/docker/sleep/`.

* To build and push directly to a registry:

	```sh
	uv run build -t docker --registry <registry> sleep
	```

* To run the benchmark through SHARP's Docker backend:

	```sh
	uv run launch -b docker sleep 2
	```

* To build a whole suite at once:

	```sh
	uv run build -t docker benchmarks/micro/cpu
	```


## Troubleshooting

* To see if the image was created successfully: `docker images | grep sharp-<benchmark>`.
* To inspect the generated build context and manifest: `ls build/docker/<benchmark>/`.
* To look at the benchmark's container output directly, run: `docker run --rm sharp-<benchmark>:latest ...`.
