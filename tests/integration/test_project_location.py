"""The file manager is mocked here; real desktop launch is checked separately."""
from unittest.mock import Mock
import base64
from pathlib import Path
import subprocess
import pytest
from fastapi.testclient import TestClient
from services.api import desktop, store as s
from services.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / '한글 자료 $test (공용)')
    s.init()
    with TestClient(app) as client:
        client.headers['X-Session-Token'] = client.get('/v1/health').json()['sessionToken']
        yield client


@pytest.mark.parametrize('platform,manager', [('darwin', 'finder'), ('win32', 'explorer'), ('linux', None)])
def test_file_manager_detection(platform, manager, monkeypatch):
    monkeypatch.setattr(desktop.sys, 'platform', platform)
    assert desktop.file_manager() == manager


@pytest.mark.parametrize('manager', ['finder', 'explorer', None])
def test_health_advertises_server_capability_without_opening(client, monkeypatch, manager):
    monkeypatch.setattr(desktop, 'file_manager', lambda: manager)
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    monkeypatch.setattr(desktop.os, 'startfile', launch, raising=False)
    assert client.get('/v1/health').json()['desktop'] == {'fileManager': manager}
    assert client.get('/v1/health').json()['projectStorage'] == {'layout': 'project-folder', 'defaultParent': str(s.DATA / 'projects')}
    launch.assert_not_called()


@pytest.mark.parametrize('manager', ['finder', 'explorer'])
def test_reveal_uses_project_folder_and_preserves_projects(client, monkeypatch, manager):
    project = client.post('/v1/projects', json={'name': '경로로 사용하면 안 됨 ; $(whoami)'}).json()
    other = client.post('/v1/projects', json={'name': '다른 프로젝트'}).json()
    before = client.get('/v1/projects').json()
    history = client.get(f'/v1/projects/{project["projectId"]}/revisions').json()
    monkeypatch.setattr(desktop, 'file_manager', lambda: manager)
    mac, windows = Mock(), Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', mac)
    monkeypatch.setattr(desktop.os, 'startfile', windows, raising=False)
    r = client.post(f'/v1/projects/{project["projectId"]}/reveal', json={})
    assert r.status_code == 200, r.text
    folder = Path(project['storage']['path'])
    assert folder.is_dir() and folder != s.DATA.resolve()
    assert folder != Path(other['storage']['path'])
    assert r.json() == {'projectId': project['projectId'], 'path': str(folder), 'fileManager': manager, 'storageLayout': 'project-folder'}
    if manager == 'finder':
        mac.assert_called_once_with(['/usr/bin/open', str(folder)], check=True, capture_output=True, timeout=5)
        windows.assert_not_called()
    else:
        windows.assert_called_once_with(str(folder), 'explore')
        mac.assert_not_called()
    assert client.get('/v1/projects').json() == before
    assert client.get(f'/v1/projects/{project["projectId"]}/revisions').json() == history
    assert client.get(f'/v1/projects/{other["projectId"]}').json()['revision'] == 1
    assert (folder / 'project.json').is_file() and (folder / 'project.sqlite3').is_file()


@pytest.mark.parametrize('body', [{'path': '/tmp'}, {'command': 'open /tmp'}, {'args': ['-a', 'Terminal']}, [], None])
def test_reveal_rejects_arbitrary_inputs(client, monkeypatch, body):
    project = client.post('/v1/projects', json={'name': '임의 경로 거부'}).json()
    launch = Mock()
    monkeypatch.setattr(desktop, 'reveal_project', launch)
    r = client.post(f'/v1/projects/{project["projectId"]}/reveal', json=body)
    assert r.status_code == 422
    launch.assert_not_called()


@pytest.mark.parametrize('headers', [{'X-Session-Token': ''}, {'Origin': 'https://evil.invalid'}])
def test_reveal_requires_local_session(client, monkeypatch, headers):
    project = client.post('/v1/projects', json={'name': '세션 검사'}).json()
    launch = Mock()
    monkeypatch.setattr(desktop, 'reveal_project', launch)
    r = client.post(f'/v1/projects/{project["projectId"]}/reveal', json={}, headers=headers)
    assert r.status_code == 403
    launch.assert_not_called()


def test_deleted_project_cannot_open_file_manager(client, monkeypatch):
    project = client.post('/v1/projects', json={'name': '삭제된 프로젝트'}).json()
    url = f'/v1/projects/{project["projectId"]}'
    assert client.request('DELETE', url, json={'expectedRevision': 1}).status_code == 200
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    monkeypatch.setattr(desktop.os, 'startfile', launch, raising=False)
    r = client.post(url + '/reveal', json={})
    assert r.status_code == 404 and r.json()['code'] == 'PROJECT_NOT_FOUND'
    launch.assert_not_called()


