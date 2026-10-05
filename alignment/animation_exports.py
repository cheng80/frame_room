"""Additional delivery formats from canonical, already-baked RGBA cells.

Never renders, changes project state, fits a pose, or infers timing from FPS.
GIF is explicitly lossy. PNG and decoded WebP must retain the canonical pixels.
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import re
import struct
import unicodedata

import numpy as np
from PIL import GifImagePlugin, Image, features

EXPORT_VERSION = "canonical-animation-v1"
MAX_SHEET_PIXELS = 64_000_000


class AnimationExportError(Exception):
    """Encoded data failed its round-trip verification; publish nothing."""


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _slug(value):
    value = unicodedata.normalize("NFKC", str(value))
    safe = re.sub(r"[^\w-]+", "-", value).strip("-_")
    return safe.encode("utf-8")[:48].decode("utf-8", errors="ignore") or "clip"


def _rgba(image):
    pixels = np.array(image.convert("RGBA"))
    pixels[pixels[..., 3] == 0, :3] = 0
    return Image.fromarray(pixels)


def _encoded(image, format, **options):
    stream = io.BytesIO()
    image.save(stream, format=format, **options)
    return stream.getvalue()


def _omitted(code, message, **details):
    return {"status": "omitted", "reason": {"code": code, "message": message, **details}}


def _sheet(images, columns):
    width, height = images[0].size
    rows = math.ceil(len(images) / columns)
    size = (columns * width, rows * height)
    if size[0] * size[1] > MAX_SHEET_PIXELS:
        return None, _omitted("SHEET_TOO_LARGE", "PNG 시트가 64MP 제한을 넘습니다. 순서별 PNG를 사용하세요.", width=size[0], height=size[1])
    sheet = Image.new("RGBA", size)
    for i, image in enumerate(images):
        sheet.paste(image, (i % columns * width, i // columns * height))
    data = _encoded(sheet, "PNG")
    with Image.open(io.BytesIO(data)) as decoded:
        for i, image in enumerate(images):
            x, y = i % columns * width, i // columns * height
            if decoded.crop((x, y, x + width, y + height)).tobytes() != image.tobytes():
                raise AnimationExportError("PNG 시트의 프레임 픽셀이 bake와 다릅니다.")
    return data, {"columns": columns, "rows": rows, "width": size[0], "height": size[1], "fullRGBAParity": True}


def _gif_frame(image):
    # 255 visible colors and one transparent index. No spatial dithering.
    rgb = Image.new("RGBA", image.size, (0, 0, 0, 255))
    rgb.alpha_composite(image)
    visible = np.asarray(image)[..., 3] > 128
    colors, inverse = np.unique(np.asarray(rgb.convert("RGB"))[visible], axis=0, return_inverse=True)
    if len(colors) <= 255:
        # Do not spend a color on transparent black. A finished 255-color,
        # binary-alpha PNG must survive GIF export without another quantization.
        indices = np.full(visible.shape, 255, dtype=np.uint8)
        indices[visible] = inverse
        paletted = Image.fromarray(indices).convert("P")
        palette = colors.flatten().tolist()
        paletted.putpalette(palette + [0] * (768 - len(palette)))
        paletted.info["transparency"] = 255
        return paletted
    paletted = rgb.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = paletted.getpalette() or []
    paletted.putpalette((palette + [0] * 768)[:768])
    paletted.paste(255, mask=image.getchannel("A").point(lambda alpha: 255 if alpha <= 128 else 0))
    paletted.info["transparency"] = 255
    return paletted


def _verify_animation(data, images, durations, loop, format):
    """Compare time intervals, allowing a codec to merge identical neighbors."""
    expected = []
    boundary = 0
    for image, duration in zip(images, durations):
        pixels = image.convert("RGBA") if format == "WEBP" else _rgba(image)
        expected.append((boundary, boundary + duration, pixels.tobytes()))
        boundary += duration
    decoded_durations, mappings = [], []
    cursor = source_index = 0
    with Image.open(io.BytesIO(data)) as decoded:
        expected_loop = (0 if loop else 1) if format == "WEBP" else (0 if loop else None)
        if decoded.info.get("loop") != expected_loop or decoded.size != images[0].size:
            raise AnimationExportError(f"{format} 반복 또는 캔버스 정보가 다릅니다.")
        for i in range(decoded.n_frames):
            decoded.seek(i)
            decoded.load()  # WebP duration is populated when the frame is loaded.
            duration = decoded.info.get("duration", 0)
            if not isinstance(duration, int) or duration <= 0:
                raise AnimationExportError(f"{format} 프레임 시간이 유효하지 않습니다.")
            pixels = (decoded.convert("RGBA") if format == "WEBP" else _rgba(decoded)).tobytes()
            end = cursor + duration
            covered = []
            j = source_index
            while j < len(expected) and expected[j][0] < end:
                start_ms, end_ms, wanted = expected[j]
                if end_ms > cursor:
                    if wanted != pixels:
                        raise AnimationExportError(f"{format} 프레임 픽셀 또는 순서가 다릅니다.")
                    covered.append(j)
                if end_ms <= end:
                    source_index = j + 1
                j += 1
            if not covered or end > boundary:
                raise AnimationExportError(f"{format} 재생 시간이 원래 동작과 다릅니다.")
            decoded_durations.append(duration)
            mappings.append(covered)
            cursor = end
    if cursor != boundary or source_index != len(expected):
        raise AnimationExportError(f"{format} 전체 재생 시간이 다릅니다.")
    return {"decodedFrameCount": len(decoded_durations), "decodedDurationsMs": decoded_durations,
            "decodedSourceIndices": mappings, "durationMs": cursor, "loop": loop, "verified": True}


def _gif(images, durations, loop):
    too_short = [i for i, duration in enumerate(durations) if duration < 10]
    if too_short:
        return None, _omitted("GIF_TIMING_UNREPRESENTABLE", "10ms 미만 프레임은 GIF로 표현할 수 없어 제외했습니다. PNG/runtime 또는 WebP를 사용하세요.", occurrenceIndices=too_short)
    # Round boundaries, not each frame, so fractional centiseconds do not drift.
    boundary = rounded_boundary = 0
    encoded_durations = []
    for duration in durations:
        boundary += duration
        next_boundary = ((boundary + 5) // 10) * 10
        encoded_durations.append(next_boundary - rounded_boundary)
        rounded_boundary = next_boundary
    paletted = [_gif_frame(image) for image in images]
    info = {"transparency": 255, "background": 255, "optimize": False}
    if loop:
        info["loop"] = 0
    # Explicit frame writes preserve duplicate slots and their durations. Pillow's
    # default multi-frame writer may merge them past GIF's 16-bit delay limit.
    header, _ = GifImagePlugin.getheader(paletted[0], info=info)
    parts = list(header)
    for frame, duration in zip(paletted, encoded_durations):
        parts.extend(GifImagePlugin.getdata(frame, duration=duration, disposal=2,
                     transparency=255, include_color_table=True))
    data = b"".join(parts) + b";"
    expected = [_rgba(image) for image in paletted]
    verification = _verify_animation(data, expected, encoded_durations, loop, "GIF")
    changed = [int(np.count_nonzero(np.any(np.asarray(original) != np.asarray(converted), axis=2)))
               for original, converted in zip(images, expected)]
    return data, {**verification, "lossy": True, "pixelLossDetected": any(changed),
                  "changedPixelsPerOccurrence": changed, "maxOpaqueColors": 255,
                  "alphaThreshold": 128, "transparentWhen": "alpha<=128", "alphaMode": "binary",
                  "palette": "exact-if-255-colors-else-per-frame-mediancut", "dither": "none", "alphaCompositeBackground": "black",
                  "timingRounding": "integer-centisecond-boundary-half-up",
                  "sourceDurationsMs": durations, "encodedDurationsMs": encoded_durations,
                  "timingLossy": durations != encoded_durations,
                  "totalDurationErrorMs": sum(encoded_durations) - sum(durations),
                  "playCount": 0 if loop else 1,
                  "note": "GIF는 최대 255색·이진 알파·10ms 단위를 사용합니다. 실제 재생기는 짧은 지연을 늘릴 수 있습니다."}


def _webp_lossless_frame(image):
    """Use the still encoder: Pillow's animation encoder drops ``exact``."""
    static = _encoded(image, "WEBP", lossless=True, exact=True, quality=100, method=4)
    if (static[:4] != b"RIFF" or static[8:12] != b"WEBP"
            or int.from_bytes(static[4:8], "little") != len(static) - 8):
        raise AnimationExportError("무손실 WebP 단일 프레임의 헤더가 유효하지 않습니다.")
    chunks, offset = [], 12
    while offset < len(static):
        if offset + 8 > len(static):
            raise AnimationExportError("무손실 WebP 단일 프레임의 청크가 잘렸습니다.")
        size = int.from_bytes(static[offset + 4:offset + 8], "little")
        end = offset + 8 + size + size % 2
        if end > len(static):
            raise AnimationExportError("무손실 WebP 단일 프레임의 청크가 잘렸습니다.")
        if static[offset:offset + 4] == b"VP8L":
            chunks.append(static[offset:end])
        offset = end
    if len(chunks) != 1:
        raise AnimationExportError("무손실 WebP 단일 프레임을 읽지 못했습니다.")
    return chunks[0]


