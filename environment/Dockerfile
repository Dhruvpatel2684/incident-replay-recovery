FROM python:3.11-slim

WORKDIR /app

COPY runtime/ ./runtime/

RUN pip3 install pytest

CMD ["python3", "/app/runtime/consensus_engine.py"]
