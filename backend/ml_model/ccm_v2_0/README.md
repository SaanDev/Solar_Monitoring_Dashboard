# CALLISTO unified model

Exported 2026-09-29T19:10:16 by CALLISTO Trainer 0.1.0.

## What this predicts

Classes: No_Burst, RFI, Type II, Type III, Type IIIG, Other
Input: [3, 224, 224] float32 in [0.0, 1.0]

## Contents

| File | Purpose |
|---|---|
| `model_card.json` | the full input contract, classes and metrics |
| `weights.pt` | state dict for rebuilding the model in this project |
| `checkpoint.pt` | the original checkpoint, config included |
| `config.yaml` | the training configuration |
| `model_scripted.pt` | TorchScript graph; runs without this project's code |
| `predict.py` | standalone example using only numpy, astropy and torch |

## Using it

```bash
python predict.py path/to/file.fit.gz
```

## The input contract

The model is only valid on input prepared exactly this way:

1. replace NaN/Inf with the finite median
2. subtract per-frequency median over time, scale to dB (plotutil_median_db)
3. map [-1.0, 8.0] dB to [0, 1] and clip
4. bilinear resize to the input shape

**Background subtraction MUST be computed over the whole file's time axis before any cropping. Cropping first makes a burst its own background and erases it.**

## Scope

**This model was trained on cropped burst regions. Running it on a whole-file spectrum is out of distribution and its output should not be trusted. Locate a region first, then crop it the same way.**

Crops are taken as the exact region given, with no context margin, then resized.

## Second input: measured physics

This model takes **two** inputs. The second is a 28-element float32 vector:

```
log_freq_start, log_freq_end, log_bandwidth, log_duration, signed_log_drift, signed_log_relative_drift, fit_quality, measured, outside_persistence, band_fraction, simultaneity, log_onset_spread, log_thickness_time, log_thickness_freq, fill_fraction, log_snr, peakiness, periodicity, log_period, duration_fraction, rfi_flag_fraction, burst_count, log_rows, log_cols, file_bright_fraction, file_noise, log_freq_mid, faint
```

This model takes a SECOND input: the region's physics and interference features, computed from the whole-file normalized spectrum by callisto_trainer.core.region_features. They are always measured in training, so all zeros is out of distribution: use this project (CascadePredictor) to run the model on real files.

## Validation metrics at export

- accuracy: 0.9679
- macro_f1: 0.8390
