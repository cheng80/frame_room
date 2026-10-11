from pathlib import Path
import sys
from types import ModuleType

import pytest

from adapters.spritegen import provider, video_processing
from alignment import pipeline


def test_adapters_import_project_engine():
    for module in (provider._engine(), video_processing._engine("video.loop")):
        assert Path(module.__file__).resolve().is_relative_to(pipeline.ENGINE_ROOT.resolve())


def test_adapters_preserve_engine_errors_when_engine_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "ENGINE_ROOT", tmp_path)

    with pytest.raises(provider.ProviderError) as provider_error:
        provider._engine()
    assert provider_error.value.code == "provider.engine_mismatch"

    with pytest.raises(video_processing.VideoProcessingError) as video_error:
        video_processing._engine("video.loop")
    assert video_error.value.code == "VIDEO_ENGINE_UNAVAILABLE"


def test_adapters_reject_external_sprite_gen_submodule(monkeypatch, tmp_path):
    external = ModuleType("sprite_gen.external_guard_fixture")
    external.__file__ = str(tmp_path / "sprite_gen" / "external_guard_fixture.py")
    monkeypatch.setitem(sys.modules, external.__name__, external)

    with pytest.raises(provider.ProviderError) as provider_error:
        provider._engine()
    assert provider_error.value.code == "provider.engine_mismatch"

    with pytest.raises(video_processing.VideoProcessingError) as video_error:
        video_processing._engine("video.loop")
    assert video_error.value.code == "VIDEO_ENGINE_MISMATCH"
