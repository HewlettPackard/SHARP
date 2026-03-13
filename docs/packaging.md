# SHARP Benchmark Packaging

SHARP provides tools to package benchmarks into portable, self-contained artifacts that can run without system-wide installation of dependencies. This is especially useful for:

- Running benchmarks on systems without root/sudo access
- Ensuring reproducible benchmark environments
- Deploying benchmarks to clusters or cloud environments
- Bundling benchmarks with external library dependencies

## Supported Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| **Docker** | Container image with all dependencies | Cluster deployment, CI/CD, isolation |
| **AppImage** | Single portable Linux executable | Desktop benchmarking, systems without Docker |

## Unified Requirements Syntax

SHARP 4.0 introduces a unified `requires` field for declaring dependencies that works consistently across both AppImage and Docker builds:

```yaml
build:
  requires:
    python: [sympy, numpy]      # Python packages (pip install)
    system: [build-essential]   # System packages (apt-get install)
    libraries: [gsl]            # Libraries to build from source
```

This replaces the older separate `requirements` and `system_deps` fields.

## Quick Start

### Building a Docker Image

```bash
# Build Docker image for a benchmark
uv run build sleep -t docker

# Build with verbose output
uv run build matmul -t docker -v

# Run the containerized benchmark
docker run --rm sharp-matmul:latest 200
```

### Building an AppImage

```bash
# Install appimagetool first (one-time setup)
# IMPORTANT: Use version 13+ (2019 or later) for --appimage-extract-and-run support
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

# Build AppImage
uv run build sleep -t appimage

# Run the AppImage directly
./build/appimages/sleep-x86_64.AppImage 0.5
```

## Running on Different Backends

SHARP automatically discovers built artifacts when launching benchmarks. The entry point is selected based on the backend:

| Backend | Entry Point Used |
|---------|------------------|
| `local` | AppImage |
| `mpi` | AppImage (via mpirun) |
| `ssh` | AppImage |
| `docker` | Docker image |

### Auto-Discovery Examples

```bash
# Build both formats
uv run build sympy-expand -t appimage
uv run build sympy-expand -t docker

# Launch automatically selects the right artifact
uv run launch -b local sympy-expand    # Uses AppImage
uv run launch -b mpi sympy-expand      # Uses AppImage via MPI
uv run launch -b docker sympy-expand   # Uses Docker image
```

### Running on Remote Systems (SSH/SLURM)

When running benchmarks on remote systems, the executable may be located at a different path. Override the entry point using the `-j` option:

```bash
# Copy AppImage to remote system
scp build/appimages/sympy-expand-x86_64.AppImage user@cluster:/home/user/benchmarks/

# Run on remote system with custom path
uv run launch -b ssh \
    -j '{"entry_point": "/home/user/benchmarks/sympy-expand-x86_64.AppImage", "backend_options": {"ssh": {"hosts": "cluster"}}}' sympy-expand
```

See [launch.md](launch.md) for more details on remote execution.

### Checksum Recording

SHARP automatically records a checksum of the executable in the output `.md` file for reproducibility:

- **AppImage/Binary**: SHA-256 hash of the file
- **Docker**: Image digest from `docker inspect`

Example in `.md` preamble:
```
Executable checksum (sha256): afa5408a9...
```

## Example: Python with External Package (sympy-expand)

The `sympy-expand` benchmark demonstrates packaging a Python program that requires an external package (SymPy) not in SHARP's venv.

**benchmarks/micro/python/benchmark.yaml:**
```yaml
benchmarks:
  sympy-expand:
    entry_point: ./sympy_expand.py
    args: ["20"]
    tags: [python, symbolic, math]

build:
  requires:
    python: [sympy]

  appimage:
    arch: x86_64  # Target architecture (x86_64, aarch64, i686)

  docker:
    base_image: python:3.11-slim
    entrypoint: ["python", "/benchmarks/sympy_expand.py"]
```

**Build and test on all backends:**
```bash
# Build
uv run build sympy-expand -t appimage -v
uv run build sympy-expand -t docker -v

# Test local backend (AppImage)
uv run launch -e test_local -b local --skip-sys-specs -r COUNT -j '{"count": 1}' sympy-expand

# Test MPI backend (AppImage via mpirun)
uv run launch -e test_mpi -b mpi --skip-sys-specs -r COUNT -j '{"count": 1}' sympy-expand

# Test Docker backend
uv run launch -e test_docker -b docker --skip-sys-specs -r COUNT -j '{"count": 1}' sympy-expand
```

