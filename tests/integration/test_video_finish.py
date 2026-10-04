"""Final sprite colors are persistent assets, never a display-only filter."""
import numpy as np
import pytest
from PIL import Image
from adapters.spritegen.video_finish import finish_frames
from services.api import store as s


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path)


@pytest.mark.parametrize('mode', ['gif', 'rgba'])
def test_finish_keeps_originals_and_records_reproducible_mode(tmp_path, mode):
    a = np.zeros((30, 19, 4), dtype=np.uint8)
    a[4:28, 2:17] = (151, 105, 65, 255)
    a[10, 3:8] = [(80, 160, 30, alpha) for alpha in (0, 20, 128, 129, 255)]
    source = tmp_path / 'input.png'
    Image.fromarray(a).save(source)
    original = source.read_bytes()
    paths, recipe = finish_frames([source], tmp_path / mode, mode=mode, cell_width=32, cell_height=48)
    result = np.asarray(Image.open(paths[0]))
    assert source.read_bytes() == original
    assert result.shape == a.shape and recipe['mode'] == mode
    assert (tmp_path / mode / 'finish.json').is_file()
    if mode == 'rgba':
        assert np.array_equal(result, a)
    else:
        assert set(np.unique(result[:, :, 3])) == {0, 255}
        assert result[10, 3:8, 3].tolist() == [0, 0, 0, 255, 255]
        assert len(np.unique(result[result[:, :, 3] > 0, :3], axis=0)) <= 255
        assert recipe['paletteSamplingScale'] == 3


def test_finish_does_not_crop_motion_that_overflows_cell(tmp_path):
    source = tmp_path / 'wide.png'
    im = Image.new('RGBA', (90, 150), (80, 60, 40, 255));im.save(source)
    paths, _ = finish_frames([source], tmp_path / 'out', mode='gif', cell_width=32, cell_height=48)
    result = Image.open(paths[0])
    assert result.size == (90, 150)
    assert result.getchannel('A').getextrema() == (255, 255)


def test_finish_rejects_unrecognized_mode(tmp_path):
    with pytest.raises(s.AppError, match='색상 마무리'):
        finish_frames([], tmp_path / 'out', mode='unknown', cell_width=64, cell_height=128)
