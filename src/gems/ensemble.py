"""A true deep ensemble of convolutional fault detectors.

Lakshminarayanan, Pritzel & Blundell (NeurIPS 2017), "Simple and Scalable Predictive
Uncertainty Estimation using Deep Ensembles": train M networks from *independent random
initialisations* on *independently ordered data*, keep each member's own predictive
distribution, and decompose the total predictive variance as

    Var(Y) = E_m[p_m (1 - p_m)]  +  Var_m(p_m)
             \____ aleatoric ____/   \_ epistemic _/

for Bernoulli outputs, where epistemic uses the population variance (ddof=0).  No
test-time dropout is used anywhere: the repo's detector has no dropout by design and the
uncertainty comes only from independently trained members.

Target and leakage rules
------------------------
The scored population is "any fault pixel not already captured by USGS/INGENIOUS"
(DrivenData staff, forum topic 11536).  The members are therefore trained on faults from
an *independent* compilation (USGS State Geologic Map Compilation, DS 1052) that the
catalogue does not contain, and no catalogue-derived channel is offered to the network.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import numpy as np

RADIUS_M = 300.0
PIXEL_M = 100.0


@dataclass
class EnsembleConfig:
    n_members_oof: int = 3          # members per fold -> honest out-of-fold ensemble
    n_members_full: int = 5         # members trained on all folds -> submitted map
    n_folds: int = 5
    patch: int = 64
    batch: int = 16
    patches_per_epoch: int = 1536
    epochs: int = 5
    lr: float = 1e-3
    weight_decay: float = 1e-4
    channels: int = 16
    positive_frac: float = 0.5
    spatial_buffer_px: int = 15     # 1,500 m held out around every evaluation fold
    tversky_alpha: float = 0.2
    tversky_beta: float = 0.8
    seed_base: int = 20261002
    tile: int = 512
    tile_stride: int = 448
    threads: int = 2


def blocked_folds(shape: Tuple[int, int], n_folds: int, buffer_px: int) -> List[np.ndarray]:
    """Column strips with a buffer: geology is spatially autocorrelated, so random
    pixel folds leak.  Strips (not quadrants) keep every fold's fault population
    representative of the whole region instead of deleting it."""
    h, w = shape
    edges = np.linspace(0, w, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        m = np.zeros((h, w), bool)
        m[:, edges[i]:edges[i + 1]] = True
        folds.append(m)
    return folds


def _buffered(mask: np.ndarray, buffer_px: int) -> np.ndarray:
    from scipy.ndimage import binary_dilation
    if buffer_px <= 0:
        return mask
    return binary_dilation(mask, np.ones((2 * buffer_px + 1, 2 * buffer_px + 1), bool))


class SmallUNet:
    """A 3-level U-Net with GroupNorm+SiLU, ~105k parameters at channels=16.

    Deliberately small: 2 CPU cores, 3 GB RAM, no GPU.  Depth and receptive field
    (64 px = 6.4 km) matter more than width for 100 m structural detection.
    """

    def __init__(self, cin: int, ch: int = 16, seed: int = 0):
        import torch
        import torch.nn as nn

        torch.manual_seed(seed)
        np.random.seed(seed)

        class Net(nn.Module):
            def __init__(s):
                super().__init__()
                s.d1 = nn.Sequential(nn.Conv2d(cin, ch, 3, padding=1), nn.GroupNorm(4, ch), nn.SiLU(),
                                     nn.Conv2d(ch, ch, 3, padding=1), nn.GroupNorm(4, ch), nn.SiLU())
                s.d2 = nn.Sequential(nn.Conv2d(ch, 2 * ch, 3, padding=1, stride=2), nn.GroupNorm(4, 2 * ch), nn.SiLU(),
                                     nn.Conv2d(2 * ch, 2 * ch, 3, padding=1), nn.GroupNorm(4, 2 * ch), nn.SiLU())
                s.d3 = nn.Sequential(nn.Conv2d(2 * ch, 4 * ch, 3, padding=1, stride=2), nn.GroupNorm(4, 4 * ch), nn.SiLU(),
                                     nn.Conv2d(4 * ch, 4 * ch, 3, padding=1), nn.GroupNorm(4, 4 * ch), nn.SiLU())
                s.up1 = nn.ConvTranspose2d(4 * ch, 2 * ch, 2, stride=2)
                s.u2 = nn.Sequential(nn.Conv2d(4 * ch, 2 * ch, 3, padding=1), nn.GroupNorm(4, 2 * ch), nn.SiLU())
                s.up2 = nn.ConvTranspose2d(2 * ch, ch, 2, stride=2)
                s.u1 = nn.Sequential(nn.Conv2d(2 * ch, ch, 3, padding=1), nn.GroupNorm(4, ch), nn.SiLU())
                s.head = nn.Conv2d(ch, 1, 1)

            def forward(s, x):
                a = s.d1(x)
                b = s.d2(a)
                c = s.d3(b)
                y = s.u2(torch.cat([s.up1(c), b], 1))
                y = s.u1(torch.cat([s.up2(y), a], 1))
                return s.head(y)

        self.net = Net()
        self.seed = seed

    def parameters(self):
        return self.net.parameters()


def tversky_loss(p, y, valid, alpha=0.2, beta=0.8, eps=1e-6):
    """Distance-agnostic Tversky on the valid mask: the same alpha/beta as the metric."""
    import torch
    v = valid.float()
    tp = (p * y * v).sum(dim=(1, 2, 3))
    fp = (p * (1 - y) * v).sum(dim=(1, 2, 3))
    fn = ((1 - p) * y * v).sum(dim=(1, 2, 3))
    return (1.0 - (tp + eps) / (tp + alpha * fp + beta * fn + eps)).mean()


def sample_patches(cube: np.ndarray, target: np.ndarray, eligible: np.ndarray,
                   n: int, patch: int, positive_frac: float, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Balanced patch sampler: half the patches contain target pixels."""
    h, w = target.shape
    half = patch // 2
    ys, xs = np.nonzero(target & eligible)
    ey, ex = np.nonzero(eligible)
    n_pos = int(round(n * positive_frac))
    out_y = np.empty((n, patch, patch), np.uint8)
    out_x = np.empty((n, cube.shape[0], patch, patch), np.float32)
    centers = []
    if len(ys):
        sel = rng.integers(0, len(ys), size=min(n_pos, n))
        centers += [(int(ys[i]), int(xs[i])) for i in sel]
    need = n - len(centers)
    if need > 0 and len(ey):
        sel = rng.integers(0, len(ey), size=need * 3)
        cnt = 0
        for i in sel:
            y, x = int(ey[i]), int(ex[i])
            centers.append((y, x))
            cnt += 1
            if cnt >= need:
                break
        while len(centers) < n:
            centers.append((int(rng.integers(half, h - half)), int(rng.integers(half, w - half))))
    centers = centers[:n]
    for k, (cy, cx) in enumerate(centers):
        y0 = int(np.clip(cy - half, 0, h - patch)); x0 = int(np.clip(cx - half, 0, w - patch))
        out_y[k] = target[y0:y0 + patch, x0:x0 + patch].astype(np.uint8)
        out_x[k] = cube[:, y0:y0 + patch, x0:x0 + patch].astype(np.float32) / 255.0
    valid = np.ones((n, patch, patch), bool)
    return out_x, out_y, valid