## Example: C with Library Built from Source (gsl-integrate)

The `gsl-integrate` benchmark demonstrates packaging a C program with a library (GNU GSL) that must be compiled from source.

### AppImage Runtime Requirements

**AppImage execution requires one of:**
1. **libfuse2 installed** (optimal, fastest execution via FUSE mount)
2. **Manual extraction** with `--appimage-extract-and-run` flag (no FUSE needed)

**Runtime Version:** Requires AppImageKit 13+ (2019 or later) for `--appimage-extract-and-run` support.
- Check your appimagetool version: `appimagetool --version`
- Update if needed: Download from https://github.com/AppImage/AppImageKit/releases

**When libfuse2 is missing:**
- Modern runtimes (13+) support `--appimage-extract-and-run` flag for extraction fallback
- SHARP's SSH backend automatically uses this flag for maximum portability
- Without libfuse2, you'll see: "AppImages require FUSE to run" error

**To install libfuse2 on the system that will run the benchmarks:**
```bash
# Ubuntu/Debian
sudo apt-get install libfuse2

# RHEL/CentOS
sudo yum install fuse-libs
```

### AppImage Portability Strategy

**⚠️ CRITICAL: AppImages must bundle ALL non-standard dependencies**

SHARP's AppImage builder will **emit warnings** for any unresolved external dependencies detected. These warnings indicate that your AppImage will NOT be portable and will fail on systems without those specific libraries installed.

**Rule:** If `system:` lists anything beyond standard system libraries (glibc, libm, libpthread, libdl), you MUST provide AppImage-specific build commands to bundle those dependencies.

For maximum portability across Linux distributions:
- **Standard system libraries** (glibc, libm, libpthread, libdl): Safe to link dynamically (always available)
- **Non-standard system libraries** (libgomp, libgfortran, etc.): **MUST be bundled** - build from source
- **Application libraries** (GSL, BLAS, OpenMP runtime, etc.): Link **dynamically** and bundle `.so` files
- Use `-Wl,-rpath,'$ORIGIN/../lib'` so binaries find bundled `.so` files at runtime
- Only `.so` files go into the AppImage, not source code or object files

**The builder will warn you if dependencies are missing:**
```
⚠️  WARNING: AppImage 'my-benchmark' has unresolved external dependencies:
   This AppImage will NOT be portable and requires these system libraries:
     • libgomp.so.1 => /lib/x86_64-linux-gnu/libgomp.so.1

   To fix this, add AppImage-specific build commands to:
     1. Download library source to 'sources'
     2. Build library with: -static or with -Wl,-rpath,'$ORIGIN/../lib'
     3. Copy library .so files to AppDir/usr/lib/
   See docs/packaging.md for details.
```

**benchmarks/micro/c/benchmark.yaml:**
```yaml
benchmarks:
  gsl-integrate:
    entry_point: ./gsl_integrate
    args: ["100"]
    tags: [c, numerical, math, gsl]

sources:
  - type: download
    location: https://ftp.gnu.org/gnu/gsl/gsl-2.7.1.tar.gz
    mirrors:
      - https://mirror.ibcp.fr/pub/gnu/gsl/gsl-2.7.1.tar.gz

build:
  requires:
    system: [build-essential]
    libraries: [gsl]

  appimage:
    build_commands:
      # 1. Extract and build GSL from source
      - tar xzf gsl-2.7.1.tar.gz
      - cd gsl-2.7.1 && ./configure --prefix=$PWD/../gsl-install && make -j$(nproc) && make install
      # 2. Compile with static system libs, dynamic GSL, rpath for bundled .so
      - gcc -O2 -Wall -static-libgcc -static-libstdc++ -I./gsl-install/include -o gsl_integrate gsl_integrate.c -L./gsl-install/lib -lgsl -lgslcblas -lm -Wl,-rpath,'$ORIGIN/../lib'
      # 3. Bundle only the .so files (not source/objects)
      - mkdir -p ../lib && cp -a gsl-install/lib/*.so* ../lib/

  docker:
    base_image: ubuntu:22.04
    entrypoint: ["/benchmarks/gsl_integrate"]
```

## Build Options

