"""Local-only contract/regression tests. No external generation calls."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from adapters.spritegen import provider
from sprite_gen import gen
from sprite_gen.gen import codex_provider
from sprite_gen.gen.base import GenTimeoutError, GenResult


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    assets = {}
    for name in ('identity', 'style', 'pose'):
        path = tmp_path / f'{name}.png'
        Image.new('RGBA', (16, 20), (10, 100, 20, 255)).save(path)
        assets[name] = path
    monkeypatch.setattr(provider, '_login_probe', lambda: {'loginReady': True, 'authMode': 'chatgpt',
                                                        'lastProbe': 'test', 'reason': None})
    monkeypatch.setattr(provider, '_models', lambda: [provider.DEFAULT_MODEL])
    params = {'providerId': 'codex', 'model': provider.DEFAULT_MODEL, 'prompt': '  walk & $(do not run)  ',
              'frameCount': 4, 'scope': 'sheet'}
    reference = {'referenceRevisionId': 'r1', 'approval': 'approved', 'identityAssetId': 'identity',
                 'styleAssetIds': ['style'], 'poseAssetIds': ['pose'], 'fixedTraits': 'green hair',
                 'allowedChanges': 'pose', 'forbiddenTransfers': 'costume', 'facing': 'right'}
    return params, reference, assets.__getitem__, tmp_path / 'output'


def test_capabilities_do_not_invoke_generation(monkeypatch):
    monkeypatch.setattr(gen, 'generate_image', lambda *a, **k: pytest.fail('must not generate'))
    monkeypatch.setattr(provider, '_login_probe', lambda: {'loginReady': True, 'lastProbe': 'now', 'authMode': 'chatgpt'})
    codex, openai, grok = provider.providers()
    assert codex['billingRoute'] == 'chatgpt-subscription'
    assert codex['quota'] == 'unknown'
    assert codex['lastSuccess'] is None and not codex['generationVerified']
    assert not codex['capabilities']['quality'] and not codex['capabilities']['resolution']
    assert codex['capabilities']['concurrency'] == 1
    assert codex['capabilities']['nativeAlphaRequest'] is True
    assert codex['capabilities']['layoutGuide'] is True
    assert 'regeneration-target' in codex['capabilities']['referenceRoles']
    assert codex['capabilities']['transparentOutputGuaranteed'] is False
    assert codex['capabilities']['remoteCancel'] is False
    assert codex['capabilities']['resultLookup'] is False
    assert not openai['enabled'] and not grok['enabled']


@pytest.mark.parametrize('output,returncode,ready', [
    ('Logged in using ChatGPT', 0, True), ('Logged in using an API key', 0, False),
    ('Logged in using ChatGPT', 1, False), ('', 0, False), ('Not logged in', 1, False)])
def test_readiness_distinguishes_subscription_login(monkeypatch, output, returncode, ready):
    monkeypatch.setattr(provider.shutil, 'which', lambda _: '/test/codex')
    seen = []
    def run(argv, **kwargs):
        seen.append(argv)
        return SimpleNamespace(returncode=returncode, stdout='', stderr=output)
    monkeypatch.setattr(provider.subprocess, 'run', run)
    assert provider._login_probe()['loginReady'] is ready
    assert seen == [['/test/codex', 'login', 'status']]


@pytest.mark.parametrize('change,code', [
    ({'providerId': None}, 'provider.unsupported'), ({'providerId': 'openai'}, 'provider.unsupported'),
    ({'providerId': 'grok'}, 'provider.unsupported'), ({'quality': 'auto'}, 'provider.unsupported_option'),
    ({'resolution': '1k'}, 'provider.unsupported_option'), ({'aspectRatio': '1:1'}, 'provider.unsupported_option'),
    ({'model': 'unsupported-model'}, 'provider.unsupported_model'), ({'prompt': ' '}, 'provider.invalid_prompt'),
    ({'frameCount': 0}, 'provider.invalid_frame_count'), ({'frameCount': True}, 'provider.invalid_frame_count'),
    ({'layoutGuide': 'true'}, 'provider.invalid_layout_guide'), ({'layoutGuide': 1}, 'provider.invalid_layout_guide'),
    ({'layoutGuide': None}, 'provider.invalid_layout_guide'), ({'layoutGuide': True}, 'provider.invalid_layout_guide'),
    ({'scope': 'frame'}, 'provider.invalid_scope'), ({'scope': 'other'}, 'provider.invalid_scope')])
def test_validation_before_any_submission(inputs, monkeypatch, change, code):
    params, reference, asset_path, out_dir = inputs
    params.update(change)
    monkeypatch.setattr(gen, 'generate_image', lambda *a, **k: pytest.fail('must not generate'))
    with pytest.raises(provider.ProviderError) as error:
        provider.generate(params, reference, asset_path, out_dir)
    assert error.value.code == code and not error.value.outcome_unknown
    assert not out_dir.exists()


def test_reference_approval_gate(inputs, monkeypatch):
    params, reference, asset_path, out_dir = inputs
    reference['approval'] = 'draft'
    with pytest.raises(provider.ProviderError, match='승인'):
        provider.generate(params, reference, asset_path, out_dir)
    assert not out_dir.exists()


def test_generate_passes_roles_and_preserves_receipt_and_raw(inputs, monkeypatch):
    params, reference, asset_path, out_dir = inputs
    original = copy.deepcopy((params, reference))
    before = asset_path('identity').read_bytes()
    seen = []
    monkeypatch.setattr(gen, 'draw_layout_guide', lambda *a: pytest.fail('disabled guide must not be drawn'))
    def generate(provider_id, prompt, out, **kwargs):
        seen.append((provider_id, prompt, out, kwargs))
        assert (out.parent / 'submission.json').is_file()
        assert (out.parent / 'request-snapshot.json').is_file()
        assert [p.name for p in kwargs['refs']] == ['001-identity.png', '002-style.png', '003-pose.png']
        Image.new('RGBA', (64, 20), (10, 100, 20, 255)).save(out)
        raw = out.with_suffix('.png.raw.png')
        raw.write_bytes(out.read_bytes())
        return GenResult(provider='codex', prompt=prompt, out=out, raw=raw, raw_bytes=out.stat().st_size,
                         elapsed_seconds=1.2, model=kwargs['model'], session_id='fake-session', refs=kwargs['refs'],
                         extra={'inline_results': 1, 'raw_metadata': {'unchanged': True}})
    monkeypatch.setattr(gen, 'generate_image', generate)
    result = provider.generate(params, reference, asset_path, out_dir)
    assert len(seen) == 1 and seen[0][0] == 'codex'
    prompt, options = seen[0][1], seen[0][3]
    assert prompt.startswith('walk & $(do not run)  \n')
    assert 'Image 2: style.' in prompt and 'Image 3: pose.' in prompt
    assert result['requestSnapshot']['prompt'] == params['prompt'] == '  walk & $(do not run)  '
    assert result['requestSnapshot']['enginePrompt'] == prompt
    assert options['model'] == provider.DEFAULT_MODEL
    assert options['quality'] is None and options['resolution'] is None
    assert options['facing'] is None and options['facing_fix'] == 'none' and options['keep_session']
    assert not options['transparent'] and not options['trim_alpha']
    assert options['layout_guide'] is False
    assert result['requestSnapshot']['layoutGuide'] == {'enabled': False}
    assert result['requestSnapshot']['params'] == params
    assert result['requestSnapshot']['requestedNativeAlpha'] is False
    assert result['requestSnapshot']['reference'] == reference
    assert result['receipt']['requestedFrameCount'] == 4 and result['receipt']['returnedImageCount'] == 1
    assert result['receipt']['actualFrameCount'] is None
    assert (params, reference) == original and asset_path('identity').read_bytes() == before
    receipt = json.loads((out_dir / 'provider-attempt/engine-receipt.json').read_text())
    assert receipt['extra']['raw_metadata'] == {'unchanged': True}
    assert receipt['prompt'] == prompt and receipt['session_id'] == 'fake-session'
    with pytest.raises(provider.ProviderError) as error:
        provider.generate(params, reference, asset_path, out_dir)
    assert error.value.code == 'provider.attempt_exists' and len(seen) == 1


@pytest.mark.parametrize('failure', [GenTimeoutError('timeout'), SystemExit('API_KEY=should-not-leak'),
                                     ConnectionError('dropped'), ValueError('bad image')])
def test_unknown_outcome_never_retries_or_leaks(inputs, monkeypatch, failure):
    params, reference, asset_path, out_dir = inputs
    calls = []
    def fail(*a, **kw):
        calls.append(1)
        raise failure
    monkeypatch.setattr(gen, 'generate_image', fail)
    with pytest.raises(provider.ProviderError) as error:
        provider.generate(params, reference, asset_path, out_dir)
    assert error.value.code == 'provider.outcome_unknown' and error.value.outcome_unknown
    assert len(calls) == 1 and 'API_KEY' not in error.value.message
    attempt = out_dir / 'provider-attempt'
    assert json.loads((attempt / 'failure.json').read_text())['outcomeUnknown']
    assert (attempt / 'request-snapshot.json').is_file() and (attempt / 'submission.json').is_file()


def test_engine_timeout_is_not_retried(tmp_path, monkeypatch):
    calls = []
    class TimeoutBackend:
        def generate(self, request, workdir):
            calls.append(1)
            raise GenTimeoutError('accepted but response lost')
    monkeypatch.setattr(gen, '_make_provider', lambda *a, **k: TimeoutBackend())
    with pytest.raises(GenTimeoutError):
        gen.generate_image('codex', 'test', tmp_path / 'out.png', workdir=tmp_path)
    assert calls == [1]


def test_layout_guide_failure_is_pre_submission_and_preserves_inputs(inputs, monkeypatch):
    params, reference, asset_path, out_dir = inputs
    params.update(layoutGuide=True, frameCount=1)
    before = {aid: asset_path(aid).read_bytes() for aid in ('identity', 'style', 'pose')}
    monkeypatch.setattr(gen, 'generate_image', lambda *a, **k: pytest.fail('must not submit'))
    def fail(*args):
        raise OSError('private path must not leak')
    monkeypatch.setattr(gen, 'draw_layout_guide', fail)
    with pytest.raises(provider.ProviderError) as error:
        provider.generate(params, reference, asset_path, out_dir)
    assert error.value.code == 'provider.layout_guide_failed'
    assert error.value.outcome_unknown is False
    assert 'private path' not in error.value.message
    assert not (out_dir / 'provider-attempt/submission.json').exists()
    assert not (out_dir / 'provider-attempt/failure.json').exists()
    assert before == {aid: asset_path(aid).read_bytes() for aid in before}


@pytest.mark.parametrize('background', [None, 'transparent', 'white', 'green', 'magenta'])
@pytest.mark.parametrize('frame_regeneration', [False, True], ids=['sheet', 'frame-target'])
@pytest.mark.parametrize('layout_guide', [False, True], ids=['no-guide', 'local-guide'])
def test_real_engine_transport_local_rollout_preserved(inputs, monkeypatch, tmp_path, background, frame_regeneration, layout_guide):
    """Real adapter+engine path, fake only CLI transport. No external call."""
    params, reference, asset_path, out_dir = inputs
    if background is not None:
        params['background'] = background
    if layout_guide:
        params.update(layoutGuide=True, frameCount=1)
    target = None
    if frame_regeneration:
        params.update(scope='frame', frameCount=1, frameVersionId='selected-frame-v2')
        target_path = tmp_path / 'selected-crop.png'
        Image.new('RGBA', (9, 13), (200, 70, 20, 255)).save(target_path)
        target_bytes = target_path.read_bytes()
        target = {'frameVersionId': params['frameVersionId'], 'imageAssetId': 'selected-crop',
                  'sha256': hashlib.sha256(target_bytes).hexdigest(), 'rawAssetId': 'sheet-original',
                  'sourceRect': {'x': 12, 'y': 20, 'width': 9, 'height': 13}}
        original_asset_path = asset_path
        asset_path = lambda aid: target_path if aid == 'selected-crop' else original_asset_path(aid)
    original_inputs = copy.deepcopy((params, reference, target))
    codex_home = tmp_path / 'codex-account'
    codex_home.mkdir()
    monkeypatch.setenv('CODEX_HOME', str(codex_home))
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-leak')
    monkeypatch.setenv('CODEX_API_KEY', 'must-not-leak')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://example.invalid')
    monkeypatch.setenv('CODEX_THREAD_ID', 'parent')
    buffer = io.BytesIO()
    Image.new('RGBA', (16, 20), (30, 90, 10, 255)).save(buffer, format='PNG')
    payload = json.dumps({'type': 'response_item', 'payload': {
        'type': 'image_generation_call', 'status': 'completed',
        'result': base64.b64encode(buffer.getvalue()).decode()}}) + '\n'
    sid = '018f0000-0000-7000-8000-000000000009'
    rollout = codex_home / 'sessions' / f'rollout-{sid}.jsonl'
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        # Evidence must describe the exact files and full prompt before the sole
        # transport call. No generated guide may be appended behind the snapshot.
        attempt = out_dir / 'provider-attempt'
        snapshot = json.loads((attempt / 'request-snapshot.json').read_text())
        attached = [Path(argv[i + 1]) for i, value in enumerate(argv) if value == '-i']
        assert attached == [attempt / ref['file'] for ref in snapshot['references']]
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in attached] == [
            ref['sha256'] for ref in snapshot['references']]
        assert snapshot['enginePrompt'] in kwargs['input']
        assert snapshot['enginePrompt'] == kwargs['input'].split('프롬프트:\n', 1)[1].removesuffix('\n')
        assert snapshot['promptHash'] == hashlib.sha256(snapshot['enginePrompt'].encode()).hexdigest()
        assert snapshot['prompt'] == snapshot['params']['prompt'] == original_inputs[0]['prompt']
        rollout.parent.mkdir()
        rollout.write_text(payload)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'type': 'thread.started', 'thread_id': sid}), stderr='')
    monkeypatch.setattr(codex_provider.subprocess, 'run', run)
    result = provider.generate(params, reference, asset_path, out_dir, regeneration_target=target)
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert isinstance(argv, list) and '--ignore-user-config' in argv and 'model_provider="openai"' in argv
    assert 'forced_login_method="chatgpt"' in argv
    assert kwargs.get('shell', False) is False and not kwargs.get('start_new_session', False)
    assert all(k not in kwargs['env'] for k in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'CODEX_THREAD_ID'))
    attempt = out_dir / 'provider-attempt'
    assert (attempt / 'codex-rollout.jsonl').read_text() == payload
    assert rollout.is_file()
    assert (attempt / 'transport-prompt.txt').read_text() == kwargs['input']
    assert json.loads((attempt / 'engine-receipt.json').read_text())['prompt'] == result['requestSnapshot']['enginePrompt']
    assert Path(result['paths'][0]).read_bytes() == buffer.getvalue()
    assert (attempt / 'generated.png.raw.png').read_bytes() == buffer.getvalue()
    assert result['receipt']['sessionId'] == sid
    assert (params, reference, target) == original_inputs
    snapshot = result['requestSnapshot']
    assert snapshot['params'] == params and snapshot['regenerationTarget'] == target
    assert 'regenerationTarget' not in params
    attachments = [Path(argv[i + 1]) for i, value in enumerate(argv) if value == '-i']
    assert len(attachments) == (4 if frame_regeneration else 3) + int(layout_guide)
    assert attachments[0].read_bytes() == asset_path('identity').read_bytes()
    assert attachments[1].read_bytes() == asset_path('style').read_bytes()
    assert attachments[2].read_bytes() == asset_path('pose').read_bytes()
    assert [ref['role'] for ref in snapshot['references'][:3]] == ['identity', 'style', 'pose']
    if frame_regeneration:
        attached_target = snapshot['references'][3]
        assert attached_target['role'] == 'regeneration-target'
        assert attached_target['frameVersionId'] == params['frameVersionId']
        assert attached_target['assetId'] == target['imageAssetId']
        assert attached_target['sha256'] == target['sha256']
        assert attachments[3].name == '004-regeneration-target.png'
        assert attachments[3].read_bytes() == target_path.read_bytes() == target_bytes
        with Image.open(attachments[3]) as attached:
            assert attached.size == (9, 13)  # no normalization or per-pose fit
        assert 'This is the selected frame to regenerate' in kwargs['input']
        assert 'pose/action as the replacement target' in kwargs['input']
        assert 'identity image and its fixed traits take priority' in kwargs['input']
        assert 'single replacement for the selected regeneration-target frame' in snapshot['enginePrompt']
    else:
        assert all(ref['role'] != 'regeneration-target' for ref in snapshot['references'])
    assert snapshot['engineOptions']['layout_guide'] is False
    if layout_guide:
        guide = snapshot['layoutGuide']
        record = snapshot['references'][-1]
        assert guide['enabled'] is True
        assert record['role'] == 'derived-guide' and record['assetId'] is None
        assert record['origin'] == {'kind': 'local-layout-guide', 'generator': 'sprite_gen.gen.draw_layout_guide',
                                    'aspectRatio': None, 'cell': guide['cell']}
        assert guide['sha256'] == record['sha256'] == hashlib.sha256(attachments[-1].read_bytes()).hexdigest()
        assert guide['file'] == record['file'] and attempt / guide['file'] == attachments[-1]
        assert guide['prompt'] == gen.layout_guide_text(guide['cell'])
        assert snapshot['enginePrompt'].count(guide['prompt']) == 1
        assert 'NOT user artwork' in snapshot['enginePrompt']
        assert 'no boxes, guide lines' in kwargs['input']
        with Image.open(attachments[-1]) as image:
            cell = guide['cell']
            assert image.size == (cell['width'], cell['height']) == (1024, 1024)
            assert 0 < cell['crown_y'] < cell['floor_y'] < image.height
            assert image.getpixel((cell['safe_margin_x'] + 1, cell['crown_y'])) == (255, 122, 0)
            assert image.getpixel((cell['safe_margin_x'] + 1, cell['floor_y'])) == (0, 167, 167)
        assert not (attempt / 'layout-guide.png').exists()  # no second engine-generated guide
    else:
        assert snapshot['layoutGuide'] == {'enabled': False}
    assert json.loads((attempt / 'request-snapshot.json').read_text()) == snapshot
    assert result['requestSnapshot']['requestedNativeAlpha'] is (background == 'transparent')
    assert result['requestSnapshot']['engineOptions']['transparent'] is False
    assert result['receipt']['alphaStats'] == {'transparent': 0, 'partial': 0, 'opaque': 320}
    assert result['receipt']['alphaChannelPresent'] is True
    if background == 'transparent':
        assert 'genuinely transparent PNG with a real alpha channel' in kwargs['input']
        assert 'use its transparent background option' in kwargs['input']
        assert 'not a painted checkerboard' in kwargs['input']
    elif background is not None:
        color = {'white': '#FFFFFF', 'green': '#00FF00', 'magenta': '#FF00FF'}[background]
        assert f'solid {background} ({color})' in kwargs['input']
        assert 'uniform, flat background' in kwargs['input']


def test_codex_timeout_preserves_stream(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, 180, output=b'{"partial":true}\n', stderr=b'stalled')
    monkeypatch.setattr(codex_provider.subprocess, 'run', run)
    with pytest.raises(GenTimeoutError):
        gen.generate_image('codex', 'a sprite', tmp_path / 'out.png', workdir=tmp_path)
    assert len(calls) == 1
    assert (tmp_path / 'codex-stdout.jsonl').read_bytes() == b'{"partial":true}\n'
    assert (tmp_path / 'codex-stderr.txt').read_bytes() == b'stalled'


@pytest.mark.parametrize('mode', ['mixed-rgba', 'opaque-rgba', 'rgb', 'palette-trns'])
@pytest.mark.parametrize('layout_guide', [False, True])
def test_native_alpha_request_measures_actual_output_without_modifying_raw(inputs, monkeypatch, mode, layout_guide):
    params, reference, asset_path, out_dir = inputs
    params['background'] = 'transparent'
    if layout_guide:
        params.update(layoutGuide=True, frameCount=1)
    if mode == 'mixed-rgba':
        image = Image.new('RGBA', (2, 2))
        image.putdata([(1, 2, 3, 0), (10, 20, 30, 128), (40, 50, 60, 255), (70, 80, 90, 0)])
    elif mode == 'opaque-rgba':
        image = Image.new('RGBA', (2, 2), (10, 20, 30, 255))
    elif mode == 'rgb':
        image = Image.new('RGB', (2, 2), (10, 20, 30))
    else:
        image = Image.new('P', (2, 2))
        image.putpalette([0, 0, 0, 10, 20, 30, 40, 50, 60] + [0] * (768 - 9))
        image.putdata([0, 1, 2, 0])
        image.info['transparency'] = bytes([0, 128, 255])
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    original_bytes = buffer.getvalue()
    calls = []

    def generate(provider_id, prompt, out, **kwargs):
        calls.append((provider_id, prompt, kwargs))
        assert kwargs['transparent'] is False and kwargs['trim_alpha'] is False
        out.write_bytes(original_bytes)
        raw = out.with_suffix('.png.raw.png')
        raw.write_bytes(original_bytes)
        return GenResult(provider='codex', prompt=prompt, out=out, raw=raw, raw_bytes=len(original_bytes),
                         elapsed_seconds=0.1, model=kwargs['model'], refs=kwargs['refs'],
                         extra={'transparent_background_reported': True})
    monkeypatch.setattr(gen, 'generate_image', generate)
    result = provider.generate(params, reference, asset_path, out_dir)
    assert len(calls) == 1  # An opaque answer must never trigger regeneration.
    assert Path(result['paths'][0]).read_bytes() == original_bytes
    assert (out_dir / 'provider-attempt/generated.png.raw.png').read_bytes() == original_bytes
    expected = {'transparent': 2, 'partial': 1, 'opaque': 1} if mode in ('mixed-rgba', 'palette-trns') else {
        'transparent': 0, 'partial': 0, 'opaque': 4}
    assert result['receipt']['alphaStats'] == expected
    assert result['receipt']['alphaChannelPresent'] is (mode != 'rgb')
    assert result['receipt']['engineExtra']['transparent_background_reported'] is True
    snapshot = json.loads((out_dir / 'provider-attempt/request-snapshot.json').read_text())
    receipt = json.loads((out_dir / 'provider-attempt/receipt.json').read_text())
    assert snapshot == result['requestSnapshot'] and snapshot['requestedNativeAlpha'] is True
    assert receipt == result['receipt'] and sum(receipt['alphaStats'].values()) == 4


@pytest.mark.parametrize('case,code', [
    ('missing-target', 'provider.regeneration_target_required'),
    ('missing-selected-id', 'provider.regeneration_target_required'),
    ('different-frame', 'provider.invalid_regeneration_target'),
    ('missing-asset', 'provider.invalid_regeneration_target'),
    ('missing-hash', 'provider.invalid_regeneration_target'),
    ('malformed-hash', 'provider.invalid_regeneration_target'),
    ('changed-pixels', 'provider.regeneration_target_changed'),
    ('sheet-target', 'provider.invalid_regeneration_target'),
])
def test_frame_regeneration_requires_matching_target_before_any_call(inputs, monkeypatch, case, code):
    params, reference, asset_path, out_dir = inputs
    params.update(scope='frame', frameCount=1, frameVersionId='selected-frame')
    target = {'frameVersionId': 'selected-frame', 'imageAssetId': 'pose',
              'sha256': hashlib.sha256(asset_path('pose').read_bytes()).hexdigest()}
    if case == 'missing-target':
        target = None
    elif case == 'missing-selected-id':
        params.pop('frameVersionId')
    elif case == 'different-frame':
        target['frameVersionId'] = 'another-frame'
    elif case == 'missing-asset':
        target.pop('imageAssetId')
    elif case == 'missing-hash':
        target.pop('sha256')
    elif case == 'malformed-hash':
        target['sha256'] = 'not-a-hash'
    elif case == 'changed-pixels':
        target['sha256'] = '0' * 64
    elif case == 'sheet-target':
        params['scope'] = 'sheet'
    monkeypatch.setattr(gen, 'generate_image', lambda *a, **k: pytest.fail('must not generate'))
    monkeypatch.setattr(provider, '_login_probe', lambda: pytest.fail('must reject before login probe'))
    with pytest.raises(provider.ProviderError) as error:
        provider.generate(params, reference, asset_path, out_dir, regeneration_target=target)
    assert error.value.code == code and not error.value.outcome_unknown
    assert not out_dir.exists()
