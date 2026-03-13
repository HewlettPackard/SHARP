# Rodinia Benchmark Suite

The Rodinia Benchmark Suite is a collection of parallel programs for heterogeneous computing systems, targeting both CUDA (GPU) and OpenMP (CPU) implementations. This is a widely-used academic benchmark suite for evaluating parallel programming models and hardware architectures.

## Reference

- **Paper**: S. Che et al., "Rodinia: A Benchmark Suite for Heterogeneous Computing," IISWC 2009
- **Source**: https://github.com/yuhc/gpu-rodinia
- **Version**: 3.1 (modified fork with improvements)
- **License**: Various (see individual benchmark directories)

## Overview

**Total Benchmarks**: 29
- **CUDA**: 15 GPU-accelerated benchmarks (in `cuda/`)
- **OpenMP**: 14 CPU-parallel benchmarks (in `omp/`)

## Benchmark Categories

### Medical Imaging
- **heartwall**: Cardiac wall tracking from ultrasound video
- **leukocyte**: White blood cell tracking (OpenMP only)

### Graph Algorithms
- **bfs**: Breadth-first search on large graphs
- **pathfinder**: Dynamic programming shortest path
- **sc** (streamcluster): K-means-based clustering

### Linear Algebra
- **lud**: LU decomposition
- **gaussian**: Gaussian elimination (CUDA only)

### Machine Learning
- **backprop**: Neural network backpropagation
- **nn**: K-nearest neighbors search
- **kmeans**: K-means clustering (OpenMP only)

### Scientific Computing
- **lavamd**: Molecular dynamics simulation
- **hotspot**: Thermal simulation
- **srad-v1, srad-v2**: Speckle reducing anisotropic diffusion (image processing)

### Bioinformatics
- **needle**: Needleman-Wunsch sequence alignment

### Monte Carlo
- **particle-filter**: Particle filter tracking (2 variants in CUDA, 1 in OpenMP)

## Quick Start

### List Available Benchmarks

```bash
# List all Rodinia benchmarks
uv run launch --list-benchmarks | grep rodinia

# Show OpenMP benchmarks
uv run launch --list-benchmarks | grep rodinia-omp

# Show CUDA benchmarks
uv run launch --list-benchmarks | grep rodinia-cuda
```

### Run Examples

```bash
# OpenMP benchmarks (local backend, AppImage)
uv run launch -b local rodinia-omp-backprop
uv run launch -b local rodinia-omp-pathfinder

# CUDA benchmarks (docker backend with GPU)
uv run launch -b docker rodinia-cuda-backprop
uv run launch -b docker rodinia-cuda-bfs
```

## Benchmark Details

### CUDA Benchmarks (15)

| Benchmark | Description | Input Size | Notes |
|-----------|-------------|------------|-------|
| `rodinia-cuda-backprop` | Neural network training | 65536 nodes | No data file required |
| `rodinia-cuda-bfs` | Breadth-first search | 65536-node graph | Uses graph65536.txt |
| `rodinia-cuda-gaussian` | Gaussian elimination | 4x4 matrix | Uses matrix4.txt |
| `rodinia-cuda-heartwall` | Cardiac tracking | 20 frames | Uses test.avi (48 MB) |
| `rodinia-cuda-hotspot` | Thermal simulation | 1024×1024 grid, 2 iters | Uses temp/power data |
| `rodinia-cuda-lavamd` | Molecular dynamics | 10³ boxes | No data file required |
| `rodinia-cuda-lud` | LU decomposition | 256×256 matrix | No data file required |
| `rodinia-cuda-needle` | Sequence alignment | 2048-length sequences | No data file required |
| `rodinia-cuda-nn` | K-nearest neighbors | Hurricane dataset | Uses filelist_4 |
| `rodinia-cuda-particle-filter-naive` | Particle filter (naive) | 128×128×10, 10k particles | No data file required |
| `rodinia-cuda-particle-filter-float` | Particle filter (float) | 128×128×10, 10k particles | No data file required |
| `rodinia-cuda-pathfinder` | Dynamic programming | 100k rows, 100 cols | No data file required |
| `rodinia-cuda-sc` | Streamcluster | 65536 points, 20 dims | No data file required |
| `rodinia-cuda-srad-v1` | Image despeckling v1 | 502×458, 100 iters | No data file required |
| `rodinia-cuda-srad-v2` | Image despeckling v2 | 2048×2048, 2 iters | No data file required |

### OpenMP Benchmarks (14)

