"""The local video-only backport preserves the existing fork's cyan matte."""
from PIL import Image, ImageDraw
from sprite_gen.video import frames


def test_decontamination_cannot_add_top_edge_contact_but_keeps_interior_recovery(tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    image = Image.new('RGB', (64, 80), (255, 0, 255))
    ImageDraw.Draw(image).rectangle((20, 10, 42, 69), fill=(90, 80, 110))
    image.save(source)
    original_cutout = frames.cutout
    def fake_recovered_edge(src, dst, **kwargs):
        result = original_cutout(src, dst, **kwargs)
        assert result['decontam']['applied']
        with Image.open(dst) as current:
            current = current.convert('RGBA')
        # Synthetic decontamination leak on the top band and a recovered pixel
        # outside that band. This is an edge policy fixture, not AI output.
        current.putpixel((32, 1), (90, 80, 110, 80))
        current.putpixel((32, 6), (90, 80, 110, 80))
        current.save(dst)
        return result
    monkeypatch.setattr(frames, 'cutout', fake_recovered_edge)
    report = frames.key_frames([source], tmp_path / 'keyed', key='magenta', decontam='palette')
    with Image.open(tmp_path / 'keyed' / source.name) as final:
        assert final.getpixel((32, 1))[3] == 0
        assert final.getpixel((32, 6))[3] == 80
        assert final.getpixel((32, 40))[3] == 255
    assert report['decontam']['edge_band'] == frames.EDGE_ROWS
    assert report['edge_contacts'] == []
