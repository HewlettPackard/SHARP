FROM python:3.10-slim

RUN pip install --no-cache-dir numpy flask

WORKDIR /benchmarks

# Copy all CPU benchmark Python files
COPY sleep.py .
COPY nope.py .
COPY inc.py .
COPY matmul.py .
COPY bounce.py .

# Default entrypoint (can be overridden)
CMD ["python3", "sleep.py", "1.0"]