def train_member(cube: np.ndarray, target: np.ndarray, eligible: np.ndarray, seed: int,
                 cfg: EnsembleConfig, log=print) -> "SmallUNet":
    import torch

    torch.set_num_threads(cfg.threads)
    model = SmallUNet(cube.shape[0], cfg.channels, seed=seed)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = max(1, cfg.patches_per_epoch // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps * cfg.epochs)
    rng = np.random.default_rng(seed)
    for ep in range(cfg.epochs):
        model.net.train()
        tot = 0.0
        for _ in range(steps):
            x, y, v = sample_patches(cube, target, eligible, cfg.batch, cfg.patch, cfg.positive_frac, rng)
            xt = torch.from_numpy(x); yt = torch.from_numpy(y).unsqueeze(1).float(); vt = torch.from_numpy(v)
            p = torch.sigmoid(model.net(xt))
            loss = tversky_loss(p, yt, vt, cfg.tversky_alpha, cfg.tversky_beta)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += float(loss)
        log(f"    seed {seed} epoch {ep+1}/{cfg.epochs} tversky_loss={tot/steps:.4f}")
    return model


def predict_map(models: Sequence[SmallUNet], cube: np.ndarray, roi: np.ndarray | None,
                cfg: EnsembleConfig, log=print) -> np.ndarray:
    """Tiled inference; returns the mean sigmoid probability over members (float32)."""
    import torch

    torch.set_num_threads(cfg.threads)
    C, H, W = cube.shape
    t, st = cfg.tile, cfg.tile_stride
    acc = np.zeros((H, W), np.float64)
    cnt = np.zeros((H, W), np.float32)
    # only tile the bounding box of the region of interest: folds are column strips, so
    # this cuts out-of-fold inference by n_folds
    y0b, y1b, x0b, x1b = 0, H, 0, W
    if roi is not None and roi.any():
        ry = np.nonzero(roi.any(1))[0]; rx = np.nonzero(roi.any(0))[0]
        y0b, y1b = max(0, int(ry[0]) - t // 8), min(H, int(ry[-1]) + 1 + t // 8)
        x0b, x1b = max(0, int(rx[0]) - t // 8), min(W, int(rx[-1]) + 1 + t // 8)
    ys = list(range(y0b, max(y0b + 1, y1b - t + st), st))
    xs = list(range(x0b, max(x0b + 1, x1b - t + st), st))
    if y1b - y0b > t: ys.append(max(y0b, y1b - t))
    if x1b - x0b > t: xs.append(max(x0b, x1b - t))
    ys = sorted(set(min(max(y, y0b), max(y0b, y1b - t)) for y in ys)) or [y0b]
    xs = sorted(set(min(max(x, x0b), max(x0b, x1b - t)) for x in xs)) or [x0b]
    for m in models:
        m.net.eval()
    with torch.no_grad():
        for y0 in ys:
            for x0 in xs:
                y1, x1 = min(y0 + t, y1b), min(x0 + t, x1b)
                blk = cube[:, y0:y1, x0:x1].astype(np.float32) / 255.0
                pad = np.zeros((C, t, t), np.float32)
                pad[:, :blk.shape[1], :blk.shape[2]] = blk
                xt = torch.from_numpy(pad).unsqueeze(0)
                out = np.zeros((t, t), np.float32)
                for m in models:
                    out += torch.sigmoid(m.net(xt))[0, 0].numpy()
                out /= max(1, len(models))
                cy0, cx0 = (y0 + t // 8, x0 + t // 8) if (y0 > 0 and x0 > 0) else (y0, x0)
                cy1, cx1 = min(H, cy0 + (t - 2 * (cy0 - y0))), min(W, cx0 + (t - 2 * (cx0 - x0)))
                oy0, ox0 = cy0 - y0, cx0 - x0
                acc[cy0:cy1, cx0:cx1] += out[oy0:oy0 + (cy1 - cy0), ox0:ox0 + (cx1 - cx0)].astype(np.float64)
                cnt[cy0:cy1, cx0:cx1] += 1.0
    cnt[cnt == 0] = 1.0
    p = (acc / cnt).astype(np.float32)
    if roi is not None:
        p[~roi] = 0.0
    return p


def predict_members(models: Sequence[SmallUNet], cube: np.ndarray, roi: np.ndarray | None,
                    cfg: EnsembleConfig) -> np.ndarray:
    """Per-member probability maps stacked as (M, H, W) - the input to the variance split."""
    out = np.zeros((len(models),) + cube.shape[1:], np.float32)
    for i, m in enumerate(models):
        out[i] = predict_map([m], cube, roi, cfg, log=lambda *_: None)
    return out


def decompose(member_probs: np.ndarray) -> dict:
    """Total = epistemic + aleatoric for Bernoulli members (NeurIPS 2017 deep ensembles)."""
    mean = member_probs.mean(0)
    epistemic = member_probs.var(0, ddof=0)                      # Var_m(p_m)
    aleatoric = (member_probs * (1.0 - member_probs)).mean(0)     # E_m[p_m (1 - p_m)]
    return dict(mean=mean.astype(np.float32), epistemic=epistemic.astype(np.float32),
                aleatoric=aleatoric.astype(np.float32),
                total=(epistemic + aleatoric).astype(np.float32))