```
sharp build [OPTIONS] BENCHMARK

Options:
  -t, --type {docker,appimage}  Build type (default: docker)
  --download-only              Download sources only, don't build
  --clean                      Remove cached sources before building
  -o, --output DIR             Output directory for artifacts
  --registry URL               Docker registry for pushing images
  -v, --verbose                Verbose output
```

## Use Cases

### 1. Running Benchmarks Without Root Access

AppImages are self-contained executables that bundle all dependencies. This is ideal for running benchmarks on shared systems where you don't have sudo access.

**Example: Running a benchmark with NumPy without installing it system-wide**

```bash
# Build the AppImage (on a system with sudo, or download pre-built)
sharp build -t appimage matmul

# Copy to target system (no sudo needed)
scp build/appimages/matmul-x86_64.AppImage user@cluster:/home/user/

# Run on target system (no installation required!)
ssh user@cluster
./matmul-x86_64.AppImage 500
```

### 2. Bundling External System Dependencies

For benchmarks that need system libraries (like MPI, CUDA, or specialized math libraries), you can bundle them in the container or AppImage.

**Example benchmark.yaml with system dependencies:**

```yaml
benchmarks:
  my-mpi-benchmark:
    entry_point: ./benchmark.py
    args: []
    tags: [mpi, hpc]

build:
  docker:
    base_image: python:3.10-slim
    requirements: [mpi4py, numpy]
  appimage:
    runtime: ubuntu:20.04
    system_deps: [libopenmpi-dev, libhdf5-dev]
  system_deps: [libopenmpi-dev]  # For AppImage
```

**Building and running:**

```bash
# Docker: System deps installed in container
sharp build -t docker my-mpi-benchmark
docker run --rm sharp-my-mpi-benchmark:latest mpirun -np 4 python3 benchmark.py

# AppImage: Libraries bundled in package
sharp build -t appimage my-mpi-benchmark
./build/appimages/my-mpi-benchmark-x86_64.AppImage
```

### 3. Running Packaged Benchmarks with SHARP

Once you've built a Docker image, you can use it with SHARP's Docker backend:

```bash
# Build the benchmark image
sharp build -t docker matmul

# Run with SHARP using Docker backend
sharp launch -e experiment.yaml -b docker

# Or configure the docker backend in your experiment:
# backends/docker.yaml:
#   backend_options:
#     docker:
#       command_template: "docker run --rm $IMAGE $CMD $ARGS"
```

**Example experiment.yaml for Docker:**

```yaml
include:
  - benchmarks/micro/cpu/benchmark.yaml
  - backends/docker.yaml

experiment:
  benchmark: matmul
  backend: docker
  args: ["500"]
  repeats: 10
```

### 4. Reproducible Benchmark Environments

Pin specific versions of dependencies for reproducibility:

```yaml
benchmarks:
  reproducible-bench:
    entry_point: ./benchmark.py
    args: []

build:
  docker:
    base_image: python:3.10.12-slim  # Pin Python version
    requirements:
      - numpy==1.24.3
      - scipy==1.11.1
  requirements:  # Also used for AppImage
    - numpy==1.24.3
    - scipy==1.11.1
```

### 5. GPU Benchmarks with CUDA

```yaml
benchmarks:
  cuda-matmul:
    entry_point: ./cuda-matmul.py
    args: ["1024"]
    tags: [gpu, cuda]

build:
  docker:
    base_image: nvidia/cuda:12.0-runtime-ubuntu22.04
    requirements: [numba, numpy]
  appimage:
    runtime: ubuntu:22.04
    system_deps: [nvidia-cuda-toolkit]
```

**Running with GPU access:**

```bash
# Docker with GPU
docker run --rm --gpus all sharp-cuda-matmul:latest python3 cuda-matmul.py 2048

# AppImage (requires CUDA drivers on host)
./build/appimages/cuda-matmul-x86_64.AppImage 2048
```

## Build Configuration Reference

### benchmark.yaml Build Section

```yaml
build:
  # Docker-specific configuration
  docker:
    base_image: python:3.10-slim    # Base Docker image
    requirements: [numpy, scipy]     # Python packages (overrides top-level)

  # AppImage-specific configuration
  appimage:
    arch: x86_64                    # Target architecture (x86_64, aarch64, i686)
                                    # Only required for compiled binaries (C, C++, etc.)
                                    # Python benchmarks are architecture-independent
    system_deps: [libfoo-dev]       # System libraries to bundle

  # Shared configuration (used by both formats)
  requirements: [numpy]              # Python packages
  system_deps: [libssl-dev]         # System libraries
  makefile: Makefile                # Run make before packaging
  build_commands:                   # Custom build steps
    - ./configure
    - make
  pre_build: ./setup.sh             # Script to run before build
  post_build: ./cleanup.sh          # Script to run after build
```

