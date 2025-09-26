# SHARP Graphical User Interface (GUI)

The GUI can be set up and run in two different ways:

## Docker GUI container

This method is the easiest in terms of installing prerequisites, because they are all included in the container, but it can only run benchmarks in the local container environment.
To build the image in Linux, run:

```sh
docker build -t sharp-gui -f gui/Dockerfile .
```

Then to run it, use:
```sh
docker run -p 2626:2626 sharp-gui
```

If you are running the experiments on local system and want the visualization using docker image, use:
```sh
docker run -v <Path to SHARP>/runlogs:/usr/sharp/runlogs -p 2626:2626 sharp-gui
```

Point a browser at your server using a url like [localhost:2626](http://localhost:2626).

To kill the container from another shell, you can run something like:

```sh
docker ps | grep sharp-gui | awk ' {print $1;} ' | xargs docker kill
```

## Native GUI

You can also run the GUI directly on your server, which opens that door to running on any backend, including MPI and FaaS.
This requires you install yourself all the preqrequisite software defined in `gui/Dockerfile`.
Once installed, you can run the GUI with a command like:

```sh
 R -e 'shiny::runApp("gui/app.R", port=2626, host = "0.0.0.0")'
```

Then continue to point a browser at your server as in the containerized version.
To stop the GUI, just kill the R shiny process like any other process.
