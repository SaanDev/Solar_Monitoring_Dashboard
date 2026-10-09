"""The BnB network: a ResNet over the whole file, fused with file metadata.

Ported from the CALLISTO Trainer (``core/models/metadata_model.py`` and the
backbone half of ``core/models/model_factory.py``). Only the architecture the
shipped checkpoint uses is rebuilt here; weights always come from its state
dict, so nothing is downloaded.

Requires: torch, torchvision  (install with pip install -e ".[ml]")
"""
from __future__ import annotations

from typing import Any

import torch
from torch import nn

_RESNETS = ("resnet18", "resnet34", "resnet50")


class MetadataConditionedModel(nn.Module):
    """Image backbone fused with station / frequency / date metadata.

    The station is embedded, concatenated with the numeric features and passed
    through a small MLP; the result joins the image features before a single
    burst logit.
    """

    def __init__(
        self,
        backbone: nn.Module,
        feature_dim: int,
        num_stations: int,
        num_numeric: int,
        station_emb_dim: int = 8,
        meta_hidden: int = 32,
        dropout: float = 0.25,
    ) -> None:
        super().__init__()
        self.backbone = backbone
        self.feature_dim = int(feature_dim)
        self.num_stations = int(num_stations)
        self.num_numeric = int(num_numeric)

        self.station_embedding = nn.Embedding(self.num_stations, int(station_emb_dim))
        self.meta_mlp = nn.Sequential(
            nn.Linear(int(station_emb_dim) + self.num_numeric, meta_hidden),
            nn.ReLU(inplace=True),
            nn.Linear(meta_hidden, meta_hidden),
            nn.ReLU(inplace=True),
        )
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(self.feature_dim + meta_hidden, 1),
        )

    def forward(self, image: torch.Tensor, meta: torch.Tensor) -> torch.Tensor:
        features = self.backbone(image)
        if features.dim() > 2:
            features = torch.flatten(features, 1)
        # meta is float32 [B, 1 + num_numeric]: column 0 is the station index.
        station = meta[:, 0].long().clamp_(0, self.num_stations - 1)
        numeric = meta[:, 1 : 1 + self.num_numeric]
        meta_features = self.meta_mlp(torch.cat([self.station_embedding(station), numeric], dim=1))
        return self.classifier(torch.cat([features, meta_features], dim=1)).squeeze(1)


def _resnet_backbone(name: str, in_channels: int) -> tuple[nn.Module, int]:
    """ResNet feature extractor (head removed) with an ``in_channels`` stem."""
    try:
        import torchvision.models as tv
    except ImportError as exc:
        raise ImportError(
            "torchvision is required for the burst model. Install with: pip install -e '.[ml]'"
        ) from exc

    model = getattr(tv, name)(weights=None)
    old = model.conv1
    model.conv1 = nn.Conv2d(
        in_channels, old.out_channels, kernel_size=old.kernel_size, stride=old.stride,
        padding=old.padding, dilation=old.dilation, groups=old.groups,
        bias=old.bias is not None, padding_mode=old.padding_mode,
    )
    feature_dim = model.fc.in_features
    model.fc = nn.Identity()
    return model, feature_dim


def build_model(model_cfg: dict[str, Any], num_numeric: int) -> nn.Module:
    """Rebuild the architecture a checkpoint's ``model`` config describes."""
    name = str(model_cfg.get("name", "")).lower().replace("-", "_")
    if name not in _RESNETS:
        raise ValueError(f"unsupported backbone {model_cfg.get('name')!r} (expected one of {_RESNETS})")
    if not model_cfg.get("use_metadata"):
        raise ValueError("expected a metadata-conditioned binary model (model.use_metadata)")
    backbone, feature_dim = _resnet_backbone(name, int(model_cfg.get("in_channels", 1)))
    return MetadataConditionedModel(
        backbone,
        feature_dim=feature_dim,
        # The known stations plus the unknown slot (0).
        num_stations=len(model_cfg.get("station_vocab") or {}) + 1,
        num_numeric=num_numeric,
        station_emb_dim=int(model_cfg.get("station_emb_dim", 8)),
        dropout=float(model_cfg.get("dropout", 0.25)),
    )
