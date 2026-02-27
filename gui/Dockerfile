# Pin base image to specific digest for reproducibility
# To update: docker pull rocker/tidyverse:4.3 && docker inspect rocker/tidyverse:4.3 | grep -A1 RepoDigests
# Or visit: https://hub.docker.com/r/rocker/tidyverse/tags
# Using both tag and digest ensures you get the exact image every time
FROM rocker/tidyverse:4.3@sha256:b2fc0a9357b1cb6c90b7a1ac527bd09f113d76f88175db8b99d205d73fbc31b7

# Kernel version for perf tools — must match the host kernel.
# Override at build time:  docker build --build-arg KERNEL_VERSION=$(uname -r) ...
ARG KERNEL_VERSION=6.8.0-100-generic

# System dependencies — use apt-get (not apt) for non-interactive scripts
# Note: Not running apt-get upgrade to keep versions consistent across builds.
# If you need security updates, rebuild from a newer base image digest.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    python3-dev \
    time \
    make \
    llvm \
    g++ \
    curl \
    rename \
    libopenmpi-dev \
    libgsl-dev \
    libev-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libtcmalloc-minimal4 \
    libgoogle-perftools-dev \
    libjemalloc2 \
    libjemalloc-dev \
    linux-tools-common \
    linux-tools-generic \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install kernel-specific perf tools.
# linux-tools-<version>-<flavour> is a stub that symlinks to linux-tools-<version>,
# which contains the actual perf binary — both packages must be installed.
RUN apt-get update \
    && KERNEL_BASE=$(echo "${KERNEL_VERSION}" | sed 's/-[a-z].*$//') \
    && apt-get install -y --no-install-recommends \
       linux-tools-${KERNEL_VERSION} \
       linux-tools-${KERNEL_BASE} \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# R packages (shinyFiles is case-sensitive)
RUN R -e ' \
    options(warn = 2); \
    install.packages(c("shiny", \
                       "shinybusy", \
                       "shinythemes", \
                       "shinyFiles", \
                       "tidyverse", \
                       "stringr", \
                       "PearsonDS", \
                       "LaplacesDemon", \
                       "moments", \
                       "processx", \
                       "rpart", \
                       "regclass", \
                       "sparkline", \
                       "visNetwork", \
                       "fansi", \
                       "yaml", \
                       "gsl", \
                       "DT", \
                       "ggdist", \
                       "GGally", \
                       "changepoint"))'

# Python packages — use a venv so we don't depend on --break-system-packages
# (that flag only exists in pip ≥ 23.0.1 / PEP 668-aware builds)
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# To be replaced with git clone:
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install stragglers, doesn't work otherwise? :/
RUN pip install --no-cache-dir scikit-learn==1.3.2

# To be replaced with git clone:
COPY . /usr/sharp

EXPOSE 2626

CMD ["R", "-e", "shiny::runApp(\"/usr/sharp/gui/app.R\", port=2626, host=\"0.0.0.0\")"]
