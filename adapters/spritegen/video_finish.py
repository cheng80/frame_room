"""Persist preview-equivalent colors as editable PNGs, keeping all inputs intact.

The accepted preview was quantized at 3x on a padded output cell. Both padding
and scale affect Pillow's adaptive palette; quantizing a cropped sprite alone
is not equivalent. This is an explicit output treatment, not semantic recolor.
"""
from pathlib import Path

from PIL import Image

from services.api import store as s
from .video_processing import _engine


def finish_frames(paths, directory, *, mode, cell_width, cell_height):
    if mode not in ('gif', 'rgba'):
        raise s.AppError('VIDEO_FINISH', '색상 마무리 설정을 확인하세요.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    recipe = dict(version='video-finish-v1', mode=mode, cellWidth=cell_width,
                  cellHeight=cell_height, preservesSource=True)
    if mode == 'gif':
        recipe.update(palette='adaptive-per-frame', maxColors=255, alphaThreshold=128,
                      paletteSamplingScale=3, rgbMatte='black', binaryAlpha=True,
                      placement='union-bottom-centre', footMargin=10)
    else:
        recipe.update(palette=None, binaryAlpha=False)
    results = []
    for source in paths:
        source = Path(source)
        with Image.open(source) as im:
            rgba = im.convert('RGBA')
        if mode == 'gif':
            # A too-small cell must never silently cut off a weapon or jump.
            # Extra bounds remain in the candidate for normal editor overflow QA.
            width = max(cell_width, rgba.width)
            height = max(cell_height, rgba.height + 10)
            if width * height * 9 > 36_000_000:
                raise s.AppError('VIDEO_FINISH_SIZE', '색상 마무리 영역이 너무 큽니다. 공통 몸 높이를 줄이세요.')
            x, y = (width - rgba.width) // 2, height - 10 - rgba.height
            cell = Image.new('RGBA', (width, height))
            cell.alpha_composite(rgba, (x, y))
            enlarged = cell.resize((width * 3, height * 3), Image.Resampling.NEAREST)
            paletted = _engine('util.gif_utils')._prepare_transparent_frame(enlarged, 128)
            finished = paletted.convert('RGBA').resize((width, height), Image.Resampling.NEAREST)
            rgba = finished.crop((x, y, x + rgba.width, y + rgba.height))
        target = directory / source.name
        rgba.save(target)
        results.append(target)
    s.atomic_bytes(directory / 'finish.json', s.dumps(recipe).encode())
    return results, recipe
