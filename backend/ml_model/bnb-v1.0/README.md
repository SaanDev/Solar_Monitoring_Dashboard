# CALLISTO binary model

Exported 2026-10-01T21:45:33 by CALLISTO Trainer 0.1.0.

## What this predicts

Classes: No_Burst, Burst
Input: [1, 224, 224] float32 in [0.0, 1.0]

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

## Decision threshold

Use `0.5634765625`, tuned on the validation split. Do not assume 0.5.

## Validation metrics at export

- accuracy: 0.9458
- precision: 0.9471
- recall: 0.9040
- f1: 0.9251
- roc_auc: 0.9770
- pr_auc: 0.9733