@pytest.mark.parametrize('manager,error', [
    ('finder', FileNotFoundError()), ('finder', subprocess.CalledProcessError(1, 'open')),
    ('finder', subprocess.TimeoutExpired('open', 5)), ('explorer', OSError('launch failed')),
])
def test_launch_errors_are_not_reported_as_success(client, monkeypatch, manager, error):
    project = client.post('/v1/projects', json={'name': '실행 실패'}).json()
    url = f'/v1/projects/{project["projectId"]}'
    monkeypatch.setattr(desktop, 'file_manager', lambda: manager)
    launch = Mock(side_effect=error)
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    monkeypatch.setattr(desktop.os, 'startfile', launch, raising=False)
    r = client.post(url + '/reveal', json={})
    assert r.status_code == 503 and r.json()['code'] == 'FILE_MANAGER_UNAVAILABLE'
    assert client.get(url).json() == project


def test_unsupported_os_is_explicit(client, monkeypatch):
    project = client.post('/v1/projects', json={'name': '미지원 OS'}).json()
    monkeypatch.setattr(desktop, 'file_manager', lambda: None)
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    r = client.post(f'/v1/projects/{project["projectId"]}/reveal', json={})
    assert r.status_code == 501 and r.json()['code'] == 'FILE_MANAGER_UNSUPPORTED'
    launch.assert_not_called()


@pytest.mark.parametrize('manager', ['finder', 'explorer'])
@pytest.mark.parametrize('purpose', ['open', 'parent'])
def test_native_picker_returns_selected_path_without_interpreting_it(tmp_path, monkeypatch, manager, purpose):
    selected = tmp_path / '한글 폴더 ; $(touch hacked) [입력]'
    selected.mkdir()
    monkeypatch.setattr(desktop, 'file_manager', lambda: manager)
    launch = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=str(selected) + '\n', stderr=''))
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    assert desktop.pick_folder(purpose) == str(selected.resolve())
    args, kwargs = launch.call_args
    command = args[0]
    assert kwargs == {'check': True, 'capture_output': True, 'text': True, 'encoding': 'utf-8', 'timeout': 300}
    assert str(selected) not in str(command)
    if manager == 'finder':
        assert command[:2] == ['/usr/bin/osascript', '-e']
        assert 'choose folder' in command[2] and 'on error number -128' in command[2]
    else:
        assert command[:5] == ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-EncodedCommand']
        script = base64.b64decode(command[5]).decode('utf-16le')
        assert 'FolderBrowserDialog' in script and '$dialog.Dispose()' in script
        assert f"$dialog.ShowNewFolderButton = ${'true' if purpose == 'parent' else 'false'}" in script


@pytest.mark.parametrize('manager', ['finder', 'explorer'])
def test_picker_cancel_returns_null(monkeypatch, manager):
    monkeypatch.setattr(desktop, 'file_manager', lambda: manager)
    monkeypatch.setattr(desktop.subprocess, 'run', Mock(return_value=subprocess.CompletedProcess([], 0, stdout='\n', stderr='')))
    assert desktop.pick_folder('open') is None


@pytest.mark.parametrize('error', [FileNotFoundError(), subprocess.CalledProcessError(1, 'picker'), subprocess.TimeoutExpired('picker', 300)])
def test_picker_errors_are_explicit(monkeypatch, error):
    monkeypatch.setattr(desktop, 'file_manager', lambda: 'finder')
    monkeypatch.setattr(desktop.subprocess, 'run', Mock(side_effect=error))
    with pytest.raises(s.AppError) as exc:
        desktop.pick_folder('parent')
    assert exc.value.code == 'FOLDER_PICKER_UNAVAILABLE' and exc.value.status == 503


def test_unsupported_picker_allows_direct_path_fallback(monkeypatch):
    monkeypatch.setattr(desktop, 'file_manager', lambda: None)
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    with pytest.raises(s.AppError) as exc:
        desktop.pick_folder('open')
    assert exc.value.code == 'FOLDER_PICKER_UNSUPPORTED' and exc.value.status == 501
    assert '직접 입력' in exc.value.message
    launch.assert_not_called()


def test_reveal_missing_folder_never_launches_manager(client, monkeypatch):
    project = client.post('/v1/projects', json={'name': '이동된 폴더'}).json()
    folder = Path(project['storage']['path'])
    folder.rename(folder.with_name(folder.name + '-moved'))
    monkeypatch.setattr(desktop, 'file_manager', lambda: 'finder')
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'run', launch)
    r = client.post(f'/v1/projects/{project["projectId"]}/reveal', json={})
    assert r.status_code == 424 and r.json()['code'] == 'PROJECT_FOLDER_MISSING'
    launch.assert_not_called()
    assert not folder.exists()
