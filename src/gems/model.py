"""A compact segmentation network used by independently trained ensemble members.

There is intentionally no dropout layer: ensemble diversity comes from separately
initialized models, independent optimizer/training randomness, and (optionally)
small feature/patch augmentations—not Monte Carlo dropout at inference.
"""

from __future__ import annotations

try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError as exc:  # pragma: no cover - requires optional model dependency
    raise RuntimeError("The model requires PyTorch; install requirements-model.txt") from exc


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)


class UNetFaultNet(nn.Module):
    """Three-scale U-Net; returns per-pixel fault logits, not probabilities."""

    def __init__(self, in_channels: int, base_channels: int = 24) -> None:
        super().__init__()
        if in_channels < 1 or base_channels < 4:
            raise ValueError("in_channels must be positive and base_channels >= 4")
        c1, c2, c3, c4 = base_channels, base_channels * 2, base_channels * 4, base_channels * 8
        self.enc1 = ConvBlock(in_channels, c1)
        self.enc2 = ConvBlock(c1, c2)
        self.enc3 = ConvBlock(c2, c3)
        self.bottleneck = ConvBlock(c3, c4)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.dec3 = ConvBlock(c4 + c3, c3)
        self.dec2 = ConvBlock(c3 + c2, c2)
        self.dec1 = ConvBlock(c2 + c1, c1)
        self.output = nn.Conv2d(c1, 1, kernel_size=1)

    @staticmethod
    def _up_to(source: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
        return F.interpolate(
            source,
            size=reference.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        z = self.bottleneck(self.pool(e3))
        z = self.dec3(torch.cat((self._up_to(z, e3), e3), dim=1))
        z = self.dec2(torch.cat((self._up_to(z, e2), e2), dim=1))
        z = self.dec1(torch.cat((self._up_to(z, e1), e1), dim=1))
        return self.output(z)
