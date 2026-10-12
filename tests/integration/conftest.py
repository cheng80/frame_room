import json

import pytest

LUNA_CATALOG = {"models": [{"slug": "gpt-6-luna", "visibility": "list", "input_modalities": ["text", "image"],
                            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}]}]}


def pytest_configure(config):
    config.addinivalue_line("markers", "codex_command: test drives codex_observe itself with a fake subprocess.run")


@pytest.fixture(autouse=True)
def _offline_frame_observer(monkeypatch, tmp_path_factory, request):
    """Tests never read the developer's Codex catalog and never start a real (paid) observer call:
    the catalog is a fixture listing gpt-6-luna, a synthetic Codex CLI is "on PATH" whether or not
    the developer installed one, and codex_observe fails unless a test replaces it."""
    import shutil
    from adapters.spritegen import frame_selection as fs
    which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: "/synthetic/bin/codex" if name == "codex" else which(name, *a, **k))
    catalog = tmp_path_factory.getbasetemp() / "codex-models-cache.json"
    if not catalog.exists():
        catalog.write_text(json.dumps(LUNA_CATALOG))
    monkeypatch.setattr(fs, "catalog_path", lambda: catalog)
    if not request.node.get_closest_marker("codex_command"):
        monkeypatch.setattr(fs, "codex_observe", lambda *a, **k: pytest.fail("real observer call blocked in tests"))
