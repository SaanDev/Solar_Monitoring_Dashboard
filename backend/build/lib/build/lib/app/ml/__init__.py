"""Native ML inference for solar radio-burst classification.

Self-contained port of the Burst Identifier inference pipeline — no separate
microservice needed. PyTorch + torchvision are required only when burst
detection is enabled; install with:

    pip install -e ".[ml]"

The model checkpoint (best.pt, ~128 MB) ships in the repo via Git LFS at
backend/ml_model/best.pt. A normal clone fetches it automatically when Git LFS
is installed:

    git lfs install      # one-time, per machine
    git lfs pull         # fetch the checkpoint (and any other LFS files)

As a fallback for environments without Git LFS, set ML_MODEL_URL in .env and
run the manual download script:

    python scripts/download_model.py
"""
