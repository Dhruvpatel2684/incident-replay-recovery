FROM ubuntu:22.04

RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    pip3 install uv && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY runtime/ ./runtime/

RUN mkdir -p /app/runtime/output /logs/verifier

CMD ["sleep", "infinity"]