def _webp_animation(images, durations, loop):
    """Mux exact full-canvas VP8L frames, including single and duplicate slots.

    Avoid both hidden-RGB loss and the still-image collapse in ``save_all``.
    No frame blending, delta rectangles, or timing inference is involved.
    https://developers.google.com/speed/webp/docs/riff_container
    """

    def chunk(kind, payload):
        return kind + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2)

    def uint24(value):
        return value.to_bytes(3, "little")

    width, height = images[0].size
    flags = 0x02 | (0x10 if any(image.getextrema()[3][0] < 255 for image in images) else 0)
    header = bytes([flags, 0, 0, 0]) + uint24(width - 1) + uint24(height - 1)
    parts = [b"WEBP", chunk(b"VP8X", header), chunk(b"ANIM", b"\0" * 4 + struct.pack("<H", 0 if loop else 1))]
    # Keep every source slot. This also bounds each 24-bit duration, even when
    # the total constant animation is longer than an ANMF duration can represent.
    for image, duration in zip(images, durations):
        # 0x02 replaces the entire canvas (including hidden RGB); do not blend.
        frame = uint24(0) + uint24(0) + uint24(width - 1) + uint24(height - 1) + uint24(duration) + b"\x02"
        parts.append(chunk(b"ANMF", frame + _webp_lossless_frame(image)))
    body = b"".join(parts)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _webp(images, durations, loop):
    if not features.check("webp"):
        return None, _omitted("WEBP_UNAVAILABLE", "이 Pillow 설치에 WebP 코덱이 없어 제외했습니다. PNG/runtime을 사용하세요.")
    if max(images[0].size) > 16383:
        return None, _omitted("WEBP_DIMENSION_LIMIT", "WebP 최대 프레임 크기를 넘습니다. PNG/runtime을 사용하세요.")
    data = _webp_animation(images, durations, loop)
    verification = _verify_animation(data, images, durations, loop, "WEBP")
    return data, {**verification, "lossy": False, "fullRGBAParity": True, "timingLossy": False,
                  "sourceDurationsMs": durations, "playCount": 0 if loop else 1,
                  "note": "투명 픽셀의 RGB와 중복 프레임의 시간까지 보존합니다. 슬롯·앵커·정확한 시간은 runtime.json이 기준입니다."}


