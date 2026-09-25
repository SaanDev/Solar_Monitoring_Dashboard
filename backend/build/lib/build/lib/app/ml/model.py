"""PyTorch model classes for the burst classifier.

Ported from Burst Identifier:
  src/models/model_factory.py
  src/models/metadata_model.py
  src/models/simple_cnn.py

Requires: torch, torchvision  (install with pip install -e "[ml]")
"""
from __future__ import annotations

import math
from typing import Any

import torch
from torch import nn


# ─── SmallBurstCNN (CNN-only baseline) ───────────────────────────────────────

class SmallBurstCNN(nn.Module):
    """Compact binary classifier for 1×224×224 dynamic spectra."""

    def __init__(self, in_channels: int = 1, dropout: float = 0.25) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128), nn.ReLU(inplace=True), nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Dropout(dropout), nn.Linear(128, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x)).squeeze(1)


# ─── MetadataConditionedModel ─────────────────────────────────────────────────

class MetadataConditionedModel(nn.Module):
    """Image backbone fused with station/frequency/date metadata."""

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
        self.station_embedding = nn.Embedding(int(num_stations), int(station_emb_dim))
        self.meta_mlp = nn.Sequential(
            nn.Linear(int(station_emb_dim) + int(num_numeric), meta_hidden),
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
        station = meta[:, 0].long().clamp_(0, self.station_embedding.num_embeddings - 1)
        numeric = meta[:, 1:]
        meta_features = self.meta_mlp(
            torch.cat([self.station_embedding(station), numeric], dim=1)
        )
        return self.classifier(torch.cat([features, meta_features], dim=1)).squeeze(1)


# ─── Factory ──────────────────────────────────────────────────────────────────

def _instantiate_tv(model_fn, pretrained: bool):
    if not pretrained:
        return model_fn(weights=None), False
    try:
        return model_fn(weights="DEFAULT"), True
    except Exception:
        return model_fn(weights=None), False


def _find_first_conv(module: nn.Module):
    for name, child in module.named_children():
        if isinstance(child, nn.Conv2d):
            return module, name, child
        found = _find_first_conv(child)
        if found is not None:
            return found
    return None


def _adapt_first_conv(module: nn.Module, in_channels: int) -> None:
    found = _find_first_conv(module)
    if found is None or found[2].in_channels == in_channels:
        return
    parent, name, old = found
    replacement = nn.Conv2d(
        in_channels, old.out_channels, kernel_size=old.kernel_size,
        stride=old.stride, padding=old.padding, dilation=old.dilation,
        groups=old.groups, bias=old.bias is not None,
        padding_mode=old.padding_mode,
    )
    with torch.no_grad():
        weight = old.weight.detach()
        if in_channels == 1:
            new_weight = weight.sum(dim=1, keepdim=True)
        else:
            repeat = int(math.ceil(in_channels / old.in_channels))
            new_weight = weight.repeat(1, repeat, 1, 1)[:, :in_channels]
            new_weight = new_weight * (old.in_channels / in_channels)
        replacement.weight.copy_(new_weight)
        if old.bias is not None:
            replacement.bias.copy_(old.bias.detach())
    setattr(parent, name, replacement)


def _replace_first_conv(module: nn.Module, in_channels: int) -> bool:
    for name, child in module.named_children():
        if isinstance(child, nn.Conv2d):
            replacement = nn.Conv2d(
                in_channels, child.out_channels, kernel_size=child.kernel_size,
                stride=child.stride, padding=child.padding, dilation=child.dilation,
                groups=child.groups, bias=child.bias is not None,
                padding_mode=child.padding_mode,
            )
            setattr(module, name, replacement)
            return True
        if _replace_first_conv(child, in_channels):
            return True
    return False


def _build_tv_backbone(normalized_name: str, in_channels: int, dropout: float, pretrained: bool):
    """Build a torchvision backbone, return (backbone, feature_dim)."""
    try:
        import torchvision.models as tv
    except ImportError as exc:
        raise ImportError(
            "torchvision is required for ResNet/EfficientNet models. "
            "Install with: pip install -e '.[ml]'"
        ) from exc

    if normalized_name == "resnet18":
        model, used_pretrained = _instantiate_tv(tv.resnet18, pretrained)
        ((_adapt_first_conv if used_pretrained else lambda m, c: _replace_first_conv(m, c))(model, in_channels))
        feature_dim = model.fc.in_features
        model.fc = nn.Identity()
        return model, feature_dim

    if normalized_name == "efficientnet_b0":
        model, used_pretrained = _instantiate_tv(tv.efficientnet_b0, pretrained)
        ((_adapt_first_conv if used_pretrained else lambda m, c: _replace_first_conv(m, c))(model, in_channels))
        feature_dim = model.classifier[-1].in_features
        model.classifier[-1] = nn.Identity()
        return model, feature_dim

    if normalized_name == "mobilenet_v3_small":
        model, used_pretrained = _instantiate_tv(tv.mobilenet_v3_small, pretrained)
        ((_adapt_first_conv if used_pretrained else lambda m, c: _replace_first_conv(m, c))(model, in_channels))
        feature_dim = model.classifier[-1].in_features
        model.classifier[-1] = nn.Identity()
        return model, feature_dim

    raise ValueError(f"Unsupported model name: {normalized_name}")


def _build_tv_classifier(
    normalized_name: str, in_channels: int, num_classes: int
) -> nn.Module:
    """A torchvision backbone with its own head resized to ``num_classes``.

    Deliberately separate from :func:`_build_tv_backbone`, which replaces the
    head with ``Identity`` for feature extraction. The multi-class burst-type
    checkpoint was saved from a plain torchvision model whose head was swapped
    in place, so its state-dict keys are ``conv1.*`` / ``fc.*``. Wrapping a
    feature backbone in ``nn.Sequential`` would produce ``0.*`` / ``1.*`` instead
    and fail a strict load.
    """
    try:
        import torchvision.models as tv
    except ImportError as exc:
        raise ImportError(
            "torchvision is required for ResNet/EfficientNet models. "
            "Install with: pip install -e '.[ml]'"
        ) from exc

    if normalized_name == "resnet18":
        model = tv.resnet18(weights=None)
        _replace_first_conv(model, in_channels)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        return model

    if normalized_name in {"efficientnet_b0", "mobilenet_v3_small"}:
        factory = getattr(tv, normalized_name)
        model = factory(weights=None)
        _replace_first_conv(model, in_channels)
        head = model.classifier[-1]
        model.classifier[-1] = nn.Linear(head.in_features, num_classes)
        return model

    raise ValueError(f"Unsupported model name: {normalized_name}")


def create_type_model(
    name: str,
    in_channels: int = 1,
    dropout: float = 0.25,
    *,
    num_classes: int = 3,
) -> nn.Module:
    """Create the multi-class burst-type classifier (image-only, softmax head).

    ``dropout`` is accepted for config symmetry but not applied: the trainer
    wraps ``avgpool`` in a Dropout, which contributes no parameters and is inert
    in ``eval()`` mode, so omitting it keeps the state dict loadable and the
    outputs identical.
    """
    normalized = name.lower().replace("-", "_")
    if normalized in {"simple_cnn", "small_cnn", "baseline"}:
        base = SmallBurstCNN(in_channels=in_channels, dropout=dropout)
        base.classifier[-1] = nn.Linear(128, num_classes)
        return base
    return _build_tv_classifier(normalized, in_channels, num_classes)


def create_model(
    name: str,
    in_channels: int = 1,
    dropout: float = 0.25,
    *,
    pretrained: bool = False,
    use_metadata: bool = False,
    num_stations: int = 1,
    num_numeric: int = 6,
    station_emb_dim: int = 8,
) -> nn.Module:
    """Create a binary classifier by name, with optional metadata fusion."""
    normalized = name.lower().replace("-", "_")

    if normalized in {"simple_cnn", "small_cnn", "baseline"}:
        base = SmallBurstCNN(in_channels=in_channels, dropout=dropout)
        if not use_metadata:
            return base
        backbone = nn.Sequential(base.features, nn.Flatten(1), nn.Dropout(dropout))
        return MetadataConditionedModel(
            backbone, feature_dim=128,
            num_stations=num_stations, num_numeric=num_numeric,
            station_emb_dim=station_emb_dim, dropout=dropout,
        )

    if not use_metadata:
        # Image-only classifier: build backbone then re-attach a [feat_dim → 1] head.
        backbone, feature_dim = _build_tv_backbone(normalized, in_channels, dropout, pretrained)
        return nn.Sequential(backbone, nn.Linear(feature_dim, 1))

    backbone, feature_dim = _build_tv_backbone(normalized, in_channels, dropout, pretrained)
    return MetadataConditionedModel(
        backbone, feature_dim=feature_dim,
        num_stations=num_stations, num_numeric=num_numeric,
        station_emb_dim=station_emb_dim, dropout=dropout,
    )
