"""
RevEngine — PBR Map Generator
==============================
Generates normal and roughness maps from a diffuse (albedo) PIL Image.
No GPU, no external binaries — pure Pillow + numpy.

Usage:
    from decoders.pbr_maps import generate_normal_map, generate_roughness_map
    normal   = generate_normal_map(diffuse_img, strength=2.0)
    roughness = generate_roughness_map(diffuse_img)
"""

from __future__ import annotations
import numpy as np
from PIL import Image, ImageFilter


def generate_normal_map(diffuse: Image.Image, strength: float = 2.0) -> Image.Image:
    """
    Convert a diffuse image to a tangent-space normal map via Sobel gradients.

    Pipeline:
      diffuse → greyscale height field → Gaussian blur (denoise) →
      Sobel dX / dY → normalize to unit vector → encode as RGB

    Encoding: R=(Nx+1)/2, G=(Ny+1)/2, B=Nz  (DirectX convention, Y-up)
    Alpha channel set to 255.

    Parameters
    ----------
    diffuse  : PIL RGBA or RGB image (typically the upscaled game texture)
    strength : gradient multiplier — higher = more pronounced surface detail.
               Recommended range 1.0 – 4.0 for painted game textures.
    """
    grey = diffuse.convert("L")
    # Mild blur reduces noise in hand-painted textures before gradient
    grey = grey.filter(ImageFilter.GaussianBlur(radius=1))

    h = np.array(grey, dtype=np.float32) / 255.0   # height field [0..1]

    # Central-difference Sobel (pad edges by replication)
    dx = np.zeros_like(h)
    dy = np.zeros_like(h)
    dx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) * 0.5
    dx[:, 0]    = h[:, 1] - h[:, 0]
    dx[:, -1]   = h[:, -1] - h[:, -2]
    dy[1:-1, :] = (h[2:, :] - h[:-2, :]) * 0.5
    dy[0, :]    = h[1, :] - h[0, :]
    dy[-1, :]   = h[-1, :] - h[-2, :]

    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(h)

    # Normalize each pixel's (nx, ny, nz) to unit length
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    length = np.maximum(length, 1e-8)
    nx /= length
    ny /= length
    nz /= length

    # Encode [-1..1] → [0..255]
    r = ((nx + 1.0) * 0.5 * 255).astype(np.uint8)
    g = ((ny + 1.0) * 0.5 * 255).astype(np.uint8)
    b = (nz * 255).astype(np.uint8)
    a = np.full_like(r, 255)

    out = np.stack([r, g, b, a], axis=-1)
    return Image.fromarray(out, mode="RGBA")


def generate_roughness_map(
    diffuse: Image.Image,
    base: float = 0.75,
    range_: float = 0.25,
) -> Image.Image:
    """
    Estimate a roughness map from luminance of the diffuse image.

    Heuristic: bright highlights → lower roughness (shinier surface),
    dark areas (crevices, cloth) → higher roughness (matte surface).

    Output is a greyscale L image where 0 = smooth (mirror) and 255 = rough.
    Values are clamped to [base - range_, base + range_] to avoid extremes.

    Parameters
    ----------
    diffuse : PIL image
    base    : mid-point roughness (default 0.75 suits fantasy/armor)
    range_  : ± deviation from base driven by luminance (default 0.25)
    """
    lum = np.array(diffuse.convert("L"), dtype=np.float32) / 255.0

    # Invert: bright → smooth (low roughness), dark → rough (high roughness)
    inverted = 1.0 - lum

    # Map to [base - range_, base + range_]
    lo = max(0.0, base - range_)
    hi = min(1.0, base + range_)
    roughness = lo + inverted * (hi - lo)

    out = (roughness * 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")