### Directory Structure After Build

```
build/
├── docker/
│   └── matmul/
│       ├── Dockerfile          # Generated Dockerfile
│       ├── manifest.json       # Build metadata
│       ├── matmul.py          # Copied source files
│       └── ...
└── appimages/
    └── matmul-x86_64.AppImage  # Portable executable
```

## Troubleshooting

### Docker Build Fails

1. **Check Docker is running:** `docker ps`
2. **Check Dockerfile syntax:** `cat build/docker/<benchmark>/Dockerfile`
3. **Build manually for debugging:** `cd build/docker/<benchmark> && docker build -t test .`

### AppImage Build Fails

1. **Install appimagetool:** Download from [AppImageKit releases](https://github.com/AppImage/AppImageKit/releases)
2. **Check AppDir structure:** `ls -la build/appimages/<benchmark>.AppDir/`
3. **Verify AppRun script:** `cat build/appimages/<benchmark>.AppDir/AppRun`

### Missing Dependencies at Runtime

- **Docker:** Add to `build.docker.requirements` or `build.system_deps`
- **AppImage:** Libraries must be bundled or available on the host system
- For system libraries in AppImage, they must be compatible with the host's glibc version

## Advanced: Custom Build Process

For complex benchmarks with custom build requirements:

```yaml
benchmarks:
  complex-bench:
    entry_point: ./bin/benchmark
    sources:
      - type: git
        location: https://github.com/example/benchmark.git
        ref: v2.0.0

build:
  build_commands:
    - mkdir -p build && cd build && cmake ..
    - make -j$(nproc)
    - make install DESTDIR=$PWD/../install
  docker:
    base_image: ubuntu:22.04
  system_deps:
    - cmake
    - build-essential
    - libboost-dev
```

## Build Hooks

Build hooks allow you to run custom scripts at specific points during the build process:

- **`pre_build`**: Runs after files are copied but before build commands (ideal for patching files, setting up environment)
- **`post_build`**: Runs after all build commands complete (ideal for validation, cleanup, or post-processing)

### Hook Execution Order

```
1. System dependencies installed (apt-get, etc.)
2. Files copied to build context
3. pre_build hook executes ← Patch files, generate code, etc.
4. Build commands execute (Makefile, gcc, etc.)
5. post_build hook executes ← Validate, strip binaries, etc.
```

### Example: Patching Version Info

```yaml
benchmarks:
  versioned-app:
    entry_point: ./app
    sources:
      - type: git
        location: https://github.com/example/app.git

build:
  # Patch version header before build
  pre_build: |
    sed -i 's/#define VERSION ".*"/#define VERSION "4.2.0"/' version.h

  build_commands:
    - make -j$(nproc)

  # Strip debug symbols after build
  post_build: |
    strip app
    echo "Build complete: $(./app --version)"
```

### Example: Dependency Setup

```yaml
build:
  # Download and extract dependencies before system packages
  pre_build: |
    wget https://example.com/libfoo.tar.gz
    tar xzf libfoo.tar.gz
    cd libfoo && ./configure --prefix=$PWD/../install && make install

  build_commands:
    - gcc -I./install/include -o myapp myapp.c -L./install/lib -lfoo

  # Verify binary works after build
  post_build: |
    ./myapp --test
    if [ $? -ne 0 ]; then exit 1; fi
```

### Hook Best Practices

1. **Use absolute paths or $PWD** for portability
2. **Check exit codes** - failed hooks stop the build
3. **Keep hooks focused** - one clear purpose per hook
4. **Test locally first** - debug hook scripts before committing
5. **Use multi-line YAML** (`|` or `>`) for complex scripts

### Hook Failures

If a hook script fails (non-zero exit code), the build stops immediately with a clear error message:

```
BuildError: pre_build hook failed: version.h not found
```

This prevents incomplete or broken builds from being packaged.

## See Also

- [backends.md](backends.md) - Backend configuration including Docker backend
- [launch.md](launch.md) - Running experiments with SHARP
- [schemas/](schemas/) - YAML schema reference
