FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY runtime/ /app/runtime/

RUN mkdir -p /app/runtime/output /logs/verifier

CMD ["sleep", "infinity"]
