FROM ubuntu:22.04

RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install pytest && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY runtime/ ./runtime/

CMD ["python3", "/app/runtime/run_resolver.py"]
