"""Replay preserved real clips through the upgraded product; never generate or write user DBs."""
from pathlib import Path
import json, os, sys, tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from frame_room import run_variant, protected_manifest, install_guard, sha, write_json


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['SPRITE_DATA_DIR'] = str(out)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    (out / 'tmp').mkdir();tempfile.tempdir = str(out / 'tmp')
    before = protected_manifest();write_json(out / 'protected-before.json', before)
    install_guard(out)
    source = ROOT / '.data/experiments'
    cases = [
        ('knight-original', source / 'grok-walk-probe-20261004/walk.mp4', source / 'grok-walk-probe-20261004/input-canvas.png', 64, 'side'),
        ('knight-new', source / 'skill-ab-20261006/new/video/original.mp4', source / 'skill-ab-20261006/new/video/input-canvas.png', 64, 'side'),
        ('gunner', source / 'skill-ab-gunner-20261006/video/original.mp4', source / 'skill-ab-gunner-20261006/video/input-canvas.png', 96, 'front_diagonal'),
    ]
    results = {};sources = []
    for name, clip, reference, width, direction in cases:
        case = out / name;case.mkdir()
        sources.extend([(clip, sha(clip)), (reference, sha(reference))])
        base = dict(state='walk', direction=direction, facing='right', key='magenta', bodyHeight=94,
                    cellWidth=width, cellHeight=128, loopMode='auto', referencePath=str(reference), finishMode='gif', repairMode='off')
        results[name] = run_variant('walk-8', base, clip, case)
        # Also exercise real RIFE reject decisions on the preserved dense gunner cycle.
        if name == 'gunner':
            results['gunner-aligned32'] = run_variant('aligned-32', {**base, 'targetFrameCount':32}, clip, case)
            results['gunner-rgba'] = run_variant('rgba-8', {**base, 'finishMode':'rgba'}, clip, case)
    after = protected_manifest()
    unchanged = before['sha256'] == after['sha256'] and all(sha(p) == digest for p,digest in sources)
    approval_codes = {'FRAME_UNAPPROVED', 'ANCHOR_UNAPPROVED'}
    success = unchanged and all(r['status']=='completed' and not (set(r['qaErrors']) - approval_codes) for r in results.values())
    report = {'status':'passed' if success else 'failed', 'externalGenerationCalls':0, 'userDataUnchanged':unchanged,
              'protectedFileCount':before['fileCount'], 'productionApproved':False, 'expectedPendingApprovalCodes':sorted(approval_codes), 'cases':results}
    write_json(out / 'report.json', report)
    print(json.dumps({'status':report['status'],'userDataUnchanged':unchanged,'cases':{k:{'status':r['status'],'frames':r.get('frameCount'),'durationMs':r.get('durationMs'),'qaErrors':r.get('qaErrors')} for k,r in results.items()}},ensure_ascii=False))
    return 0 if success else 1

if __name__ == '__main__': raise SystemExit(main())
