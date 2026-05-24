FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-minimal \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime

WORKDIR /opt/replay-recovery

COPY runtime/ ./runtime/
COPY validator/ ./validator/
COPY repair/ ./repair/

RUN chmod +x validator/run_audit.sh repair/run_repair.sh
