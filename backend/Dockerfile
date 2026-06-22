FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Install with the [ml] extras so the radio-burst classifier (PyTorch) runs
# natively in this container. On linux/arm64 (Apple Silicon Macs) PyPI serves a
# CPU-only wheel automatically; on linux/amd64 it serves the CUDA build, which
# still runs on CPU inside the container (just a larger image).
RUN pip install --no-cache-dir -e ".[ml]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
