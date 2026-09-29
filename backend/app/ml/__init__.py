"""Native ML inference for solar radio bursts (CCM v2.0).

Self-contained port of the CALLISTO Trainer's region-based inference — no
separate microservice needed. PyTorch + torchvision are required only when burst
detection is enabled; install with:

    pip install -e ".[ml]"

The model checkpoint (``ccm_v2_0.pt``, ~43 MB) ships in the repo via Git LFS at
backend/ml_model/ccm_v2_0.pt. A normal clone fetches it automatically when Git
LFS is installed:

    git lfs install      # one-time, per machine
    git lfs pull         # fetch the checkpoint (and any other LFS files)

As a fallback for environments without Git LFS, set ML_MODEL_URL in .env and
run the manual download script:

    python scripts/download_model.py

Modules, in the order a file flows through them:

* ``preprocessing`` — FITS + physical axes, whole-file normalization, region views
* ``regions``       — candidate-region finder
* ``physics`` / ``region_features`` — the 28 measured features per region
* ``model``         — the network
* ``inference``     — loading, scoring and the file-level verdict
* ``registry``      — which models exist and which one is active
"""