def _padded_cells(cells):
    if not cells or any(image.width <= 0 or image.height <= 0 for image in cells):
        raise ValueError("At least one nonempty canonical cell is required")
    width, height = max(image.width for image in cells), max(image.height for image in cells)
    images = []
    for image in cells:
        image = image.convert("RGBA")
        if image.size == (width, height):
            images.append(image)
        else:
            padded = Image.new("RGBA", (width, height))
            padded.paste(image, (0, 0))
            images.append(padded)
    return images


def _format_results(images, durations, loop):
    for key, filename, make in (
        ("stripPng", "strip.png", lambda: _sheet(images, len(images))),
        ("gridPng", "grid.png", lambda: _sheet(images, math.ceil(math.sqrt(len(images))))),
        ("gif", "animation.gif", lambda: _gif(images, durations, loop)),
        ("webp", "animation.webp", lambda: _webp(images, durations, loop)),
    ):
        data, metadata = make()
        yield key, filename, data, metadata


def write_animation_formats(cells: list[Image.Image], durations: list[int], loop: bool, out_dir: Path) -> dict:
    """Write verified strip.png/grid.png/animation.gif/animation.webp.

    Input cells must already be the final render. No finishing, resampling or
    project changes occur here. Returns {files: [relative filenames], formats:
    {stripPng, gridPng, gif, webp}, warnings, cell, frameCount}. An unsupported
    optional format has status=omitted and a reason; it is absent from files.
    GIF preserves <=255 visible colors exactly when alpha is already binary.
    Caller publishes this private output directory after the function succeeds.
    """
    if len(cells) != len(durations) or any(type(d) is not int or not 1 <= d <= 60000 for d in durations):
        raise ValueError("Each cell needs an integer durationMs between 1 and 60000")
    if not isinstance(loop, bool):
        raise ValueError("loop must be boolean")
    images = _padded_cells(cells)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"version": EXPORT_VERSION, "files": [], "formats": {}, "warnings": [],
              "frameCount": len(images), "cell": {"width": images[0].width, "height": images[0].height}}
    for key, filename, data, metadata in _format_results(images, durations, loop):
        if data is None:
            result["formats"][key] = metadata
            result["warnings"].append({"format": key, **metadata["reason"]})
        else:
            with (out_dir / filename).open("xb") as target:
                target.write(data)
            result["files"].append(filename)
            result["formats"][key] = {"status": "created", "file": filename, "sha256": _hash(data), **metadata}
    return result


