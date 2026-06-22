FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Install with the [ml] extras so the radio-burst classifier (PyTorch) runs
# natively in this container. Containers have no GPU, so prefer CPU-only torch:
# on amd64 (Windows / Linux x86) pull the CPU wheel from PyTorch's index to skip
# the ~2.5 GB CUDA build; on arm64 (Apple Silicon) PyPI already serves CPU-only.
# TARGETARCH is auto-populated by BuildKit; if empty (classic builder) we fall
# through to the default index, which still works.
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi && \
    pip install --no-cache-dir -e ".[ml]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