| Benchmark | Description | Input Size | Notes |
|-----------|-------------|------------|-------|
| `rodinia-omp-backprop` | Neural network training | 65536 nodes | No data file required |
| `rodinia-omp-bfs` | Breadth-first search | 1M-node graph | Uses graph1MW_6.txt |
| `rodinia-omp-heartwall` | Cardiac tracking | 20 frames, 4 threads | Uses test.avi (48 MB) |
| `rodinia-omp-hotspot` | Thermal simulation | 1024×1024, 2 iters, 4 threads | Uses temp/power data |
| `rodinia-omp-kmeans` | K-means clustering | KDD Cup dataset, 4 threads | Uses kdd_cup data |
| `rodinia-omp-lavamd` | Molecular dynamics | 10³ boxes, 4 cores | No data file required |
| `rodinia-omp-leukocyte` | Cell tracking | 5 frames, 4 threads | Uses testfile.avi |
| `rodinia-omp-lud` | LU decomposition | 8000×8000 matrix | No data file required |
| `rodinia-omp-needle` | Sequence alignment | 2048-length, 10 penalty | No data file required |
| `rodinia-omp-nn` | K-nearest neighbors | Hurricane dataset | Uses filelist.txt |
| `rodinia-omp-particle-filter` | Particle filter | 128×128×10, 10k particles | No data file required |
| `rodinia-omp-pathfinder` | Dynamic programming | 100k rows, 100 cols | No data file required |
| `rodinia-omp-sc` | Streamcluster | 65536 points, 4 threads | No data file required |
| `rodinia-omp-srad-v1` | Image despeckling v1 | 502×458, 100 iters, 4 threads | No data file required |
| `rodinia-omp-srad-v2` | Image despeckling v2 | 2048×2048, 2 iters | No data file required |

## Build Requirements

### CUDA Benchmarks

- **Docker base image**: `nvidia/cuda:11.8.0-devel-ubuntu22.04`
- **System packages**: `make`, `git`, `wget`, `ca-certificates`, `tar`
- **GPU**: CUDA-capable GPU with compute capability ≥ 5.0 (Maxwell architecture or newer)
  - Tested on: Tesla P4 (Pascal, sm_61)
  - Note: Original Rodinia used sm_13/sm_20, patched to sm_50 for CUDA 12.0+ compatibility
- **Supported backends**: `local` (with GPU), `docker` (with nvidia-docker)

### OpenMP Benchmarks

- **Docker base image**: `ubuntu:22.04`
- **System packages**: `gcc`, `g++`, `make`, `libgomp1`, `git`, `wget`, `ca-certificates`, `tar`
- **Packaging**: AppImage with static runtime (no libfuse2 dependency)
  - Runtime: `type2-runtime` (944 KB, statically linked musl + libfuse)
  - Portable across Linux distributions without FUSE installation
- **Supported backends**: `local`, `docker`, `ssh`, `mpi`

## Data Files

Benchmark data is automatically downloaded from Dropbox during build:

- **Archive**: `rodinia-3.1-data.tar.gz` (378 MB)
- **SHA256**: `b90994d5208ec5a0a133dfb9ab7928a1e8a16741503a91d212884b9e4fce8cd8`
- **Extracted location**: `benchmarks/_sources/rodinia-shared/rodinia-data/`
- **Contents**: Input files for bfs, heartwall, hotspot, kmeans, leukocyte, nn, gaussian

Data files are bundled into AppImage/Docker artifacts during build, so benchmarks can run without external dependencies.

## Building Benchmarks

### Build All CUDA Benchmarks

```bash
uv run build -t docker rodinia-cuda-backprop
```

This builds all 15 CUDA benchmarks as Docker images with tag `sharp-rodinia-cuda-*:latest`.

### Build All OpenMP Benchmarks

```bash
uv run build -t appimage rodinia-omp-backprop
```

This builds all 14 OpenMP benchmarks as AppImages in `build/appimages/`.

### Build Options

```bash
# Download sources only (no build)
uv run build -t docker rodinia-cuda-backprop --download-only

# Clean and rebuild
uv run build -t appimage rodinia-omp-backprop --clean

# List available benchmarks
uv run build --list-benchmarks | grep rodinia
```

## Implementation Notes

### Suite Architecture

Both CUDA and OpenMP suites follow the **shared source pattern**:

1. **Sources**: Single git repository + data tarball shared by all benchmarks in suite
2. **Build**: Single build process compiles all benchmarks, outputs copied to individual binaries
3. **Benchmarks**: Individual entries in `benchmark.yaml` reference specific binaries

This approach:
- ✅ Efficient: Clone/build once, use for all benchmarks
- ✅ Consistent: All benchmarks use same source version
- ✅ Maintainable: Suite-level defaults inherited by benchmarks

