"""The same approval transitions are exercised by Python and the frontend draft."""
import copy
import json
from pathlib import Path

import pytest
from services.api.edits import apply

CASES=json.loads((Path(__file__).parents[1]/'fixtures/review-transitions.json').read_text())

def review_state(p):
    return {
        'clips':[{k:v for k,v in c.items() if k in ('clipId','review','reviewInvalidatedReason')} for c in p['clips']],
        'alignments':{fid:{k:v for k,v in a.items() if k in ('approval','reviewInvalidatedReason')} for fid,a in p['alignments'].items()},
    }

@pytest.mark.parametrize('case',CASES['cases'],ids=lambda c:c['name'])
def test_review_transition(case):
    p=copy.deepcopy(CASES['snapshot'])
    for c in p['clips']:
        if case.get('initialPending'): c['review']='pending'
    if case.get('initialPending'): p['alignments']['f']['approval']='pending'
    before=copy.deepcopy(p)
    result=apply(p,case['operations'])
    assert review_state(result)==case['expected']
    assert p==before


def test_partial_transform_and_fps_timing_match_draft():
    result=apply(CASES['snapshot'],[
        {'type':'setTransform','clipId':'c','occurrenceId':'o','transform':{'dx':3}},
        {'type':'setTiming','clipId':'c','occurrenceId':'o','durationMs':9,'timingMode':'fps'},
        {'type':'setOutline','outline':{'enabled':True}},
    ])
    occurrence=result['clips'][0]['occurrences'][0]
    assert occurrence['transform']['dx']==3
    assert occurrence['transform']['scaleX']==1
    assert occurrence['durationMs']==100
    assert result['outline']['mode']=='preview-only'

@pytest.mark.parametrize('payload,expected',[
    ({'params':{'clipIds':['c','c','missing']}},['c','missing']),
    ({'params':{'clipIds':[]}},[]),
    ({'params':{'clipIds':['c',None,1,{}]}},['c']),
    ({'params':{'clipIds':'c'}},[]),
    ({'clipRevisionIds':['c-rev']},['c']),
    ({'params':{'clipRevisionIds':['unrelated-rev']}},['unrelated']),
    ({'clipRevisionIds':['old-rev']},[]),
    ({'clipRevisionIds':[]},[]),
    ({},['c','unrelated']),
])
def test_public_inspection_scope_is_derived_without_mutating_history(payload,expected):
    from services.api.store import public_job
    job={'operation':'inspect','status':'failed','request':payload,'snapshot':CASES['snapshot']}
    before=copy.deepcopy(job)
    public=public_job(job)
    assert public['inspectionClipIds']==expected
    assert 'snapshot' not in public and 'request' not in public
    assert job==before


def test_non_inspection_jobs_do_not_expose_scope():
    from services.api.store import public_job
    assert 'inspectionClipIds' not in public_job({'operation':'generate','request':{},'snapshot':CASES['snapshot']})
