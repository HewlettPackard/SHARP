FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir numba numpy

WORKDIR /benchmarks

# Copy all GPU benchmark Python files
COPY cuda-inc.py .
COPY cuda-matmul.py .

# Default entrypoint (can be overridden)
CMD ["python3", "cuda-inc.py", "10000", "0"]