### Lessons Learned from Integration

**Challenge 1: Data Download Failure**
- **Issue**: Original Dropbox URL (`dropbox.com/s/...`) returned HTML instead of file
- **Root cause**: Dropbox changed link format requiring `?dl=1` parameter
- **Solution**: Updated URL to new format with direct download parameter
- **Lesson**: Pin URLs to stable locations or use checksums to detect failures

**Challenge 2: Data Path Mismatch**
- **Issue**: Benchmarks referenced `data/` but archive extracted to `rodinia-data/`
- **Root cause**: Archive structure changed between Rodinia versions
- **Solution**: Updated all benchmark args to use correct `rodinia-data/` prefix
- **Lesson**: Inspect archive structure before assuming paths

**Challenge 3: CUDA Architecture Obsolescence**
- **Issue**: Makefiles specified sm_13/sm_20 (compute capability 1.3/2.0), unsupported by CUDA 12.0+
- **Root cause**: Rodinia targets old GPUs (2010-2012 era: Fermi, Tesla)
- **Solution**: Added `pre_build` step to patch all Makefiles: `sed -i 's/sm_13/sm_50/g; s/sm_20/sm_50/g'`
- **Target**: sm_50 (Maxwell 2014+, supported by CUDA 11.8-12.x)
- **Lesson**: Use `pre_build` hook to adapt legacy code for modern toolchains

**Challenge 4: AppImage Portability**
- **Issue**: Standard AppImage runtime requires `libfuse2`, unavailable on some systems
- **Root cause**: FUSE 3 replaced FUSE 2, extraction fallback disabled by design
- **Solution**: Switched to static `type2-runtime` (944 KB) that embeds musl + libfuse
- **Trade-off**: 5× larger runtime (193 KB → 944 KB) for zero-dependency portability
- **Lesson**: For maximum portability, use static runtimes at cost of size

**Challenge 5: Build Output Filename Mismatch**
- **Issue**: BFS CUDA makefile outputs `bfs.out`, not `bfs`
- **Solution**: Updated build command to `cp bfs.out ../../bin_bfs`
- **Lesson**: Inspect build artifacts, don't assume standard naming

### Best Practices for Importing Suites

Based on Rodinia integration experience:

1. **Verify Source Availability**
   - Test download URLs before adding to YAML
   - Use checksums (`sha256`) to detect corruption
   - Prefer stable mirrors over Dropbox/Google Drive

2. **Inspect Archive Structure**
   - Extract manually first to verify paths
   - Document expected directory layout in README
   - Use relative paths from source root

3. **Test Build Process**
   - Run build commands manually before automating
   - Check for missing dependencies (libraries, tools)
   - Validate output artifacts exist and are executable

4. **Handle Legacy Code**
   - Use `pre_build` for source patching (sed, awk)
   - Update compiler flags for modern toolchains
   - Test on target architectures (GPU compute capability, CPU ISA)

5. **Document Data Requirements**
   - List required input files with sizes
   - Specify which benchmarks need data vs. synthetic
   - Include download instructions if data not bundled

6. **Verify Portability**
   - Test on multiple systems (distributions, kernel versions)
   - Check for dynamic library dependencies (`ldd`, `docker inspect`)
   - Use static linking or bundle dependencies

7. **Validate Correctness**
   - Run each benchmark at least once after build
   - Check for non-zero exit codes
   - Verify output format matches expected metrics

## Troubleshooting

### CUDA Benchmarks Fail with "no kernel image available"

**Symptom**: Docker run fails with CUDA error about compute capability

**Cause**: GPU compute capability < 5.0 (pre-Maxwell)

**Solution**: Update Makefile `GENCODE` flags to match your GPU architecture, or use newer GPU

### OpenMP Benchmarks Fail with "command not found"

**Symptom**: AppImage fails to launch or extract

**Cause**: Missing FUSE or execution bit not set

**Solution**: AppImages use static runtime with embedded FUSE; ensure file is executable (`chmod +x`)

### Data File Not Found

**Symptom**: Benchmark exits with "No such file or directory" for .txt/.avi file

**Cause**: Data not bundled in artifact, or wrong path

**Solution**: Rebuild with `--clean` to re-download and extract data archive

### Benchmark Hangs Indefinitely

**Symptom**: Benchmark runs but never completes

**Cause**: Input size too large, or deadlock in parallel code

**Solution**: Reduce input size in benchmark args, or kill and inspect with debugger

## Support

For issues specific to SHARP integration, see main project documentation. For Rodinia-specific questions, refer to original paper or GitHub repository.
