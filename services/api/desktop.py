"""User-requested native folder dialogs and file-manager actions on the server host."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from . import store as s


def file_manager():
    return {'darwin': 'finder', 'win32': 'explorer'}.get(sys.platform)


def pick_folder(purpose: Literal['open', 'parent']) -> str | None:
    """Invoked only by the protected POST endpoint, never during discovery/startup."""
    if purpose not in ('open', 'parent'):
        raise s.AppError('FOLDER_PICKER_PURPOSE', '폴더 선택 목적을 확인하세요.')
    manager = file_manager()
    if not manager:
        raise s.AppError('FOLDER_PICKER_UNSUPPORTED', '폴더 선택창은 macOS와 Windows에서 지원합니다. 경로를 직접 입력하세요.', 501)
    prompt = '열 프로젝트 폴더를 선택하세요.' if purpose == 'open' else '새 프로젝트를 저장할 상위 폴더를 선택하세요.'
    if manager == 'finder':
        # Only the fixed prompt enters AppleScript; user paths never become code.
        script = f'''try
    return POSIX path of (choose folder with prompt "{prompt}")
on error number -128
    return ""
end try'''
        command = ['/usr/bin/osascript', '-e', script]
    else:
        script = f'''$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{prompt}'
$dialog.ShowNewFolderButton = ${'true' if purpose == 'parent' else 'false'}
try {{
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
        [Console]::Write($dialog.SelectedPath)
    }}
}} finally {{ $dialog.Dispose() }}'''
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-EncodedCommand', encoded]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', timeout=300)
        selected = result.stdout.rstrip('\r\n')
        if not selected:
            return None
        path = Path(selected)
        if not path.is_absolute() or not path.is_dir():
            raise OSError('Selected folder is unavailable')
        return str(path.resolve())
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise s.AppError('FOLDER_PICKER_UNAVAILABLE', '폴더 선택창을 열지 못했습니다. 경로를 직접 입력하거나 다시 시도하세요.', 503) from exc


def reveal_project(pid: str):
    s.get_project(pid)
    folder = Path(s.project_folder(pid)).resolve()
    manager = file_manager()
    if not manager:
        raise s.AppError('FILE_MANAGER_UNSUPPORTED', '저장 위치 열기는 macOS와 Windows에서 지원합니다.', 501)
    if not folder.is_dir():
        raise s.AppError('PROJECT_FOLDER_MISSING', '프로젝트 폴더가 없습니다. 이동한 폴더를 다시 여세요.', 424)
    try:
        if manager == 'finder':
            subprocess.run(['/usr/bin/open', str(folder)], check=True, capture_output=True, timeout=5)
        else:
            os.startfile(str(folder), 'explore')
    except (OSError, subprocess.SubprocessError) as exc:
        raise s.AppError('FILE_MANAGER_UNAVAILABLE', '저장 폴더를 열지 못했습니다. 파일 관리자 상태를 확인한 뒤 다시 시도하세요.', 503) from exc
    return {'projectId': pid, 'path': str(folder), 'fileManager': manager, 'storageLayout': 'project-folder'}
