FROM python:3.11-slim

WORKDIR /app

# Install pytest for test execution
RUN pip install --no-cache-dir pytest

# Copy runtime into the container
COPY runtime/ /app/runtime/

# Create output and logs directories
RUN mkdir -p /app/runtime/output /logs/verifier

ENTRYPOINT ["python3", "/app/runtime/run_auditor.py"]
