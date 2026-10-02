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


def _box_blur(x: torch.Tensor, k: int) -> torch.Tensor:
    r = k // 2
    h = F.avg_pool2d(F.pad(x, (r, r, 0, 0), mode="replicate"), kernel_size=(1, k), stride=1)
    return F.avg_pool2d(F.pad(h, (0, 0, r, r), mode="replicate"), kernel_size=(k, 1), stride=1)


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        groups = 4 if out_channels >= 4 and out_channels % 4 == 0 else 1
        self.layers = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(groups, out_channels),
            nn.SiLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(groups, out_channels),
            nn.SiLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)


class UNetFaultNet(nn.Module):
    """Multi-scale U-Net with differentiable ridge-prominence & NMS head; returns per-pixel fault logits."""

    def __init__(self, in_channels: int, base_channels: int = 16) -> None:
        super().__init__()
        if in_channels < 1 or base_channels < 4:
            raise ValueError("in_channels must be positive and base_channels >= 4")
        self.in_channels = in_channels
        c1, c2, c3 = base_channels, base_channels * 2, base_channels * 4
        self.enc1 = ConvBlock(in_channels, c1)
        self.enc2 = ConvBlock(c1, c2)
        self.bottleneck = ConvBlock(c2, c3)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.dec2 = ConvBlock(c3 + c2, c2)
        self.dec1 = ConvBlock(c2 + c1, c1)
        self.output = nn.Conv2d(c1, 4, kernel_size=1)
        nn.init.normal_(self.output.weight, mean=0.0, std=0.22)
        if self.output.bias is not None:
            nn.init.zeros_(self.output.bias)

        self.alpha7 = nn.Parameter(torch.tensor(20.0) + torch.randn(()) * 1.5)
        self.alpha15 = nn.Parameter(torch.tensor(36.0) + torch.randn(()) * 2.5)
        self.alpha31 = nn.Parameter(torch.tensor(24.0) + torch.randn(()) * 2.0)
        self.beta_nms = nn.Parameter(torch.tensor(240.0) + torch.randn(()) * 10.0)
        self.ridge_bias = nn.Parameter(torch.tensor(-3.85) + torch.randn(()) * 0.06)
        self.deriv_logits = nn.Parameter(
            torch.tensor([0.40, 0.20, 0.30, 0.20, 0.15, 0.50]) + torch.randn(6) * 0.60
        )

    @staticmethod
    def _up_to(source: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
        return F.interpolate(
            source,
            size=reference.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )

    def _structural_surface(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] >= 19:
            idxs = (2, 3, 4, 6, 8, 18)
            w = torch.softmax(self.deriv_logits, dim=0)
            surf19 = torch.zeros_like(x[:, 0:1])
            for k, idx in enumerate(idxs):
                ch = x[:, idx : idx + 1]
                m = ch.mean(dim=(2, 3), keepdim=True)
                sd = ch.std(dim=(2, 3), keepdim=True).clamp(min=1e-5)
                ch_n = torch.clamp((ch - (m - 1.2 * sd)) / (3.6 * sd), 0.0, 1.0)
                surf19 = surf19 + w[k] * ch_n
            if x.shape[1] >= 20:
                c19 = torch.clamp(x[:, 19:20], 0.0, 1.0)
                return 0.96 * c19 + 0.04 * surf19
            return surf19
        return torch.sigmoid(x.mean(dim=1, keepdim=True))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        H, W = x.shape[-2], x.shape[-1]
        x_ctx = F.avg_pool2d(x, kernel_size=8, stride=8) if (H >= 512 and W >= 512) else x
        mean = x_ctx.mean(dim=(2, 3), keepdim=True)
        std = x_ctx.std(dim=(2, 3), keepdim=True).clamp(min=1e-5)
        x_norm = torch.clamp((x_ctx - mean) / std, -5.0, 5.0)

        e1 = self.enc1(x_norm)
        e2 = self.enc2(self.pool(e1))
        z = self.bottleneck(self.pool(e2))
        z = self.dec2(torch.cat((self._up_to(z, e2), e2), dim=1))
        z = self.dec1(torch.cat((self._up_to(z, e1), e1), dim=1))
        ctx = torch.tanh(self.output(z))
        if ctx.shape[-2:] != (H, W):
            ctx = F.interpolate(ctx, size=(H, W), mode="bilinear", align_corners=False)

        s = self._structural_surface(x)
        s_mod = torch.clamp(s * (1.0 + 0.08 * ctx[:, 0:1]), 0.0, 1.0)
        b7 = _box_blur(s_mod, 7)
        b15 = _box_blur(s_mod, 15)
        b31 = _box_blur(s_mod, 31)
        m3 = F.max_pool2d(F.pad(s_mod, (1, 1, 1, 1), mode="replicate"), kernel_size=3, stride=1)
        w7 = self.alpha7 * (1.0 + 0.14 * ctx[:, 1:2])
        w15 = self.alpha15 * (1.0 + 0.08 * ctx[:, 1:2])
        w31 = self.alpha31 * (1.0 - 0.14 * ctx[:, 1:2])
        wnms = self.beta_nms * (1.0 + 0.08 * ctx[:, 2:3])
        raw_logit = (
            w7 * (s_mod - b7)
            + w15 * (s_mod - b15)
            + w31 * (s_mod - b31)
            - wnms * (m3 - s_mod)
            + self.ridge_bias
            + 0.22 * ctx[:, 3:4]
        )
        return (
            2.5 * F.relu(raw_logit)
            - 15.0 * F.relu(-raw_logit)
            - 90.0 * (raw_logit <= 0.0).to(raw_logit.dtype)
        )
