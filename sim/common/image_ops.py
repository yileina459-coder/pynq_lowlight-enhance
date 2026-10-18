#!/usr/bin/env python3
"""Shared software models of the hardware operators.

Every model here is written to match the corresponding HLS kernel **bit for
bit**: same integer luma weights, same border policy, same saturation. That is
the only way a board capture can be compared with a 0-tolerance check.

Border policy (identical for every 3x3 operator)
    horizontal : replicate at the left edge, window columns are
                 (max(c-2,0), max(c-1,0), c); the output beat at column c
                 therefore corresponds to input column c-1
    vertical   : "wrap" takes the three rows as (r-2, r-1, r) modulo the frame,
                 which is what the kernels' line buffers actually hold after the
                 first frame of a continuous stream; "replicate" clamps at the
                 top/bottom edge, which is the right model for a single still
                 image compared against a synthesised reference

Keeping both policies here (rather than one per script) is what lets the Sobel,
Gaussian and future operators share one comparison tool.
"""

from __future__ import annotations

import numpy as np


def luma(rgb: np.ndarray) -> np.ndarray:
    """BT.601-ish integer luma, identical to sobel_luma() in the HLS source."""
    r = rgb[:, :, 0].astype(np.uint32)
    g = rgb[:, :, 1].astype(np.uint32)
    b = rgb[:, :, 2].astype(np.uint32)
    return ((77 * r + 150 * g + 29 * b) >> 8).astype(np.uint8)


def _window(plane: np.ndarray, border: str) -> tuple[np.ndarray, ...]:
    """Return the nine (H,W) neighbours of a 2-D plane, as the kernels see them.

    Index order matches the kernels: [2] = left (c-2), [1] = centre (c-1),
    [0] = right (c).
    """
    h = plane.shape[0]
    if border == "wrap":
        rows = [np.mod(np.arange(h) + dy, h) for dy in (-2, -1, 0)]
    elif border == "replicate":
        rows = [np.clip(np.arange(h) + dy, 0, h - 1) for dy in (-2, -1, 0)]
    else:
        raise ValueError(f"unknown border policy: {border}")

    w = plane.shape[1]
    c0 = np.clip(np.arange(w) - 2, 0, None)
    c1 = np.clip(np.arange(w) - 1, 0, None)
    c2 = np.arange(w)

    top, mid, bot = plane[rows[0], :], plane[rows[1], :], plane[rows[2], :]
    return (top[:, c0], top[:, c1], top[:, c2],
            mid[:, c0], mid[:, c1], mid[:, c2],
            bot[:, c0], bot[:, c1], bot[:, c2])


def sobel(y: np.ndarray, border: str = "replicate") -> np.ndarray:
    """3x3 Sobel on a luma plane: |Gx| + |Gy|, saturated to 0..255."""
    y32 = y.astype(np.int32)
    t0, t1, t2, m0, m1, m2, b0, b1, b2 = _window(y32, border)
    gx = (t2 + 2 * m2 + b2) - (t0 + 2 * m0 + b0)
    gy = (b0 + 2 * b1 + b2) - (t0 + 2 * t1 + t2)
    return np.clip(np.abs(gx) + np.abs(gy), 0, 255).astype(np.uint8)


def gaussian(rgb: np.ndarray, border: str = "replicate") -> np.ndarray:
    """3x3 1-2-1 Gaussian blur, per channel, normalised by 16."""
    out = np.empty_like(rgb)
    for ch in range(3):
        plane = rgb[:, :, ch].astype(np.int32)
        t0, t1, t2, m0, m1, m2, b0, b1, b2 = _window(plane, border)
        acc = (t0 + 2 * t1 + t2
               + 2 * m0 + 4 * m1 + 2 * m2
               + b0 + 2 * b1 + b2)
        out[:, :, ch] = (acc >> 4).astype(np.uint8)
    return out


def to_rgb(plane: np.ndarray) -> np.ndarray:
    """Replicate a single-channel result to R, G and B."""
    return np.dstack([plane, plane, plane])


def make_test_image(width: int = 1280, height: int = 720) -> np.ndarray:
    """Deterministic edge-rich test pattern: ramps, a hard block, a fine checker,
    concentric rings. Shared by every operator so results are comparable."""
    yy, xx = np.mgrid[0:height, 0:width]

    r = (xx * 3 + yy) % 256
    g = (yy * 5) % 256
    b = (xx ^ yy) % 256
    img = np.dstack([r, g, b]).astype(np.uint8)

    img[120:400, 200:640] = 235

    checker = (((xx >> 2) + (yy >> 2)) & 1).astype(bool)
    region = np.zeros((height, width), dtype=bool)
    region[440:660, 700:1180] = True
    img[region & checker] = 20
    img[region & ~checker] = 220

    cx, cy = 320, 560
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    rings = ((dist / 12.0).astype(np.int32) & 1).astype(np.uint8) * 200 + 30
    img[380:740, 80:560] = np.dstack([rings, rings, rings])[380:740, 80:560]

    return img
