from __future__ import annotations

import csv
import json
import math
import random
import re
import time
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset


SEED = 42
INPUT_SHAPE = (96, 96, 96)
MAX_RUNTIME_SECONDS = 12 * 60 * 60
SAVE_DIR = Path("/kaggle/working/neuroage_3d_resnet18")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class IXIVolumes(Dataset):
    def __init__(self, records: list[dict[str, Any]], augment: bool = False) -> None:
        self.records = records
        self.augment = augment

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        record = self.records[index]
        image = nib.as_closest_canonical(nib.load(str(record["path"])))
        volume = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32)
        if volume.ndim == 4:
            volume = volume[..., 0]
        if volume.ndim != 3 or volume.size == 0 or not np.isfinite(volume).all():
            raise ValueError(f"Invalid MRI volume for subject {record['subject_id']}")

        foreground = volume[np.isfinite(volume) & (volume != 0)]
        if foreground.size:
            low, high = np.percentile(foreground, (0.5, 99.5))
            volume = np.clip(volume, low, high)
            mean = float(foreground.mean())
            std = float(foreground.std())
            if std > 1e-6:
                volume = (volume - mean) / std
            else:
                volume = volume - mean
        volume = np.nan_to_num(volume, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        tensor = torch.from_numpy(np.ascontiguousarray(volume)).float()[None, None]
        tensor = F.interpolate(
            tensor, size=INPUT_SHAPE, mode="trilinear", align_corners=False
        )[0]

        if self.augment and random.random() < 0.5:
            tensor = torch.flip(tensor, dims=(1,))
        if self.augment and random.random() < 0.5:
            tensor = torch.flip(tensor, dims=(2,))
        return tensor, torch.tensor(record["age"], dtype=torch.float32)


class BasicBlock3D(nn.Module):
    expansion = 1

    def __init__(self, in_channels: int, channels: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv3d(
            in_channels, channels, kernel_size=3, stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm3d(channels)
        self.conv2 = nn.Conv3d(
            channels, channels, kernel_size=3, stride=1, padding=1, bias=False
        )
        self.bn2 = nn.BatchNorm3d(channels)
        self.shortcut = (
            nn.Sequential(
                nn.Conv3d(in_channels, channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm3d(channels),
            )
            if stride != 1 or in_channels != channels
            else nn.Identity()
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(value)
        value = F.relu(self.bn1(self.conv1(value)), inplace=True)
        value = self.bn2(self.conv2(value))
        return F.relu(value + residual, inplace=True)


class ResNet3D18(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.in_channels = 32
        self.stem = nn.Sequential(
            nn.Conv3d(1, 32, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm3d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=3, stride=2, padding=1),
        )
        self.layer1 = self._make_layer(32, blocks=2, stride=1)
        self.layer2 = self._make_layer(64, blocks=2, stride=2)
        self.layer3 = self._make_layer(128, blocks=2, stride=2)
        self.layer4 = self._make_layer(256, blocks=2, stride=2)
        self.pool = nn.AdaptiveAvgPool3d(1)
        self.regressor = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=0.2),
            nn.Linear(256, 1),
        )

    def _make_layer(self, channels: int, blocks: int, stride: int) -> nn.Sequential:
        layers = [BasicBlock3D(self.in_channels, channels, stride)]
        self.in_channels = channels
        layers.extend(BasicBlock3D(channels, channels) for _ in range(blocks - 1))
        return nn.Sequential(*layers)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        value = self.stem(value)
        value = self.layer1(value)
        value = self.layer2(value)
        value = self.layer3(value)
        value = self.layer4(value)
        return self.regressor(self.pool(value)).squeeze(-1)


def discover_records(input_root: Path) -> list[dict[str, Any]]:
    if not input_root.exists():
        raise FileNotFoundError(f"Kaggle input mount not found at {input_root}")

    manifest_candidates = list(input_root.rglob("subjects.csv"))
    if not manifest_candidates:
        available = sorted(path.name for path in input_root.iterdir())
        raise FileNotFoundError(
            f"subjects.csv not found under {input_root}; mounted datasets: {available}"
        )
    manifest = next(
        (
            path
            for path in manifest_candidates
            if "subject_id" in path.read_text(encoding="utf-8-sig")[:512]
        ),
        manifest_candidates[0],
    )

    image_by_subject: dict[str, Path] = {}
    for image_path in input_root.rglob("*mni_registered_T1w.nii*"):
        if "segmask" in image_path.name.lower():
            continue
        match = re.search(r"sub-(IXI\d+)", image_path.name, re.IGNORECASE)
        if match:
            image_by_subject.setdefault(match.group(1).upper(), image_path)

    records: list[dict[str, Any]] = []
    with manifest.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            subject_id = str(row.get("subject_id", "")).strip().upper()
            try:
                age = float(row.get("age", ""))
            except (TypeError, ValueError):
                continue
            image_path = image_by_subject.get(subject_id)
            if (
                image_path is None
                or not subject_id.startswith("IXI")
                or not math.isfinite(age)
                or not 0 < age < 120
            ):
                continue
            records.append({"subject_id": subject_id, "age": age, "path": image_path})

    unique_records = {record["subject_id"]: record for record in records}
    records = [unique_records[key] for key in sorted(unique_records)]
    if len(records) < 30:
        raise ValueError(
            f"Only {len(records)} labeled registered T1 scans were matched; "
            "at least 30 are required to create subject-level train/validation/test splits."
        )
    return records


def split_records(
    records: list[dict[str, Any]], seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    shuffled = records.copy()
    random.Random(seed).shuffle(shuffled)
    train_end = int(len(shuffled) * 0.70)
    validation_end = int(len(shuffled) * 0.85)
    return shuffled[:train_end], shuffled[train_end:validation_end], shuffled[validation_end:]


def calculate_metrics(
    predictions: list[float], actual: list[float]
) -> dict[str, float | int | None]:
    predicted = np.asarray(predictions, dtype=np.float64)
    labels = np.asarray(actual, dtype=np.float64)
    if labels.size == 0:
        return {"mae": None, "rmse": None, "pearson_r": None, "n_samples": 0}
    residual = predicted - labels
    correlation = (
        float(np.corrcoef(predicted, labels)[0, 1])
        if labels.size > 1 and np.std(predicted) > 1e-8 and np.std(labels) > 1e-8
        else None
    )
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(np.square(residual)))),
        "pearson_r": correlation,
        "n_samples": int(labels.size),
    }


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    amp_enabled: bool,
) -> tuple[float, dict[str, float | int | None]]:
    model.eval()
    predictions: list[float] = []
    actual: list[float] = []
    total_loss = 0.0
    sample_count = 0
    with torch.inference_mode():
        for volumes, ages in loader:
            volumes = volumes.to(device, non_blocking=True)
            ages = ages.to(device, non_blocking=True)
            with torch.autocast(
                device_type="cuda", dtype=torch.float16, enabled=amp_enabled
            ):
                output = model(volumes)
                loss = F.huber_loss(output.float(), ages, delta=2.0)
            predictions.extend(output.float().cpu().tolist())
            actual.extend(ages.cpu().tolist())
            total_loss += float(loss.item()) * ages.size(0)
            sample_count += ages.size(0)
    return total_loss / max(sample_count, 1), calculate_metrics(predictions, actual)


def main() -> None:
    seed_everything(SEED)
    started_at = time.monotonic()
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    records = discover_records(Path("/kaggle/input"))
    train_records, validation_records, test_records = split_records(records, SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Kaggle GPU is required; this job must not fall back to CPU.")
    device_count = torch.cuda.device_count()
    print(
        json.dumps(
            {
                "device": torch.cuda.get_device_name(0),
                "gpu_count": device_count,
                "subjects": len(records),
                "train": len(train_records),
                "validation": len(validation_records),
                "test": len(test_records),
                "input_shape": INPUT_SHAPE,
            }
        ),
        flush=True,
    )

    batch_size = 4 if device_count < 2 else 8
    train_loader = DataLoader(
        IXIVolumes(train_records, augment=True),
        batch_size=batch_size,
        shuffle=True,
        num_workers=2,
        pin_memory=True,
        drop_last=True,
    )
    validation_loader = DataLoader(
        IXIVolumes(validation_records),
        batch_size=batch_size,
        shuffle=False,
        num_workers=2,
        pin_memory=True,
    )
    test_loader = DataLoader(
        IXIVolumes(test_records),
        batch_size=batch_size,
        shuffle=False,
        num_workers=2,
        pin_memory=True,
    )

    base_model = ResNet3D18().to(device)
    model: nn.Module = (
        nn.DataParallel(base_model) if device_count > 1 else base_model
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=3e-4, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=8, min_lr=1e-6
    )
    amp_enabled = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    history: list[dict[str, Any]] = []
    best_validation_mae = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    epoch = 0
    deadline = started_at + MAX_RUNTIME_SECONDS
    reserve_seconds = 5 * 60

    while time.monotonic() < deadline - reserve_seconds:
        epoch += 1
        model.train()
        running_loss = 0.0
        sample_count = 0
        for volumes, ages in train_loader:
            if time.monotonic() >= deadline - reserve_seconds:
                break
            volumes = volumes.to(device, non_blocking=True)
            ages = ages.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(
                device_type="cuda", dtype=torch.float16, enabled=amp_enabled
            ):
                predictions = model(volumes)
                loss = F.huber_loss(predictions.float(), ages, delta=2.0)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()
            running_loss += float(loss.item()) * ages.size(0)
            sample_count += ages.size(0)

        if sample_count == 0:
            break
        validation_loss, validation_metrics = evaluate(
            model, validation_loader, device, amp_enabled
        )
        scheduler.step(validation_loss)
        epoch_record = {
            "epoch": epoch,
            "train_huber_loss": running_loss / sample_count,
            "validation_huber_loss": validation_loss,
            "validation": validation_metrics,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "elapsed_seconds": int(time.monotonic() - started_at),
        }
        history.append(epoch_record)
        print(json.dumps(epoch_record), flush=True)

        validation_mae = validation_metrics["mae"]
        if validation_mae is not None and validation_mae < best_validation_mae:
            best_validation_mae = validation_mae
            selected = model.module if isinstance(model, nn.DataParallel) else model
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in selected.state_dict().items()
            }
            torch.save(
                {
                    "architecture": "NeuroAge-ResNet3D-18",
                    "model_state_dict": best_state,
                    "input_shape": INPUT_SHAPE,
                    "preprocessing": {
                        "orientation": "RAS",
                        "foreground_percentiles": [0.5, 99.5],
                        "normalization": "foreground z-score",
                        "interpolation": "trilinear",
                    },
                    "best_validation_mae": best_validation_mae,
                    "epoch": epoch,
                    "seed": SEED,
                },
                SAVE_DIR / "best_model.pth",
            )
            (SAVE_DIR / "training_history.json").write_text(
                json.dumps(history, indent=2), encoding="utf-8"
            )

    if best_state is None:
        raise RuntimeError("Training ended without a valid validation checkpoint.")

    selected = model.module if isinstance(model, nn.DataParallel) else model
    selected.load_state_dict(best_state)
    test_loss, test_metrics = evaluate(
        selected, test_loader, device, amp_enabled
    )
    summary = {
        "model": "NeuroAge-ResNet3D-18",
        "dataset": "kingpowa/preprocessed-ixi-dataset-with-fs8",
        "license_reported_by_kaggle": "Apache-2.0",
        "input_shape": INPUT_SHAPE,
        "preprocessing": {
            "orientation": "RAS",
            "foreground_percentiles": [0.5, 99.5],
            "normalization": "foreground z-score",
            "interpolation": "trilinear",
        },
        "seed": SEED,
        "split": {
            "train": len(train_records),
            "validation": len(validation_records),
            "test": len(test_records),
        },
        "best_validation_mae": best_validation_mae,
        "test_huber_loss": test_loss,
        "test_metrics": test_metrics,
        "epochs_completed": epoch,
        "elapsed_seconds": int(time.monotonic() - started_at),
        "training_history": history,
        "limitations": [
            "This is an exploratory research model, not a clinical diagnostic tool.",
            "A single IXI cohort does not establish cross-site or external generalization.",
            "Metrics must be reviewed before any inference or clinical interpretation.",
        ],
    }
    (SAVE_DIR / "evaluation_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    torch.save(
        {
            "architecture": "NeuroAge-ResNet3D-18",
            "model_state_dict": best_state,
            "input_shape": INPUT_SHAPE,
            "preprocessing": summary.get("preprocessing"),
            "evaluation": test_metrics,
        },
        SAVE_DIR / "final_model.pth",
    )
    print(json.dumps({"training_complete": True, **summary}), flush=True)


if __name__ == "__main__":
    main()
