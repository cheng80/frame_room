# SPDX-License-Identifier: Apache-2.0
"""The v2.34 edge guard lives inside decontamination; exercise the real pass.
Synthetic decoded-looking pixels, never generated artwork.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from sprite_gen.video import frames as frames_mod

GREEN_PAINTED = (18, 232, 26)

def _composite_on(F, A, key):
    C = F * A[..., None] + np.asarray(key, np.float64) * (1 - A[..., None])
    return np.clip(np.round(C), 0, 255).astype(np.uint8)


def _subsample_420(rgb: np.ndarray) -> np.ndarray:
    """Decode-like 4:2:0: full-resolution luma, chroma averaged over 2x2 blocks (BT.601)."""
    x = rgb.astype(np.float64)
    y = x @ np.array([0.299, 0.587, 0.114])
    cb = (x[..., 2] - y) * 0.564
    cr = (x[..., 0] - y) * 0.713
    h, w = y.shape
    for c in (cb, cr):
        blk = c[: h // 2 * 2, : w // 2 * 2].reshape(h // 2, 2, w // 2, 2).mean((1, 3))
        c[: h // 2 * 2, : w // 2 * 2] = np.repeat(np.repeat(blk, 2, 0), 2, 1)
    r = y + cr / 0.713
    b = y + cb / 0.564
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    return np.clip(np.round(np.stack([r, g, b], -1)), 0, 255).astype(np.uint8)


def _head_under_the_top_edge(t: int) -> np.ndarray:
    """A decoded frame of a dark head whose matte edge sits 6 px under the top of the frame.

    Above it the head's blur runs on into the key as a decoded clip shows it: coverage
    0.3, 0.15, 0.08, 0.03 on rows 5 to 2, which the hard cut keys, and rows 0 to 1 are key.
    """
    F = np.zeros((96, 96, 3))
    A = np.zeros((96, 96))
    F[6:90, 30 + t:66 + t] = (60, 62, 66)
    F[40:70, 40 + t:56 + t] = (150, 148, 152)  # a lighter patch, so the palette has two colours
    A[6:90, 30 + t:66 + t] = 1.0
    for row, coverage in ((5, 0.3), (4, 0.15), (3, 0.08), (2, 0.03)):
        F[row, 30 + t:66 + t] = (60, 62, 66)
        A[row, 30 + t:66 + t] = coverage
    return _subsample_420(_composite_on(F, A, GREEN_PAINTED))


def test_video_frames_keep_the_frame_edge_as_the_matte_left_it(tmp_path: Path):
    """A clip that passes the edge gate with decontam off passes it with decontam on.

    Each blur row above the head fits a faint blend. Rows 3 to 5 lie within the flank,
    and row 3 inside the gate's edge band too: recovering it put the subject's grey on
    the frame edge, and the gate read it as the key surviving the matte.
    """
    raws = []
    for t in range(2):
        path = tmp_path / f"frame-{t + 1:04d}.png"
        Image.fromarray(_head_under_the_top_edge(t)).save(path)
        raws.append(path)
    off = frames_mod.key_frames(raws, tmp_path / "plain", key="green", spill="full")
    on = frames_mod.key_frames(raws, tmp_path / "keyed", key="green", spill="full", decontam="palette")
    assert off["edge_contacts"] == on["edge_contacts"] == []
    assert on["decontam"]["applied_frames"] == 2 and on["decontam"]["edge_band"] == frames_mod.EDGE_ROWS
    band = np.zeros((96, 96), dtype=bool)
    band[:frames_mod.EDGE_ROWS] = band[:, :frames_mod.EDGE_ROWS] = band[:, -frames_mod.EDGE_ROWS:] = True
    for raw in raws:
        plain = np.array(Image.open(tmp_path / "plain" / raw.name))[..., 3]
        keyed = np.array(Image.open(tmp_path / "keyed" / raw.name))[..., 3]
        assert not keyed[band & (plain == 0)].any()
        # below the edge band the flank still gives the blur rows their coverage back
        assert keyed[4:6][plain[4:6] == 0].any()
    assert on["decontam"]["totals"]["recovered_px"] > 0

