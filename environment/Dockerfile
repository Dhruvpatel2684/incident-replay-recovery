FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

RUN mkdir -p /app/runtime/data /solution /logs/verifier /output

COPY runtime/ /app/runtime/

WORKDIR /app

CMD ["sleep", "infinity"]
