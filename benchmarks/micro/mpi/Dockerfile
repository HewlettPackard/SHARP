FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenmpi-dev \
    && rm -rf /var/lib/apt/lists*

RUN pip install --no-cache-dir mpi4py numpy

WORKDIR /benchmarks

# Copy MPI benchmark Python file
COPY mpi-pingpong-single.py .

# Default entrypoint (can be overridden)
CMD ["python3", "mpi-pingpong-single.py"]
