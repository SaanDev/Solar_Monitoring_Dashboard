FROM python:3.11-slim

WORKDIR /app

# Make pip resilient to slow mirrors and large wheels (torch, scipy) so a transient
# network hiccup during a long download doesn't fail the whole image build.
ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=5 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg backs the Data Analysis movie export (MP4). gcc/g++/gfortran + libpq are a
# safety net so any dependency lacking a prebuilt wheel for this architecture can
# still build from source instead of aborting.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ gfortran libpq-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# 1) Core backend + the multi-mission Solar Image Analysis stack (SunPy/Fido,
#    drms, reproject, aiapy, imageio — now core dependencies). This is everything
#    the dashboard needs to serve every page. `-e .` resolves the deps from
#    pyproject.toml; the `app/` package itself is provided at runtime (WORKDIR
#    /app is on sys.path and the source is bind-mounted / COPY'd below).
RUN pip install -e . \
    && python -c "import sunpy, drms, reproject, astropy, aiapy; print('scientific stack OK')"

# 2) Radio-burst ML classifier (PyTorch). It is large and occasionally flaky to
#    download, so it lives in its own layer gated behind INSTALL_ML. Set
#    INSTALL_ML=false (e.g. on a resource-constrained machine, or an Apple-Silicon
#    Mac where the emulated/arm64 torch build OOMs) for a lean image that runs the
#    whole dashboard EXCEPT native burst detection. Containers have no GPU, so on
#    amd64 we pull the smaller CPU-only wheel from PyTorch's index; arm64 already
#    gets CPU-only from PyPI. TARGETARCH is auto-populated by BuildKit.
ARG INSTALL_ML=true
ARG TARGETARCH
RUN if [ "$INSTALL_ML" = "true" ]; then \
        if [ "$TARGETARCH" = "amd64" ]; then \
            pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
        fi && \
        pip install -e ".[ml]"; \
    else \
        echo ">> INSTALL_ML=$INSTALL_ML — skipping PyTorch; native burst detection is disabled in this image"; \
    fi

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
