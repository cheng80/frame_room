# SPDX-License-Identifier: Apache-2.0
"""Registration must not make feet overflow the final cell during placement."""

import pytest
from PIL import Image, ImageDraw

from sprite_gen.frames.extract import conform_registered_row, place_row_frame, row_placement


def _registered_pair(width: int, height: int) -> list[Image.Image]:
    frames = []
    for right_contact in (False, True):
        frame = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(frame)
        # Identical upper body; alternating contact reaches opposite canvas edges.
        draw.rectangle((width // 3, 0, width * 2 // 3, height // 2), fill="blue")
        left, right = (width // 2, width - 1) if right_contact else (0, width // 2)
        draw.rectangle((left, height // 2 + 1, right, height - 1), fill="red")
        frames.append(frame)
    return frames


@pytest.mark.parametrize("size,scale", [((65, 102), 1), ((40, 123), 1), ((33, 62), 2)])
def test_common_cap_preserves_registration_and_avoids_placement_loss(size, scale):
    frames = conform_registered_row(_registered_pair(*size), 64 // scale, 122 // scale)
    assert len({frame.size for frame in frames}) == 1
    width, height = frames[0].size
    assert width * scale <= 64 and height * scale <= 122
    # Re-cropping each pose would shift the common torso coordinates.
    assert frames[0].crop((0, 0, width, height // 3)).tobytes() == frames[1].crop((0, 0, width, height // 3)).tobytes()
    left, top = row_placement(frames, 64, 128, 6, scale, {})
    for frame in frames:
        placed = place_row_frame(frame, 64, 128, scale, left, top, 6)
        assert placed.getbbox()[3] == 122
        # Every post-resample opaque pixel must survive final compositing.
        assert sum(placed.getchannel("A").get_flattened_data()) == sum(frame.getchannel("A").get_flattened_data()) * scale ** 2
    assert frames[0].getbbox()[0] == 0
    assert frames[1].getbbox()[2] == width


def test_registered_row_that_fits_keeps_exact_pixels():
    frames = _registered_pair(60, 100)
    assert conform_registered_row(frames, 64, 122) is frames
