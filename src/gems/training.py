"""Patch-sampled training for genuinely independent ensemble members."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def _dependencies():
    try:
        import numpy as np
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:  # pragma: no cover - optional model dependency
        raise RuntimeError("Training requires numpy, rasterio, scipy, and PyTorch") from exc
    return np, torch, nn, DataLoader, Dataset


def train_members(
    *,
    feature_path: str | Path,
    label_path: str | Path,
    label_observed_path: str | Path,
    footprint_path: str | Path,
    training_mask: Any,
    output_dir: str | Path,
    ensemble_size: int,
    seed_base: int,
    patch_size: int,
    patches_per_epoch: int,
    batch_size: int,
    epochs: int,
    learning_rate: float,
    unlabeled_loss_weight: float,
    device: str | None = None,
) -> list[dict[str, Any]]:
    """Fit M separate U-Nets on the same eligible data with independent seeds.

    The input labels are known catalogue faults. Unlabelled background is not a
    verified negative set, so its loss is downweighted. Each ensemble member is
    initialized and optimized from scratch; no test-time dropout is involved.
    """
    np, torch, nn, DataLoader, Dataset = _dependencies()
    from .model import UNetFaultNet

    if ensemble_size < 2:
        raise ValueError("ensemble_size must be at least 2")
    if patch_size < 32 or patch_size % 8 != 0:
        raise ValueError("patch_size must be >=32 and divisible by 8")
    if patches_per_epoch < 1 or batch_size < 1 or epochs < 1:
        raise ValueError("training lengths and batch size must be positive")
    if not 0.0 < unlabeled_loss_weight <= 1.0:
        raise ValueError("unlabeled_loss_weight must be in (0, 1]")

    x = np.load(feature_path, mmap_mode="r")
    y = np.load(label_path, mmap_mode="r")
    label_observed = np.asarray(np.load(label_observed_path, mmap_mode="r"), dtype=bool)
    footprint = np.asarray(np.load(footprint_path, mmap_mode="r"), dtype=bool)
    train_mask = np.asarray(training_mask, dtype=bool)
    if (x.ndim != 3 or y.shape != x.shape[1:] or footprint.shape != y.shape
            or label_observed.shape != y.shape or train_mask.shape != y.shape):
        raise ValueError("Prepared arrays must align: X=(bands,height,width), y/label_observed/footprint/train_mask=(height,width)")
    train_mask &= footprint
    positive_coords = np.argwhere((y > 0) & train_mask)
    eligible_flat = np.flatnonzero(train_mask)
    if not positive_coords.size:
        raise ValueError("No known positive fault pixels remain in the training mask")
    if not eligible_flat.size:
        raise ValueError("Training mask contains no eligible pixels")

    class PatchDataset(Dataset):
        def __init__(self, member_seed: int) -> None:
            self.member_seed = member_seed
            self.epoch = 0
            self.rng = np.random.default_rng(member_seed)

        def set_epoch(self, epoch: int) -> None:
            self.epoch = int(epoch)
            self.rng = np.random.default_rng(self.member_seed + 1009 * self.epoch)

        def __len__(self) -> int:
            return patches_per_epoch

        def __getitem__(self, _: int):
            if self.rng.random() < 0.5:
                cy, cx = positive_coords[self.rng.integers(0, len(positive_coords))]
            else:
                flat = eligible_flat[self.rng.integers(0, len(eligible_flat))]
                cy, cx = np.unravel_index(flat, y.shape)
            half = patch_size // 2
            y0 = min(max(int(cy) - half, 0), y.shape[0] - patch_size)
            x0 = min(max(int(cx) - half, 0), y.shape[1] - patch_size)
            y1, x1 = y0 + patch_size, x0 + patch_size
            patch_x = np.asarray(x[:, y0:y1, x0:x1], dtype=np.float32).copy()
            patch_y = np.asarray(y[y0:y1, x0:x1], dtype=np.float32).copy()
            eligible = train_mask[y0:y1, x0:x1]
            observed = label_observed[y0:y1, x0:x1]
            weights = np.where(patch_y > 0, 1.0, unlabeled_loss_weight).astype(np.float32)
            weights *= (eligible & observed).astype(np.float32)
            return (
                torch.from_numpy(patch_x),
                torch.from_numpy(patch_y[None, :, :]),
                torch.from_numpy(weights[None, :, :]),
            )

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device_obj = torch.device(device)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for member_index in range(ensemble_size):
        seed = int(seed_base + member_index)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True

        # New model and optimizer for every member: no shared weights or optimizer state.
        model = UNetFaultNet(in_channels=int(x.shape[0])).to(device_obj)
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
        loss_fn = nn.BCEWithLogitsLoss(reduction="none")
        dataset = PatchDataset(seed)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
        epoch_losses = []
        model.train()
        for epoch in range(epochs):
            dataset.set_epoch(epoch)
            weighted_loss_sum = 0.0
            weight_sum = 0.0
            for xb, yb, wb in loader:
                xb, yb, wb = xb.to(device_obj), yb.to(device_obj), wb.to(device_obj)
                optimizer.zero_grad(set_to_none=True)
                logits = model(xb)
                per_pixel = loss_fn(logits, yb)
                denom = wb.sum().clamp_min(1.0)
                loss = (per_pixel * wb).sum() / denom
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                optimizer.step()
                weighted_loss_sum += float((per_pixel.detach() * wb).sum().item())
                weight_sum += float(wb.sum().item())
            epoch_losses.append(weighted_loss_sum / max(weight_sum, 1.0))

        checkpoint = out / f"member-{member_index:02d}-seed-{seed}.pt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "seed": seed,
                "member_index": member_index,
                "ensemble_size": ensemble_size,
                "in_channels": int(x.shape[0]),
                "architecture": "UNetFaultNet-v1",
                "epochs": epochs,
                "patch_size": patch_size,
                "epoch_weighted_bce": epoch_losses,
                "training_label_semantics": "catalogue positives; unlabeled background downweighted",
                "dropout_at_inference": False,
            },
            checkpoint,
        )
        reports.append(
            {
                "member_index": member_index,
                "seed": seed,
                "checkpoint": str(checkpoint),
                "last_epoch_weighted_bce": epoch_losses[-1],
            }
        )
        del model, optimizer, loader, dataset
        if device_obj.type == "cuda":
            torch.cuda.empty_cache()

    report_path = out / "ensemble-training.json"
    report_path.write_text(
        json.dumps(
            {
                "ensemble_size": ensemble_size,
                "seed_base": seed_base,
                "members": reports,
                "training_contract": "Independent initialization and complete optimization per member; deterministic inference; no test-time dropout.",
                "warning": "Training loss is not a holdout score or evidence of hidden-fault performance.",
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return reports
