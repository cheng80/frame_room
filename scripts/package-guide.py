"""Package the generated static HTML handbook without runtime project data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import shutil

root = Path(__file__).resolve().parents[1]
base = root / 'apps/web/public/guide'
archive = base / 'frame-room-guide.zip'
required = ['index.html', 'manual.html', 'guide.css', 'guide.js', 'media/atlas.png']
for name in required:
    if not (base / name).is_file():
        raise SystemExit(f'Missing guide file: {name}. Run npm --prefix apps/web run guide:build first.')
files = [base / name for name in ['index.html', 'manual.html', 'guide.css', 'guide.js']]
files += sorted((base / 'screens').glob('*.png'))
files += [base / 'media/atlas.png', base / 'media/reference.png']
files += sorted((base / 'media').glob('clip-follow-*'))
files += [base / 'media/clip-tools-source.json']
with ZipFile(archive, 'w', ZIP_DEFLATED) as out:
    for path in files:
        # An offline copy does not offer a link to download itself.
        if path.suffix == '.html':
            text = path.read_text().replace('<a href="frame-room-guide.zip" download>HTML 설명서 내려받기 ↓</a>', '')
            out.writestr(path.relative_to(base).as_posix(), text)
        else:
            out.write(path, path.relative_to(base))
    out.writestr('읽어주세요.txt', 'index.html: 퀵스타트\nmanual.html: 상세 설명서\n\n폴더 전체를 유지한 채 HTML을 브라우저로 여세요. 외부 폰트·CDN·로그인은 필요하지 않습니다.\n설명서의 재생·시간 조절은 실제 프로젝트를 변경하지 않습니다. 에디터 열기는 로컬 앱(127.0.0.1:8765)이 실행 중일 때 사용할 수 있습니다.\n')
with ZipFile(archive) as check:
    assert check.testzip() is None
if (root / 'apps/web/dist/guide').exists():
    shutil.copyfile(archive, root / 'apps/web/dist/guide/frame-room-guide.zip')
print(f'{len(files)} files packaged: {archive} ({archive.stat().st_size:,} bytes)')
