"""Project-owned, disposable RIFE cache; accepted frames are copied into job outputs."""
from pathlib import Path
import hashlib
import time
import tempfile

from . import video_processing as vp

BUDGET_SECONDS = 60
MAX_PIXELS = 2_000_000


class Session:
    def __init__(self, project_root: Path, check=lambda: None, *, budget=BUDGET_SECONDS, tta=()):
        if Path(project_root).is_symlink():
            raise vp.VideoProcessingError('VIDEO_CACHE_PATH', '프로젝트 캐시 경로에 심볼릭 링크를 사용할 수 없습니다.')
        self.root = Path(project_root).resolve()
        self.directory = self.root / '.cache' / 'rife-m2'
        self.check, self.budget = check, budget
        self.tta = tta
        self.deadline = None
        self.located = self.cache = None
        self.elapsed = 0.0
        self.calls = 0

    def _check(self):
        self.check()
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise vp._engine('video.rife').RifeUnavailable('RIFE job time budget exhausted')
        for path in (self.root / '.cache', self.directory):
            if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                raise vp.VideoProcessingError('VIDEO_CACHE_PATH', '프로젝트 캐시 경로에 심볼릭 링크를 사용할 수 없습니다.')

    def __call__(self, a, b, t):
        self._check()
        rife = vp._engine('video.rife')
        if a.width * a.height > MAX_PIXELS:
            raise rife.RifeUnavailable('RIFE input exceeds the local pixel budget')
        if self.deadline is None:
            self.deadline = time.monotonic() + self.budget
        if self.cache is None:
            try:
                self.cache = rife.Cache(self.directory, check=self._check)
            except OSError:
                self.cache = False
        started = time.monotonic()
        token = rife.RUN_CONTROL.set((self.deadline, self._check))
        augmentation = rife.TTA_OVERRIDE.set(self.tta)
        try:
            if self.located is None:
                self.located = vp.rife_interpolator()
            # Stand-ins without identity are deliberately not persisted.
            result = (self.cache.frame(self.located, a, b, t) if self.cache and hasattr(self.located, 'identity')
                      else self.located(a, b, t))
            self._check()
            self.calls += 1
            return result
        finally:
            self.elapsed += time.monotonic() - started
            rife.RUN_CONTROL.reset(token)
            rife.TTA_OVERRIDE.reset(augmentation)

    def start(self):
        if self.deadline is None:
            self.deadline = time.monotonic() + self.budget
        self._check()

    def read(self, a, b, t):
        frame = self(a, b, t)
        rife = vp._engine('video.rife')
        token = rife.RUN_CONTROL.set((self.deadline, self._check))
        augmentation = rife.TTA_OVERRIDE.set(self.tta)
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix='frame-room-rife-passes-') as td:
                apart = rife.passes(a, b, t, binary=self.located.binary, model=self.located.model, tmp=Path(td))
            self.located.calls += rife.PASS_CALLS
            self._check()
            return frame, apart
        finally:
            self.elapsed += time.monotonic() - started
            rife.RUN_CONTROL.reset(token)
            rife.TTA_OVERRIDE.reset(augmentation)

    def describe(self):
        record = {'budgetSeconds': self.budget, 'elapsedSeconds': round(self.elapsed, 4), 'requests': self.calls,
                  'binaryCalls': getattr(self.located, 'calls', 0), 'localOnly': True,
                  'cacheUnavailable': self.cache is False,
                  'cache': {k: v for k, v in self.cache.record().items() if k != 'dir'} if self.cache else {'hits': 0, 'misses': 0}}
        if self.located:
            record.update(self.located.describe())
            if hasattr(self.located, 'identity'):
                rife = vp._engine('video.rife')
                token = rife.TTA_OVERRIDE.set(self.tta)
                try:
                    identity = self.located.identity()
                    record['identitySha256'] = hashlib.sha256(identity.encode()).hexdigest()
                    import json
                    parts = json.loads(identity) if identity.startswith('{') else {}
                    record.update({k: parts[v] for k, v in {'binarySha256': 'binary', 'modelFilesSha256': 'model_files', 'preprocessingSha256': 'code'}.items() if v in parts})
                finally:
                    rife.TTA_OVERRIDE.reset(token)
        # Paths identify machine locations, not portable lineage.
        record.pop('binary', None)
        return record
