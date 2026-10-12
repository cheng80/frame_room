"""Standalone scripts must durably save motions; synthetic fixtures, no generation."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from services.api import store as s, project_folders
from adapters.spritegen import video_provider as vp
from adapters.spritegen.video_processing import _write
from scripts.project_library import target_project, publish, publish_delivery
from adapters.spritegen.video_normalization import normalize_frames
from adapters.spritegen.video_finish import finish_frames


@pytest.fixture
def scene(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'data')
    s.init()
    project = s.create_project('시험 라이브러리', '시험 캐릭터')
    run = tmp_path / 'run'; (run / 'bases/E').mkdir(parents=True)
    base = run / 'bases/E/anchor.png'
    cell = Image.new('RGBA', (32, 48)); ImageDraw.Draw(cell).rectangle((12, 12, 20, 40), fill=(120, 80, 40, 255)); cell.save(base)
    video = run / 'synthetic.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', str(base), '-t', '1', '-r', '8', '-pix_fmt', 'yuv420p', str(video)], check=True)
    spec = dict(key='walk_E', name='걷기 · 동(E)', direction='E', facing='right', cells=[cell, cell.copy()],
        anchor={'x': 16, 'y': 40}, durations=[100, 900], indices=[0, 7], times=[i*125 for i in range(9)],
        loop=True, base=base, video=video, requestId='synthetic-test', processing={'take':'synthetic-retimed'})
    return project, run, spec


def test_publish_survives_reopen_and_retry_preserves_ids(scene):
    p, run, spec = scene; pid = p['projectId']
    assert target_project(run, pid) == target_project(run) == pid
    receipt = publish(pid, [spec], run/'saved.json')
    stored = s.get_project(pid)
    assert receipt['addedClips'] == 1 and receipt['folderVerified']
    assert len(stored['clips']) == 1 and len(stored['frames']) == 2
    assert [o['durationMs'] for o in stored['clips'][0]['occurrences']] == [100, 900]
    folder = s.project_folder(pid)
    _, disk = project_folders._read(folder)
    assert disk == stored
    assert disk['clips'][0]['libraryProcessing'] == spec['processing']
    for f in stored['frames']:
        assert Image.open(s.asset_path(f['imageAssetId'])).convert('RGBA').tobytes() == spec['cells'][0].tobytes()
    again = publish(pid, [spec], run/'saved.json')
    assert again['addedClips'] == 0 and again['clipIds'] == receipt['clipIds']
    assert s.get_project(pid) == stored
    # Moving the folder and opening the new location re-registers it without deletion.
    reopened = project_folders.open_project(str(folder.rename(folder.with_name(folder.name + '-moved'))))
    assert len(reopened['clips']) == 1 and reopened['revision'] == stored['revision']


def test_correction_appends_and_preserves_user_edit(scene):
    p, run, spec = scene; pid = p['projectId']
    publish(pid, [spec], run/'saved.json')
    with s.transaction() as db:
        before = s.get_project(pid, db)
        before['clips'][0]['occurrences'][0]['durationMs'] = 500
        s.write_project(db, before, '사용자 시간 편집')
    receipt = publish(pid, [spec], run/'saved.json')
    after = s.get_project(pid)
    assert receipt['addedClips'] == 1 and len(after['clips']) == 2
    assert after['clips'][0] == before['clips'][0]
    assert after['clips'][1]['occurrences'][0]['durationMs'] == 100


def test_failed_publication_has_no_success_receipt_and_no_partial_library(scene, monkeypatch):
    p, run, spec = scene
    original = s.write_project
    def fail(*args, **kwargs):
        raise s.AppError('INJECTED', '시험 저장 실패')
    monkeypatch.setattr(s, 'write_project', fail)
    with pytest.raises(s.AppError, match='시험 저장 실패'):
        publish(p['projectId'], [spec], run/'saved.json')
    assert not (run/'saved.json').exists()
    assert s.get_project(p['projectId']) == {k:v for k,v in p.items() if k != 'storage'}
    monkeypatch.setattr(s, 'write_project', original)
    assert publish(p['projectId'], [spec], run/'saved.json')['addedClips'] == 1


def test_missing_or_changed_target_and_bad_timing_fail_before_save(scene):
    p, run, spec = scene
    with pytest.raises(s.AppError) as error: target_project(run)
    assert error.value.code == 'LIBRARY_TARGET_REQUIRED'
    target_project(run, p['projectId'])
    with pytest.raises(s.AppError) as error: target_project(run, 'other-id')
    assert error.value.code == 'LIBRARY_TARGET_CONFLICT'
    with pytest.raises(s.AppError): publish(p['projectId'], [{**spec, 'durations': [0, 1000]}], run/'saved.json')
    assert not (run/'saved.json').exists() and not s.get_project(p['projectId'])['clips']


def test_provider_checkpoint_writer_does_not_change_application_data(scene):
    _, run, spec = scene; original_data = s.DATA
    checkpoint = run / 'checkpoint.json'
    _write(checkpoint, {'phase':'downloaded', 'postCount':1, 'requestHash':'fixture', 'requestId':'fixture',
                        'localPath':str(spec['video']), 'receipt':{'sha256':s.digest(spec['video'].read_bytes())}})
    result = vp.generate(spec['base'], run/'provider', {}, checkpoint, 'fixture', save_checkpoint=_write,
                         call=lambda *_: pytest.fail('Must not generate a new video'))
    assert result['path'] == spec['video'] and s.DATA == original_data
    assert json.loads(checkpoint.read_text())['postCount'] == 1


def test_standalone_processing_metadata_preserves_application_data(scene):
    _, run, spec = scene; original_data = s.DATA
    frames = [{'keyedPath': str(spec['base']), 'outputFrameIndex':0}]
    paths, recipe = normalize_frames(frames, 28, 28, run/'normalized', save_metadata=_write)
    finished, finish = finish_frames(paths, run/'finished', mode='gif', cell_width=64, cell_height=64, save_metadata=_write)
    assert s.DATA == original_data and Path(finished[0]).is_file()
    assert json.loads((run/'normalized/normalization.json').read_text()) == recipe
    assert json.loads((run/'finished/finish.json').read_text()) == finish


def test_delivery_uses_manifest_frame_timing_and_saves_to_bound_target(scene):
    p, run, spec = scene; target_project(run, p['projectId'])
    motion = run/'motions/walk_E'; motion.mkdir(parents=True)
    _write(motion/'generation.json', {'path':str(spec['video'])})
    record = {'name':'walk_E','direction':'E','state':'walk','baseSha256':s.digest(spec['base'].read_bytes()),
        'sourceSha256':s.digest(spec['video'].read_bytes()),'requestId':'synthetic-test',
        'frames':[{'durationMs':500,'sourceFrameIndex':i} for i in (0,7)],
        'source':{'timesMs':spec['times']},'selection':{'loop':True}}
    _write(motion/'complete.json',record)
    delivery=run/'delivery';delivery.mkdir()
    sheet=Image.new('RGBA',(64,48));sheet.paste(spec['cells'][0],(0,0));sheet.paste(spec['cells'][1],(32,0));sheet.save(delivery/'cleric-atlas.png')
    _write(delivery/'cleric-atlas.json',{'frames':{f'f{i}':{'frame':{'x':i*32,'y':0,'w':32,'h':48},'duration':d} for i,d in enumerate(spec['durations'])},'animations':{'walk_E':['f0','f1']}})
    clip={'frameNames':['f0','f1'],'durationsMs':spec['durations'],'durationMs':1000,'sourceFrameIndices':[0,7],'loop':True,
          'sourceVideoSha256':record['sourceSha256'],'baseImageSha256':record['baseSha256']}
    _write(delivery/'cleric-manifest.json',{'atlasSha256':s.digest((delivery/'cleric-atlas.png').read_bytes()),'anchor':{'x':.5,'y':40/48},'animations':{'walk_E':clip}})
    receipt=publish_delivery(run,delivery)
    assert receipt['addedClips']==1
    assert [o['durationMs'] for o in s.get_project(p['projectId'])['clips'][0]['occurrences']]==[100,900]


def test_script_entry_rejects_unbound_run_before_calling_provider(scene, monkeypatch):
    _, run, _ = scene
    path = s.ROOT/'scripts/cleric-eightway.py'
    module_spec = importlib.util.spec_from_file_location('cleric_test', path)
    module = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
    monkeypatch.setattr(module.vp, 'generate', lambda *_args, **_kwargs: pytest.fail('Unbound run must not generate'))
    with pytest.raises(s.AppError) as error: module.clip(run, 'E', 'walk')
    assert error.value.code == 'LIBRARY_TARGET_REQUIRED'
