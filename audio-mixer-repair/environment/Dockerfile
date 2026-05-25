FROM python:3.11-slim

WORKDIR /app

COPY runtime/ ./runtime/

RUN pip install --no-cache-dir uv

CMD ["python", "runtime/mixer.py"]
