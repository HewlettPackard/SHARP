FROM python:3.10-slim

RUN pip install --no-cache-dir numpy

WORKDIR /benchmarks

# Copy I/O benchmark Python file
COPY swapbytes.py .

# Default entrypoint (can be overridden)
CMD ["python3", "swapbytes.py"]
