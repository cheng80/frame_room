"""Worker integration with synthetic PNGs and a mocked provider; no external calls."""
import copy
import io
import json
from unittest.mock import Mock

import pytest
from PIL import Image

from adapters.spritegen import provider
from services.api import store as s
from services.api.main import enqueue
from services.worker.main import publish
from services.worker.task import execute


@pytest.mark.parametrize('active_reference',[False,True])
@pytest.mark.parametrize('reuse',[None,'same-attempt','new-attempt'])
def test_asset_worker_preserves_original_provenance_and_checkpoint(tmp_path,monkeypatch,active_reference,reuse):
    monkeypatch.setattr(s,'DATA',tmp_path/'data');s.init()
    p=s.create_project('자료 생성 격리 시험','캐릭터')
    if active_reference:
        with s.transaction() as db:
            p=s.get_project(p['projectId'],db)
            p['references']=[{'referenceRevisionId':'existing-ref','approval':'approved','identityAssetId':'unused'}]
            p['activeReferenceRevisionId']='existing-ref'
            s.write_project(db,p,'existing reference fixture')
        p=s.get_project(p['projectId'])
    params={'scope':'asset','providerId':'codex','frameCount':1,'prompt':'  첫 원본 자료\n원문 보존  '}
    request={'operation':'generate','inputRevision':p['revision'],'assetIds':[],'params':params}
    queued=enqueue(p['projectId'],'generate',request,s.uid(),p['revision'])
    j=s.get_job(queued['jobId']);original_job=copy.deepcopy(j)
    out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
    image=io.BytesIO();Image.new('RGBA',(8,12),(30,80,120,128)).save(image,format='PNG')
    original=image.getvalue()
    request_snapshot={'params':copy.deepcopy(params),'reference':{},'references':[],'enginePrompt':params['prompt']}
    receipt={'testFixture':True,'sha256':s.digest(original)}

    def generated(given_params,reference,asset_path,out_dir):
        assert given_params==params and reference=={}
        assert asset_path is s.asset_path and out_dir==out
        path=out_dir/'synthetic-provider-fixture.png';path.write_bytes(original)
        return {'paths':[str(path)],'providerId':'codex','model':provider.DEFAULT_MODEL,
                'requestSnapshot':copy.deepcopy(request_snapshot),'receipt':receipt}

    generate=Mock(side_effect=generated);monkeypatch.setattr(provider,'generate',generate)
    result=execute(j,out)
    assert j==original_job
    checkpoint=json.loads((out.parent/'provider-completed.json').read_text())
    assert checkpoint['requestHash']==j['requestHash']
    assert checkpoint['providerResult']['requestSnapshot']==request_snapshot
    if reuse:
        if reuse=='new-attempt':
            j={**j,'reuseProviderAttemptId':j['attemptId'],'attemptId':s.uid()}
            out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
            with s.transaction() as db: s.write_job(db,j)
        result=execute(j,out)
    assert generate.call_count==1
    assert set(result)=={'assets','generations','files','status','receipt'}
    assert result['files']==[] and result['status']=='needs_review'
    assert len(result['assets'])==len(result['generations'])==1
    asset=result['assets'][0];generation=result['generations'][0]
    assert asset['role']=='source'
    assert asset['provenance']=={
        'kind':'real-provider','providerId':'codex','generationVersionId':generation['generationVersionId'],
        'referenceRevisionId':None}
    assert generation['scope']=='asset' and generation['referenceRevisionId'] is None
    assert generation['parentFrameVersionId'] is None
    assert generation['rawAssetIds']==[asset['assetId']]
    assert generation['requestedFrameCount']==generation['returnedImageCount']==1
    assert generation['requestSnapshot']==request_snapshot and generation['receipt']==receipt
    assert generation['promptHash']==s.digest(params['prompt'].encode())
    assert s.asset_path(asset['assetId']).read_bytes()==original
    publish(j,{'ok':True,'result':result})
    saved=s.get_project(p['projectId'])
    assert saved['assets']==[asset] and saved['generations']==[generation]
    for key in ('references','activeReferenceRevisionId','frames','clips','alignmentGroups','alignments','generationSettings'):
        assert saved[key]==p[key]
    assert s.get_job(j['jobId'])['status']=='needs_review'
    assert s.get_job(j['jobId'])['request']==request