def build_animation_exports(runtime_clips, png_data, *, export_id, recipe_hash, project_revision):
    """Return a JSON-compatible manifest and safe relative ZIP entries."""
    manifest = {"schemaVersion": 1, "version": EXPORT_VERSION, "exportId": export_id,
                "recipeHash": recipe_hash, "projectRevision": project_revision,
                "source": "canonical-bake-cells", "runtime": "runtime.json",
                "placement": "top-left; no scaling; transparent padding for differing cell sizes",
                "clips": [], "warnings": []}
    entries = []
    for ci, clip in enumerate(runtime_clips):
        cells = []
        for slot in clip["occurrences"]:
            with Image.open(io.BytesIO(png_data[slot["renderedFrameId"]])) as image:
                cells.append(image.convert("RGBA"))
        images = _padded_cells(cells)
        width, height = images[0].size
        clip_id = str(clip["id"])
        prefix = f"clips/{ci:03d}-{_slug(clip_id)}-{_hash(clip_id.encode())[:10]}-{_slug(clip.get('name', ''))}"
        durations = [slot["durationMs"] for slot in clip["occurrences"]]
        columns = math.ceil(math.sqrt(len(images)))
        record = {key: clip.get(key) for key in ("id", "clipId", "clipRevisionId", "name", "loop", "endBehavior", "durationMs")}
        record.update(frameCount=len(images), cell={"width": width, "height": height}, occurrences=[], formats={})
        for i, (slot, cell) in enumerate(zip(clip["occurrences"], cells)):
            record["occurrences"].append({**slot, "index": i,
                "sourceCell": {"width": cell.width, "height": cell.height},
                "stripRect": {"x": i * width, "y": 0, "width": width, "height": height},
                "gridRect": {"x": i % columns * width, "y": i // columns * height, "width": width, "height": height}})
        for key, filename, data, metadata in _format_results(images, durations, clip["loop"]):
            if data is None:
                record["formats"][key] = metadata
                manifest["warnings"].append({"clipId": clip_id, "format": key, **metadata["reason"]})
            else:
                name = f"{prefix}/{filename}"
                entries.append((name, data))
                record["formats"][key] = {"status": "created", "file": name, "sha256": _hash(data), **metadata}
        manifest["clips"].append(record)
    return manifest, entries
