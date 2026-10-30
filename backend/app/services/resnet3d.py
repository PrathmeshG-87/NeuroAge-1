from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


ARCHITECTURE = 'NeuroAge-ResNet3D-18'
INPUT_SHAPE = (96, 96, 96)


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


class ResNet3D18Predictor:
    def __init__(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get('architecture') != ARCHITECTURE:
            raise ValueError(
                f'Expected {ARCHITECTURE} checkpoint, got {checkpoint.get("architecture")!r}.'
            )
        if tuple(checkpoint.get('input_shape', ())) != INPUT_SHAPE:
            raise ValueError(f'Checkpoint input shape must be {INPUT_SHAPE}.')

        self.model = ResNet3D18()
        self.model.load_state_dict(checkpoint['model_state_dict'], strict=True)
        self.model.eval()

    def predict(self, volume: np.ndarray) -> float:
        if volume.ndim == 4:
            volume = volume[..., 0]
        if volume.ndim != 3 or volume.size == 0 or not np.isfinite(volume).all():
            raise ValueError('MRI volume must be a finite, non-empty 3D array.')

        foreground = volume[volume != 0]
        volume = volume.astype(np.float32, copy=True)
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
            tensor, size=INPUT_SHAPE, mode='trilinear', align_corners=False
        )
        with torch.inference_mode():
            prediction = self.model(tensor).item()
        return float(prediction)
