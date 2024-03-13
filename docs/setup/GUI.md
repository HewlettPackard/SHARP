# SHARP Graphical User Interface (GUI)

The GUI can be set up and run in two different ways:

## Docker GUI container

This method is the easiest in terms of installing prerequisites, because they are all included in the container, but it can only run benchmarks in the local container environment.
To build the image in Linux, run:

```sh
cd gui
docker build -t sharp-gui .
```

Then to run it, use:
```sh
docker run -p 2610:2610 sharp-gui
```

Point a browser at your server using a url like [localhost:2610](http://localhost:2610).

To kill the container from another shell, you can run something like:

```sh
docker ps | grep sharp-gui | awk ' {print $1;} ' | xargs docker kill
```

## Native GUI

You can also run the GUI directly on your server, which opens that door to running on any backend, including MPI and FaaS.
This requires you install yourself all the preqrequisite software defined in `gui/Dockerfile`.
Once installed, you can run the GUI with a command like:

```sh
 R -e 'shiny::runApp("gui/app.R", port=2610, host = "0.0.0.0")'
```

Then continue to point a browser at your server as in the containerized version.
To stop the GUI, just kill the R shiny process like any other process.
