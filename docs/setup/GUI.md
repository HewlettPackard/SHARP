# SHARP Graphical User Interface (GUI)

The GUI can be set up and run in two different ways:

## Docker GUI container

This method is the easiest in terms of installing prerequisites, because they are all included in the container, but it can only run benchmarks in the local container environment.

### Building

To build the image in Linux, pass the host kernel version so the correct `perf` tools are installed:

```sh
docker build --build-arg KERNEL_VERSION=$(uname -r) -t sharp-gui -f gui/Dockerfile .
```

### Running

Basic usage:
```sh
docker run -p 2626:2626 sharp-gui
```

If you are running the experiments on local system and want the visualization using docker image, use:
```sh
docker run -v <Path to SHARP>/runlogs:/usr/sharp/runlogs -p 2626:2626 sharp-gui
```

To use `perf` profiling inside the container, run with the `SYS_ADMIN` capability:
```sh
docker run --cap-add SYS_ADMIN -p 2626:2626 sharp-gui
```

> **Note:** The host must have `kernel.perf_event_paranoid` set to `-1` for perf to work:
> ```sh
> sudo sysctl -w kernel.perf_event_paranoid=-1
> ```

To preload an alternative memory allocator (tcmalloc or jemalloc) for benchmarked workloads:
```sh
# tcmalloc
docker run -e LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4 \
  -p 2626:2626 sharp-gui

# jemalloc
docker run -e LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
  -p 2626:2626 sharp-gui
```

Point a browser at your server using a url like [localhost:2626](http://localhost:2626).

### Stopping

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
