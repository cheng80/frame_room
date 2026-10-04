"""Isolated process recovery audits; never call a network provider.

Only this test file contains the harness. It starts the real worker main loop,
SQLite store and task entrypoint in separate processes against SPRITE_DATA_DIR.
Faults are injected at process/publication boundaries, never into recovery logic.

All recovered invariants are ordinary passing regressions. Provider and
completed-result retries must reuse durable output without external calls.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
TERMINAL = {'succeeded', 'needs_review', 'failed', 'interrupted', 'provider_outcome_unknown', 'canceled'}


def _wait_for(check, *, timeout=12, label='condition'):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(f'timed out waiting for {label}')


def _running(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip()) and not result.stdout.lstrip().startswith('Z')


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _png():
    buffer = io.BytesIO()
    Image.new('RGBA', (12, 16), (25, 170, 110, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture(params=['default-project-directory', 'external-project-directory'])
def sandbox(tmp_path, monkeypatch, request):
    """No global .data, real provider auth, API listener, or permanent helper file."""
    from services.api import store as s
    from services.api import main as api
    data = tmp_path / 'isolated-data'
    monkeypatch.setenv('SPRITE_DATA_DIR', str(data))
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    monkeypatch.setattr(s, 'DATA', data)
    s.init()
    parent = tmp_path / 'user-owned projects' if request.param == 'external-project-directory' else None
    if parent: parent.mkdir()
    project = s.create_project('복구 회귀', '합성 캐릭터', parent_directory=str(parent) if parent else None)
    with s.project_scope(project['projectId']), s.transaction() as c:
        original = s.register_asset(_png(), 'owned-fixture.png', 'identity', c=c)
        project['assets'].append(original)
        rid = s.uid()
        project['references'].append(dict(referenceRevisionId=rid, identityAssetId=original['assetId'],
                                          styleAssetIds=[], poseAssetIds=[], approval='approved'))
        project['activeReferenceRevisionId'] = rid
        s.write_project(c, project, 'test fixture')
    processes = []
    files = []

    def start(mode='normal'):
        env = os.environ.copy()
        env.update(SPRITE_DATA_DIR=str(data), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                   SPRITE_RECOVERY_TEST_MODE=mode)
        log = (tmp_path / f'worker-{len(processes)}.log').open('wb')
        files.append(log)
        proc = subprocess.Popen([sys.executable, str(THIS_FILE), '--harness-worker'],
                                cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True)
        processes.append(proc)
        return proc

    def enqueue(operation='backup'):
        p = s.get_project(project['projectId'])
        request = {'savedRevision': p['revision']} if operation == 'backup' else {
            'operation': operation, 'inputRevision': p['revision'], 'assetIds': [],
            'params': {'providerId': 'codex', 'prompt': 'test-only fake', 'frameCount': 1}}
        return api.enqueue(p['projectId'], operation, request, s.uid(), p['revision'])

    def job(j):
        return s.get_job(j['jobId'])

    def terminal(j):
        return _wait_for(lambda: job(j) if job(j)['status'] in TERMINAL else None,
                         label=f"terminal job {j['jobId']}")

    state = SimpleNamespace(s=s, api=api, data=data, tmp=tmp_path, project=project,
                            original=original, start=start, enqueue=enqueue, job=job, terminal=terminal)
    try:
        yield state
    finally:
        # First stop owned workers, then every recorded task group, including
        # orphan descendants whose group leader has already exited.
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(proc.pid)
                proc.wait(timeout=3)
        with s.connect() as c:
            jobs = [json.loads(r[0]) for r in c.execute('SELECT body FROM jobs')]
        for j in jobs:
            if j.get('childPid'):
                _kill_group(j['childPid'])
        for f in files:
            f.close()


def _call_count(data):
    path = data / 'test-provider-calls.jsonl'
    return len(path.read_text().splitlines()) if path.exists() else 0


def _wait_entered(sandbox):
    return _wait_for(lambda: json.loads((sandbox.data / 'test-provider-entered.json').read_text())
                     if (sandbox.data / 'test-provider-entered.json').exists() else None,
                     label='fake provider entry')


def test_real_worker_backup_preserves_source_and_publishes_once(sandbox):
    s = sandbox.s
    original = s.asset_path(sandbox.original['assetId'])
    original_bytes = original.read_bytes()
    j = sandbox.enqueue()
    proc = sandbox.start()
    done = sandbox.terminal(j)
    assert done['status'] == 'succeeded'
    assert len(done['artifacts']) == 1
    artifact = done['artifacts'][0]
    with s.connect() as c:
        row = c.execute('SELECT * FROM artifacts WHERE id=?', (artifact['artifactId'],)).fetchone()
        events = [r[0] for r in c.execute('SELECT seq FROM events WHERE job_id=? ORDER BY seq', (j['jobId'],))]
    assert hashlib.sha256(s.resolve_work_path(j['jobId'], row['path']).read_bytes()).hexdigest() == artifact['sha256']
    assert original.read_bytes() == original_bytes
    folder = s.project_folder(j['projectId'])
    assert original.is_relative_to(folder / 'assets')
    assert s.job_directory(j['jobId']) == folder / 'jobs' / j['jobId']
    assert s.artifact_directory(j['jobId']) == folder / 'outputs' / j['jobId']
    assert s.resolve_work_path(j['jobId'], row['path']).is_relative_to(folder / 'outputs')
    assert not (s.DATA / 'jobs' / j['jobId']).exists()
    assert not (s.DATA / 'artifacts' / j['jobId']).exists()
    assert events == list(range(1, done['eventSeq'] + 1))
    proc.terminate(); proc.wait(timeout=5)
    sandbox.start()
    _wait_for(lambda: sandbox.job(j)['status'] == 'succeeded', label='preserved completion')
    assert sandbox.job(j)['artifacts'] == done['artifacts']
    assert _call_count(sandbox.data) == 0


def test_sigkill_restart_marks_inflight_generation_unknown_without_resubmission(sandbox):
    j = sandbox.enqueue('generate')
    proc = sandbox.start('wait-provider')
    entered = _wait_entered(sandbox)
    _wait_for(lambda: sandbox.job(j).get('childPid'), label='recorded child pid')
    proc.kill(); proc.wait(timeout=3)
    sandbox.start()
    recovered = sandbox.terminal(j)
    assert recovered['status'] == 'provider_outcome_unknown'
    _wait_for(lambda: not _running(entered['pid']), label='terminated old child')
    assert _call_count(sandbox.data) == 1
    with pytest.raises(sandbox.s.AppError) as error:
        sandbox.api.retry(j['jobId'], sandbox.api.Retry(idempotencyKey='retry-unknown'))
    assert error.value.status == 409
    assert sandbox.s.get_project(j['projectId'])['generations'] == []


def test_cancel_stubborn_process_group_kills_all_members_and_never_retries(sandbox):
    j = sandbox.enqueue('generate')
    sandbox.start('stubborn-provider')
    entered = _wait_entered(sandbox)
    _wait_for(lambda: sandbox.job(j).get('childPid'), label='recorded child pid')
    sandbox.api.cancel(j['jobId'], sandbox.api.Cancel(expectedStatus='running'))
    canceled = sandbox.terminal(j)
    assert canceled['status'] == 'provider_outcome_unknown'
    _wait_for(lambda: not _running(entered['pid']) and not _running(entered['descendantPid']),
              label='entire canceled process group exited')
    assert _call_count(sandbox.data) == 1


def test_restart_must_reap_sigterm_resistant_group_before_releasing_job(sandbox):
    j = sandbox.enqueue('generate')
    proc = sandbox.start('stubborn-provider')
    entered = _wait_entered(sandbox)
    _wait_for(lambda: sandbox.job(j).get('childPid'), label='recorded child pid')
    proc.kill(); proc.wait(timeout=3)
    sandbox.start()
    assert sandbox.terminal(j)['status'] == 'provider_outcome_unknown'
    _wait_for(lambda: not _running(entered['pid']) and not _running(entered['descendantPid']),
              timeout=6, label='recovery reaped previous process group')
    assert _call_count(sandbox.data) == 1


def test_cancel_must_kill_descendants_even_if_group_leader_exits_first(sandbox):
    j = sandbox.enqueue('generate')
    sandbox.start('orphan-descendant')
    entered = _wait_entered(sandbox)
    _wait_for(lambda: sandbox.job(j).get('childPid'), label='recorded child pid')
    sandbox.api.cancel(j['jobId'], sandbox.api.Cancel(expectedStatus='running'))
    assert sandbox.terminal(j)['status'] == 'provider_outcome_unknown'
    _wait_for(lambda: not _running(entered['descendantPid']), timeout=5,
              label='descendant terminated after task leader exit')


@pytest.mark.parametrize('operation', ['backup', 'generate'])
@pytest.mark.parametrize('mode', ['hold-before-publish', 'hold-after-rename'])
def test_restart_reconciles_completed_result_without_reexecuting(sandbox, operation, mode):
    j = sandbox.enqueue(operation)
    proc = sandbox.start(mode)
    marker = sandbox.data / 'test-publication-boundary.json'
    _wait_for(marker.exists, label=mode)
    boundary = json.loads(marker.read_text())
    work = sandbox.s.job_directory(j['jobId']) / j['attemptId']
    assert json.loads((work / 'result.json').read_text())['ok'] is True
    assert Path(boundary['path']).is_dir()
    proc.kill(); proc.wait(timeout=3)
    sandbox.start()
    done = sandbox.terminal(j)
    assert done['status'] == ('needs_review' if operation == 'generate' else 'succeeded'), done
    if operation == 'generate':
        assert len(sandbox.s.get_project(j['projectId'])['generations']) == 1
        assert _call_count(sandbox.data) == 1
    else:
        assert len(done['artifacts']) == 1
        assert _call_count(sandbox.data) == 0


def test_post_provider_local_failure_retains_success_receipt(sandbox):
    j = sandbox.enqueue('generate')
    sandbox.start('post-provider-error')
    done = sandbox.terminal(j)
    assert _call_count(sandbox.data) == 1
    # A local persistence failure is not a failed remote generation. Keep the
    # known success receipt so only local publication needs recovery.
    assert done.get('result', {}).get('receipt', {}).get('testOnly') is True, done
    # Retry is publication-only: use the recorded provider result, never invoke
    # generate again. A fresh task process must load the durable checkpoint.
    retried = sandbox.api.retry(j['jobId'], sandbox.api.Retry(
        failedStep='publication', reuseCheckpoint=True, idempotencyKey='local-publication-only'))
    assert retried['attemptId'] != done['attemptId']
    completed = sandbox.terminal(j)
    assert completed['status'] == 'needs_review', completed
    assert _call_count(sandbox.data) == 1
    assert len(sandbox.s.get_project(j['projectId'])['generations']) == 1


def _retry_via_http(sandbox, j, key):
    from fastapi.testclient import TestClient
    with TestClient(sandbox.api.app) as client:
        token = client.get('/v1/health').json()['sessionToken']
        response = client.post(f"/v1/jobs/{j['jobId']}/retry", headers={'X-Session-Token': token}, json={
            'failedStep': 'publication', 'reuseCheckpoint': True, 'idempotencyKey': key})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.mark.parametrize('tamper', [False, True], ids=['reuse-confirmed-pixels', 'reject-changed-pixels'])
def test_provider_checkpoint_retry_never_calls_provider_again(sandbox, tamper):
    j = sandbox.enqueue('generate')
    sandbox.start('post-provider-error')
    failed = sandbox.terminal(j)
    assert failed['status'] == 'failed' and failed['providerCheckpoint'] is True
    previous = sandbox.s.job_directory(j['jobId']) / failed['attemptId']
    checkpoint_bytes = (previous / 'provider-completed.json').read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    old_image = Path(checkpoint['providerResult']['paths'][0])
    confirmed_bytes = old_image.read_bytes()
    assert checkpoint['providerResult']['receipt']['sha256'] == hashlib.sha256(confirmed_bytes).hexdigest()
    assert _call_count(sandbox.data) == 1
    if tamper:
        old_image.write_bytes(confirmed_bytes + b'changed-after-confirmation')
    retried = _retry_via_http(sandbox, j, 'reuse-provider-checkpoint')
    assert retried['attemptId'] != failed['attemptId']
    assert retried['reuseProviderAttemptId'] == failed['attemptId']
    assert not retried.get('reuseResultAttemptId')
    done = sandbox.terminal(j)
    assert _call_count(sandbox.data) == 1
    assert (previous / 'provider-completed.json').read_bytes() == checkpoint_bytes
    if tamper:
        assert done['status'] == 'failed'
        assert done['errors'][0]['code'] == 'CHECKPOINT_HASH', done
        assert sandbox.s.get_project(j['projectId'])['generations'] == []
        return
    assert done['status'] == 'needs_review', done
    current = sandbox.s.job_directory(j['jobId']) / done['attemptId']
    reused = json.loads((current / 'provider-completed.json').read_text())
    assert reused['requestHash'] == checkpoint['requestHash']
    assert reused['providerResult']['receipt'] == checkpoint['providerResult']['receipt']
    copied = Path(reused['providerResult']['paths'][0])
    assert copied.parent == current / 'staging' and copied != old_image
    # Publication moved staging atomically; compare the published copy and the
    # untouched previous attempt, not a stale absolute staging path.
    published = sandbox.s.artifact_directory(j['jobId']) / done['attemptId'] / copied.name
    assert published.read_bytes() == old_image.read_bytes() == confirmed_bytes
    p = sandbox.s.get_project(j['projectId'])
    assert len(p['generations']) == 1 and len(p['assets']) == 2
    assert p['generations'][0]['receipt'] == checkpoint['providerResult']['receipt']
    repeated = _retry_via_http(sandbox, j, 'reuse-provider-checkpoint')
    assert repeated['attemptId'] == done['attemptId']
    assert _call_count(sandbox.data) == 1


@pytest.mark.parametrize('mode', ['fail-before-publish-once', 'fail-after-rename-once'])
def test_completed_result_retry_republishes_without_task_execution_or_provider_call(sandbox, mode):
    j = sandbox.enqueue('generate')
    sandbox.start(mode)
    failed = sandbox.terminal(j)
    assert failed['status'] == 'failed' and failed['errors'][0]['code'] == 'PUBLICATION_FAILED'
    previous = sandbox.s.job_directory(j['jobId']) / failed['attemptId']
    payload_bytes = (previous / 'result.json').read_bytes()
    payload = json.loads(payload_bytes)
    assert payload['ok'] is True and payload['result']['receipt']['testOnly'] is True
    old_directory = previous / 'staging' if mode == 'fail-before-publish-once' else (
        sandbox.s.artifact_directory(j['jobId']) / failed['attemptId'])
    old_image = old_directory / 'fake-generated.png'
    raw = old_image.read_bytes()
    assert sandbox.s.get_project(j['projectId'])['generations'] == []
    retried = _retry_via_http(sandbox, j, 'reuse-completed-result')
    assert retried['attemptId'] != failed['attemptId']
    assert retried['reuseResultAttemptId'] == failed['attemptId']
    done = sandbox.terminal(j)
    assert done['status'] == 'needs_review', done
    assert _call_count(sandbox.data) == 1
    # task.main's result-reuse path must bypass execute(), not merely happen to
    # use another generate() implementation which also returns cached pixels.
    executions = (sandbox.data / 'test-task-executions.jsonl').read_text().splitlines()
    assert len(executions) == 1
    assert json.loads(executions[0])['attemptId'] == failed['attemptId']
    published = sandbox.s.artifact_directory(j['jobId']) / done['attemptId']
    assert (published / 'fake-generated.png').read_bytes() == old_image.read_bytes() == raw
    assert (previous / 'result.json').read_bytes() == payload_bytes
    p = sandbox.s.get_project(j['projectId'])
    assert len(p['generations']) == 1 and len(p['assets']) == 2
    assert p['generations'][0] == payload['result']['generations'][0]
    assert done['result']['receipt'] == payload['result']['receipt']
    repeated = _retry_via_http(sandbox, j, 'reuse-completed-result')
    assert repeated['attemptId'] == done['attemptId'] and _call_count(sandbox.data) == 1


@pytest.mark.parametrize('stored_form', ['legacy-absolute', 'relative'])
def test_generation_checkpoint_uses_project_copy_of_old_path(sandbox, monkeypatch, stored_form):
    """The preserved legacy bytes are not an alternate live job directory."""
    from services.worker.task import execute
    from adapters.spritegen import provider
    s = sandbox.s
    j = s.get_job(sandbox.enqueue('generate')['jobId'])
    out = s.job_directory(j['jobId']) / j['attemptId'] / 'staging'
    relative = Path('jobs') / j['jobId'] / j['attemptId'] / 'staging' / 'confirmed.png'
    legacy = s.DATA / relative
    image = out / 'confirmed.png'
    original = _png()
    s.atomic_bytes(legacy, original)
    s.atomic_bytes(image, original)
    saved_path = str(legacy) if stored_form == 'legacy-absolute' else relative.as_posix()
    result = {'paths': [saved_path], 'requestSnapshot': {'testOnly': True},
              'providerId': 'codex', 'model': 'test-only',
              'receipt': {'testOnly': True, 'sha256': s.digest(original)}}
    checkpoint = out.parent / 'provider-completed.json'
    s.atomic_bytes(checkpoint, s.dumps({'requestHash': j['requestHash'], 'providerResult': result}).encode())
    unchanged = checkpoint.read_bytes()
    monkeypatch.setattr(provider, 'generate', lambda *a, **k: pytest.fail('Checkpoint recovery must not generate'))
    assert s.resolve_work_path(j['jobId'], saved_path) == image
    recovered = execute(j, out)
    assert s.asset_path(recovered['assets'][0]['assetId']).read_bytes() == original
    assert s.asset_path(recovered['assets'][0]['assetId']).is_relative_to(s.project_folder(j['projectId']) / 'assets')
    assert checkpoint.read_bytes() == unchanged and legacy.read_bytes() == image.read_bytes() == original



def test_unpublished_completed_result_keeps_resource_records_in_project_folder(sandbox, monkeypatch):
    """A failed publication must survive copying only the project folder."""
    from services.worker.task import execute
    from adapters.spritegen import provider
    s = sandbox.s
    j = s.get_job(sandbox.enqueue('generate')['jobId'])
    out = s.job_directory(j['jobId']) / j['attemptId'] / 'staging'
    def fake_generate(params, reference, asset_path, out_dir):
        image = out_dir / 'synthetic-generated.png'
        s.atomic_bytes(image, _png())
        return {'paths': [str(image)], 'requestSnapshot': {'testOnly': True},
                'providerId': 'codex', 'model': 'test-only',
                'receipt': {'testOnly': True, 'sha256': s.digest(_png())}}
    monkeypatch.setattr(provider, 'generate', fake_generate)
    result = execute(j, out)
    result['publicationHashes'] = {}
    s.atomic_bytes(out.parent / 'result.json', s.dumps({'ok': True, 'result': result}).encode())
    with s.transaction() as c:
        current = s.get_job(j['jobId'], c)
        current.update(status='failed', errors=[{'code': 'PUBLICATION_FAILED', 'message': 'Synthetic local failure'}])
        s.write_job(c, current)
    folder = s.project_folder(j['projectId'])
    generated = result['assets'][0]
    assert generated['assetId'] not in {a['assetId'] for a in s.get_project(j['projectId'])['assets']}
    with sqlite3.connect((folder / 'project.sqlite3').as_uri() + '?mode=ro', uri=True) as portable:
        record = portable.execute('SELECT path,metadata FROM assets WHERE id=?', (generated['assetId'],)).fetchone()
    assert record is not None, 'Completed checkpoint resource metadata must be portable before publication'
    assert (folder / record[0]).read_bytes() == _png()
    assert json.loads(record[1]) == generated


def test_generation_checkpoint_cannot_read_other_project(sandbox, monkeypatch):
    from services.worker.task import execute
    from adapters.spritegen import provider
    s = sandbox.s
    j = s.get_job(sandbox.enqueue('generate')['jobId'])
    other = s.create_project('다른 프로젝트', '합성 캐릭터')
    with s.project_scope(other['projectId']):
        asset = s.register_asset(_png(), 'foreign.png')
    foreign = s.asset_path(asset['assetId'])
    out = s.job_directory(j['jobId']) / j['attemptId'] / 'staging'
    result = {'paths': [str(foreign)], 'requestSnapshot': {}, 'providerId': 'codex',
              'model': 'test-only', 'receipt': {'sha256': s.digest(foreign.read_bytes())}}
    s.atomic_bytes(out.parent / 'provider-completed.json',
                   s.dumps({'requestHash': j['requestHash'], 'providerResult': result}).encode())
    monkeypatch.setattr(provider, 'generate', lambda *a, **k: pytest.fail('Invalid checkpoint must not generate'))
    with pytest.raises(s.AppError): execute(j, out)
    assert foreign.read_bytes() == _png()



def _other_project_backup(sandbox):
    s=sandbox.s
    project=s.create_project('계속 처리할 프로젝트','합성 캐릭터')
    return sandbox.api.enqueue(project['projectId'],'backup',{'savedRevision':project['revision']},s.uid(),project['revision'])


def _assert_missing_folder_isolated(sandbox, affected, healthy, process, original_folder, moved_folder):
    s=sandbox.s
    assert sandbox.terminal(healthy)['status']=='succeeded'
    for job in affected:
        stopped=sandbox.job(job)
        assert stopped['status']=='interrupted',stopped
        assert stopped['errors'][0]['code'].startswith('PROJECT_FOLDER_')
    assert process.poll() is None and not original_folder.exists()
    with s.connect() as c:
        assert c.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(affected[0]['projectId'],)).fetchone()
    moved_folder.rename(original_folder)
    from services.api import project_folders
    project_folders.flush([affected[0]['projectId']])
    with sqlite3.connect(original_folder/'project.sqlite3') as portable:
        for job in affected:
            assert portable.execute('SELECT status FROM jobs WHERE id=?',(job['jobId'],)).fetchone()[0]=='interrupted'
    with s.connect() as c:
        assert not c.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(affected[0]['projectId'],)).fetchone()
    assert sandbox.terminal(_other_project_backup(sandbox))['status']=='succeeded'


@pytest.mark.parametrize('initial_status',['queued','running','cancel_requested'])
def test_missing_project_folder_does_not_stop_recovery_or_queue(sandbox, initial_status):
    s=sandbox.s
    first=sandbox.enqueue()
    second=sandbox.enqueue('generate')
    if initial_status!='queued':
        with s.transaction() as c:
            current=s.get_job(first['jobId'],c);current['status']=initial_status;s.write_job(c,current)
    healthy=_other_project_backup(sandbox)
    folder=s.project_folder(first['projectId']);moved=sandbox.tmp/'temporarily-unavailable'
    folder.rename(moved)
    proc=sandbox.start()
    _assert_missing_folder_isolated(sandbox,[first,second],healthy,proc,folder,moved)
    assert not sandbox.job(second).get('externalStarted')
    assert _call_count(sandbox.data)==0


def test_missing_folder_during_execution_reaps_child_and_preserves_retry_guard(sandbox):
    s=sandbox.s
    first=sandbox.enqueue('generate')
    second=sandbox.enqueue()
    healthy=_other_project_backup(sandbox)
    proc=sandbox.start('stubborn-provider')
    entered=_wait_entered(sandbox)
    _wait_for(lambda:sandbox.job(first).get('childPid'),label='recorded child')
    folder=s.project_folder(first['projectId']);moved=sandbox.tmp/'unavailable-during-execution'
    folder.rename(moved)
    _assert_missing_folder_isolated(sandbox,[first,second],healthy,proc,folder,moved)
    _wait_for(lambda:not _running(entered['pid']) and not _running(entered['descendantPid']),label='missing-folder children reaped')
    assert sandbox.job(first)['externalStarted'] is True
    with pytest.raises(s.AppError) as error:
        sandbox.api.retry(first['jobId'],sandbox.api.Retry(idempotencyKey='no-paid-replay'))
    assert error.value.code=='PROVIDER_RETRY_BLOCKED'
    assert _call_count(sandbox.data)==1  # Synthetic provider only; no network.


@pytest.mark.parametrize('boundary',['claim','spawn','publish'])
def test_folder_loss_during_worker_flush_does_not_terminate_loop(sandbox,boundary):
    s=sandbox.s
    first=sandbox.enqueue();second=sandbox.enqueue()
    healthy=_other_project_backup(sandbox)
    folder=s.project_folder(first['projectId']);moved=sandbox.data/'test-offline-project'
    proc=sandbox.start('lose-folder-'+boundary)
    _assert_missing_folder_isolated(sandbox,[first,second],healthy,proc,folder,moved)
    child=sandbox.job(first).get('childPid')
    if child: _wait_for(lambda:not _running(child),label='child reaped after failed flush')
    assert _call_count(sandbox.data)==0


def test_asset_registration_rejects_symlink_escape_before_write(sandbox):
    s = sandbox.s
    data = _png() + b'owned unique fixture'
    sha = s.digest(data)
    outside = sandbox.tmp / 'outside-data'
    outside.mkdir()
    assets = s.DATA / 'assets'
    assets.mkdir(exist_ok=True)
    prefix = assets / sha[:2]
    assert not prefix.exists(), 'fixture hash must choose an unused prefix'
    prefix.symlink_to(outside, target_is_directory=True)
    try:
        s.register_asset(data, 'test.png')
    except (s.AppError, OSError):
        pass
    assert not (outside / sha).exists(), 'asset bytes escaped the managed data directory'


def test_read_path_rejects_symlink_escape_and_corrupted_original(sandbox):
    s = sandbox.s
    aid = sandbox.original['assetId']
    original = s.asset_path(aid)
    original.write_bytes(b'corrupted fixture')
    with pytest.raises(s.AppError) as error:
        s.asset_path(aid)
    assert error.value.code == 'ASSET_HASH'
    outside = sandbox.tmp / 'outside-image.png'
    outside.write_bytes(_png())
    original.unlink(); original.symlink_to(outside)
    with pytest.raises(s.AppError) as error:
        s.asset_path(aid)
    assert error.value.code == 'ASSET_MISSING'


def test_api_rejects_missing_token_bad_origin_and_stale_export(sandbox):
    from fastapi.testclient import TestClient
    with TestClient(sandbox.api.app) as client:
        token = client.get('/v1/health').json()['sessionToken']
        assert client.post('/v1/projects', json={'name': 'blocked'}).status_code == 403
        assert client.post('/v1/projects', json={'name': 'blocked'}, headers={
            'X-Session-Token': token, 'Origin': 'https://example.invalid'}).status_code == 403
        response = client.post(f"/v1/projects/{sandbox.project['projectId']}/exports", headers={
            'X-Session-Token': token}, json={'savedRevision': 0, 'clipRevisionIds': [], 'idempotencyKey': 'stale'})
        assert response.status_code == 409 and response.json()['code'] == 'REVISION_CONFLICT'


# All harness helpers below run only in test-owned subprocesses. The production
# source files are never rewritten. A patched fake provider is the only generate
# implementation visible to the test task; no login or Codex exec can occur.
def _deny_network():
    def denied(*args, **kwargs):
        raise AssertionError('network is forbidden in worker recovery tests')
    socket.socket.connect = denied
    socket.create_connection = denied


def _harness_worker():
    _deny_network()
    from services.worker import main as worker
    mode = os.environ['SPRITE_RECOVERY_TEST_MODE']
    original_popen = subprocess.Popen

    def spawn(argv, *args, **kwargs):
        if isinstance(argv, list) and 'services.worker.task' in argv:
            index = argv.index('services.worker.task')
            argv = [sys.executable, str(THIS_FILE), '--harness-task', 'services.worker.task', *argv[index + 1:]]
        return original_popen(argv, *args, **kwargs)
    worker.subprocess.Popen = spawn

    if mode in ('lose-folder-claim','lose-folder-spawn'):
        original_write_job=worker.s.write_job
        moved_once=False
        def lose_folder(c,j):
            nonlocal moved_once
            original_write_job(c,j)
            at_boundary=j['status']=='running' and (bool(j.get('childPid')) if mode=='lose-folder-spawn' else not j.get('childPid'))
            if at_boundary and not moved_once:
                moved_once=True
                worker.s.project_folder(j['projectId'],c).rename(worker.s.DATA/'test-offline-project')
        worker.s.write_job=lose_folder

    if mode == 'lose-folder-publish':
        original_publish=worker.publish
        moved_once=False
        def lose_folder_before_publish(j,payload):
            nonlocal moved_once
            if not moved_once:
                moved_once=True
                worker.s.project_folder(j['projectId']).rename(worker.s.DATA/'test-offline-project')
            return original_publish(j,payload)
        worker.publish=lose_folder_before_publish

    if mode == 'fail-before-publish-once':
        original_publish = worker.publish
        failed_once = False
        def fail_once(j, payload):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError('test-only publication failure before rename')
            return original_publish(j, payload)
        worker.publish = fail_once
    elif mode == 'fail-after-rename-once':
        original_write_project = worker.s.write_project
        failed_once = False
        def fail_project_once(*args, **kwargs):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError('test-only DB publication failure after rename')
            return original_write_project(*args, **kwargs)
        worker.s.write_project = fail_project_once

    if mode == 'hold-before-publish':
        def hold(j, payload):
            path = worker.s.job_directory(j['jobId']) / j['attemptId'] / 'staging'
            worker.s.atomic_bytes(worker.s.DATA / 'test-publication-boundary.json', json.dumps({'path': str(path)}).encode())
            while True:
                time.sleep(.1)
        worker.publish = hold
    elif mode == 'hold-after-rename':
        original_replace = os.replace
        def replace(src, dst, *args, **kwargs):
            result = original_replace(src, dst, *args, **kwargs)
            if Path(src).name == 'staging':
                worker.s.atomic_bytes(worker.s.DATA / 'test-publication-boundary.json', json.dumps({'path': str(dst)}).encode())
                while True:
                    time.sleep(.1)
            return result
        worker.os.replace = replace
    worker.main()


def _harness_task():
    _deny_network()
    from services.worker import task
    from adapters.spritegen import provider
    mode = os.environ['SPRITE_RECOVERY_TEST_MODE']

    def fake_generate(params, reference, asset_path, out_dir):
        s = task.s
        out_dir.mkdir(parents=True, exist_ok=True)
        with (s.DATA / 'test-provider-calls.jsonl').open('a') as stream:
            stream.write(json.dumps({'pid': os.getpid(), 'testOnly': True}) + '\n')
            stream.flush(); os.fsync(stream.fileno())
        child = None
        if mode in ('stubborn-provider', 'orphan-descendant'):
            child = subprocess.Popen([sys.executable, str(THIS_FILE), '--harness-grandchild'], env=os.environ.copy())
            _wait_for((s.DATA / 'test-descendant-ready').exists, label='test descendant ready')
        if mode == 'stubborn-provider':
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        s.atomic_bytes(s.DATA / 'test-provider-entered.json', json.dumps({
            'pid': os.getpid(), 'descendantPid': child.pid if child else None}).encode())
        if mode in ('wait-provider', 'stubborn-provider', 'orphan-descendant'):
            while True:
                time.sleep(.1)
        path = out_dir / 'fake-generated.png'
        path.write_bytes(_png())
        receipt = {'testOnly': True, 'sessionId': 'no-network', 'sha256': s.digest(path.read_bytes())}
        s.atomic_bytes(out_dir / 'test-provider-receipt.json', s.dumps(receipt).encode())
        if mode == 'post-provider-error':
            def fail(*args, **kwargs):
                raise OSError('simulated local disk failure after provider success')
            s.register_asset = fail
        return {'paths': [str(path)], 'requestSnapshot': {'testOnly': True}, 'receipt': receipt,
                'providerId': 'codex', 'model': 'test-only'}
    original_execute = task.execute
    def recorded_execute(j, out):
        with (task.s.DATA / 'test-task-executions.jsonl').open('a') as stream:
            stream.write(json.dumps({'attemptId': j['attemptId']}) + '\n')
        return original_execute(j, out)
    task.execute = recorded_execute
    provider.generate = fake_generate
    sys.argv = ['services.worker.task', *sys.argv[-2:]]
    task.main()


def _harness_grandchild():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    data = Path(os.environ['SPRITE_DATA_DIR'])
    (data / 'test-descendant-ready').write_text(str(os.getpid()))
    while True:
        time.sleep(.1)


if __name__ == '__main__':
    entry = sys.argv[1]
    if entry == '--harness-worker':
        _harness_worker()
    elif entry == '--harness-task':
        _harness_task()
    elif entry == '--harness-grandchild':
        _harness_grandchild()
    else:
        raise SystemExit('This file is only a pytest subprocess harness.')
