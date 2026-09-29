"""The CCM v2.0 network: one backbone over several views, fused with region features.

Ported from the CALLISTO Trainer (``core/models/physics_model.py`` and the
backbone half of ``core/models/model_factory.py``). Only the architecture the
shipped checkpoint uses is rebuilt here; weights always come from its state
dict, so nothing is downloaded.

Requires: torch, torchvision  (install with pip install -e ".[ml]")
"""
from __future__ import annotations

from typing import Any

import torch
from torch import nn


class RegionContextModel(nn.Module):
    """One shared backbone embeds each view; embeddings meet the feature MLP.

    The views (exact crop, wide context strip, quiet-background strip) are not
    pixel-aligned, so they are embedded one at a time by the same backbone rather
    than stacked as input channels. The input stays a single ``[B, V, H, W]``
    tensor.
    """

    def __init__(
        self,
        backbone: nn.Module,
        feature_dim: int,
        num_views: int,
        num_features: int,
        num_classes: int,
        hidden: int = 64,
        dropout: float = 0.25,
    ) -> None:
        super().__init__()
        self.backbone = backbone
        self.feature_dim = int(feature_dim)
        self.num_views = int(num_views)
        self.num_features = int(num_features)
        self.num_classes = int(num_classes)

        self.feature_mlp = nn.Sequential(
            nn.Linear(self.num_features, hidden),
            nn.ReLU(inplace=True),
            nn.Linear(hidden, hidden),
            nn.ReLU(inplace=True),
        )
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(self.feature_dim * self.num_views + hidden, self.num_classes),
        )

    def forward(self, image: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        batch = image.shape[0]
        views = image.reshape(batch * self.num_views, 1, image.shape[-2], image.shape[-1])
        embedded = self.backbone(views)
        if embedded.dim() > 2:
            embedded = torch.flatten(embedded, 1)
        embedded = embedded.reshape(batch, self.num_views * self.feature_dim)
        return self.classifier(torch.cat([embedded, self.feature_mlp(features)], dim=1))


def _resnet18_backbone(in_channels: int) -> tuple[nn.Module, int]:
    """ResNet-18 feature extractor (head removed) with an ``in_channels`` stem."""
    try:
        import torchvision.models as tv
    except ImportError as exc:
        raise ImportError(
            "torchvision is required for the burst model. Install with: pip install -e '.[ml]'"
        ) from exc

    model = tv.resnet18(weights=None)
    old = model.conv1
    model.conv1 = nn.Conv2d(
        in_channels, old.out_channels, kernel_size=old.kernel_size, stride=old.stride,
        padding=old.padding, dilation=old.dilation, groups=old.groups,
        bias=old.bias is not None, padding_mode=old.padding_mode,
    )
    feature_dim = model.fc.in_features
    model.fc = nn.Identity()
    return model, feature_dim


def build_model(model_cfg: dict[str, Any], num_classes: int, num_features: int) -> nn.Module:
    """Rebuild the architecture a checkpoint's ``model`` config describes."""
    name = str(model_cfg.get("name", "")).lower().replace("-", "_")
    if name != "resnet18":
        raise ValueError(f"unsupported backbone {model_cfg.get('name')!r} (expected resnet18)")
    backbone, feature_dim = _resnet18_backbone(int(model_cfg.get("in_channels", 1)))
    return RegionContextModel(
        backbone,
        feature_dim=feature_dim,
        num_views=len(model_cfg.get("views") or ["crop"]),
        num_features=num_features,
        num_classes=num_classes,
        dropout=float(model_cfg.get("dropout", 0.25)),
    )
