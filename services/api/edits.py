from __future__ import annotations
import copy, math
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field
from .store import AppError, uid

class Strict(BaseModel): model_config=ConfigDict(extra='forbid')
class SetSettings(Strict):
    type:Literal['setGenerationSettings']; settings:dict
class CreateClip(Strict):
    type:Literal['createClip']; clip:dict
class UpdateClip(Strict):
    type:Literal['updateClip']; clipId:str; changes:dict
class AddOccurrence(Strict):
    type:Literal['addOccurrence']; clipId:str; frameVersionId:str; index:int|None=None
class RemoveOccurrence(Strict):
    type:Literal['removeOccurrence','duplicateOccurrence']; clipId:str; occurrenceId:str
class Reorder(Strict):
    type:Literal['reorderOccurrences']; clipId:str; occurrenceIds:list[str]
class Timing(Strict):
    type:Literal['setTiming']; clipId:str; occurrenceId:str; durationMs:int=Field(ge=1,le=60000,strict=True); timingMode:Literal['fps','explicit']='explicit'
class Transform(Strict):
    type:Literal['setTransform']; clipId:str; occurrenceId:str; transform:dict
class Pixels(Strict):
    type:Literal['setPixelEdits']; clipId:str; occurrenceId:str; pixelEdits:list[dict]=Field(max_length=100000)
class Replace(Strict):
    type:Literal['replaceFrameVersion']; clipId:str; occurrenceId:str; frameVersionId:str
class Review(Strict):
    type:Literal['setFrameReview']; frameVersionId:str; review:Literal['pending','approved','rejected']; hidden:bool|None=None
    reason:str|None=Field(default=None,max_length=2000)
class Group(Strict):
    type:Literal['setAlignmentGroup']; alignmentGroupId:str; changes:dict
class Alignment(Strict):
    type:Literal['setAlignment']; frameVersionId:str; alignment:dict
class Outline(Strict):
    type:Literal['setOutline']; outline:dict
class Character(Strict):
    type:Literal['updateCharacter']; name:str=Field(min_length=1,max_length=200)
Operation=Annotated[Union[SetSettings,CreateClip,UpdateClip,AddOccurrence,RemoveOccurrence,Reorder,Timing,Transform,Pixels,Replace,Review,Group,Alignment,Outline,Character],Field(discriminator='type')]
class EditRequest(Strict):
    expectedRevision:int; operations:list[Operation]=Field(min_length=1,max_length=500)

def find(items,key,value):
    item=next((i for i in items if i.get(key)==value),None)
    if item is None: raise AppError('ENTITY_NOT_FOUND','선택한 항목을 찾을 수 없습니다.',404,{'id':value})
    return item

def fields(d,allowed):
    unknown=set(d)-set(allowed)
    if unknown: raise AppError('UNSUPPORTED_FIELD','지원하지 않는 설정입니다.',422,{'fields':sorted(unknown)})

def number(n,minimum,maximum,name,integer=False):
    if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not minimum<=n<=maximum or (integer and int(n)!=n):
        raise AppError('VALUE_RANGE',f'{name}: {minimum}–{maximum} 범위 값을 입력하세요.')

def point(p,name):
    if not isinstance(p,dict) or set(p)!={'x','y'}: raise AppError('POINT_INVALID',f'{name} 좌표가 필요합니다.')
    for v in p.values(): number(v,-32768,32768,name)

REVIEW_REASONS={
    'addOccurrence':'재생 슬롯이 추가되었습니다.', 'removeOccurrence':'재생 슬롯이 삭제되었습니다.',
    'duplicateOccurrence':'재생 슬롯이 복제되었습니다.', 'reorderOccurrences':'재생 순서가 변경되었습니다.',
    'setTiming':'표시 시간이 변경되었습니다.', 'setTransform':'프레임 변형이 변경되었습니다.',
    'setPixelEdits':'픽셀 편집이 변경되었습니다.', 'replaceFrameVersion':'사용 프레임이 교체되었습니다.',
    'setAlignment':'앵커 설정이 변경되었습니다.', 'setAlignmentGroup':'정렬 그룹 설정이 변경되었습니다.',
    'setFrameReview':'사용 프레임의 수동 승인 상태가 변경되었습니다.', 'setOutline':'테두리 설정이 변경되었습니다.',
    'updateClip':'동작 설정이 변경되었습니다.',
}

def invalidate_review(entity,key,reason,was_approved=None):
    if (was_approved if was_approved is not None else entity.get(key)=='approved'):
        entity['reviewInvalidatedReason']=reason
    entity[key]='pending'

def apply(p,ops):
    p=copy.deepcopy(p)
    for obj in ops:
        op=obj.model_dump(exclude_none=True) if hasattr(obj,'model_dump') else obj
        t=op['type']; clip=None
        if 'clipId' in op: clip=find(p['clips'],'clipId',op['clipId'])
        if 'occurrenceId' in op: occ=find(clip['occurrences'],'occurrenceId',op['occurrenceId'])
        clip_was_approved=clip is not None and clip.get('review')=='approved'
        if t=='setGenerationSettings':
            fields(op['settings'],['providerId','model','prompt','frameCount','quality','resolution','scope','frameVersionId','clipId','background'])
            p['generationSettings']=op['settings']
        elif t=='createClip':
            d=op['clip']; fields(d,['name','stateId','facing','referenceRevisionId','loop','defaultFps'])
            fps=d.get('defaultFps',10); number(fps,1,60,'FPS',True)
            cid=uid(); p['clips'].append(dict(clipId=cid,clipRevisionId=uid(),name=d.get('name','새 동작'),stateId=d.get('stateId',cid),facing=d.get('facing','right'),referenceRevisionId=d.get('referenceRevisionId',p['activeReferenceRevisionId']),loop=d.get('loop',True),endBehavior='hold-last',defaultFps=fps,occurrences=[],review='pending'))
        elif t=='updateClip':
            d=op['changes']; fields(d,['name','loop','defaultFps','facing','referenceRevisionId','review'])
            if 'review' in d and d['review'] not in ('approved','pending'): raise AppError('REVIEW_INVALID','검수 상태가 잘못되었습니다.')
            if 'referenceRevisionId' in d:
                find(p['references'],'referenceRevisionId',d['referenceRevisionId'])
            if 'defaultFps' in d:
                number(d['defaultFps'],1,60,'FPS',True)
                for o in clip['occurrences']:
                    if o['timingMode']=='fps': o['durationMs']=math.floor(1000/d['defaultFps']+.5)
            clip.update(d)
        elif t=='addOccurrence':
            f=find(p['frames'],'frameVersionId',op['frameVersionId'])
            o=dict(occurrenceId=uid(),frameVersionId=f['frameVersionId'],durationMs=math.floor(1000/clip['defaultFps']+.5),timingMode='fps',transform={'dx':0,'dy':0,'scaleX':1,'scaleY':1,'rotationDeg':0,'shearX':0,'shearY':0,'flipX':False,'flipY':False},pixelEdits=[])
            clip['occurrences'].insert(op.get('index',len(clip['occurrences'])),o)
        elif t=='removeOccurrence': clip['occurrences'].remove(occ)
        elif t=='duplicateOccurrence':
            clone=copy.deepcopy(occ); clone['occurrenceId']=uid(); clip['occurrences'].insert(clip['occurrences'].index(occ)+1,clone)
        elif t=='reorderOccurrences':
            ids=op['occurrenceIds']
            if len(ids)!=len(set(ids)) or set(ids)!={o['occurrenceId'] for o in clip['occurrences']}: raise AppError('ORDER_INVALID','모든 재생 슬롯을 중복 없이 지정하세요.')
            clip['occurrences']=[find(clip['occurrences'],'occurrenceId',i) for i in ids]
        elif t=='setTiming':
            occ.update(durationMs=op['durationMs'],timingMode=op['timingMode'])
            if op['timingMode']=='fps': occ['durationMs']=math.floor(1000/clip['defaultFps']+.5)
        elif t=='setTransform':
            d=op['transform']; fields(d,['dx','dy','scaleX','scaleY','rotationDeg','shearX','shearY','flipX','flipY','pivot'])
            for k,v in d.items():
                if k in ('flipX','flipY'):
                    if type(v) is not bool: raise AppError('TRANSFORM_INVALID','반전 값은 boolean입니다.')
                elif k=='pivot': point(v,k)
                elif k in ('scaleX','scaleY'): number(v,.05,8,k)
                else: number(v,-8192,8192,k)
            occ['transform'].update(d)
        elif t=='setPixelEdits':
            for e in op['pixelEdits']:
                fields(e,['x','y','color']); number(e.get('x'),0,8191,'픽셀 x',True); number(e.get('y'),0,8191,'픽셀 y',True)
                if not isinstance(e.get('color'),list) or len(e['color'])!=4: raise AppError('COLOR_INVALID','RGBA 색이 필요합니다.')
                for v in e['color']: number(v,0,255,'색',True)
            occ['pixelEdits']=op['pixelEdits']; occ['pixelEditRevision']=uid()
        elif t=='replaceFrameVersion':
            find(p['frames'],'frameVersionId',op['frameVersionId']); occ.update(frameVersionId=op['frameVersionId'],pixelEdits=[],transform={'dx':0,'dy':0,'scaleX':1,'scaleY':1,'rotationDeg':0,'flipX':False,'flipY':False})
        elif t=='setFrameReview':
            f=find(p['frames'],'frameVersionId',op['frameVersionId']); f['review']=op['review']
            if op['review']=='rejected' and not (op.get('reason') or f.get('reviewReason','')).strip():
                raise AppError('REVIEW_REASON_REQUIRED','검수에서 제외한 이유를 입력하세요.')
            if op.get('reason') is not None: f['reviewReason']=op['reason'].strip()
            f['reviewReferenceRevisionId']=p.get('activeReferenceRevisionId')
            if 'hidden' in op: f['hidden']=op['hidden']
        elif t=='setAlignmentGroup':
            g=find(p['alignmentGroups'],'alignmentGroupId',op['alignmentGroupId']); d=op['changes']
            fields(d,['sharedScale','cell','targetAnchor','mode','bodyMeasurement'])
            if 'sharedScale' in d: number(d['sharedScale'],.01,8,'공통 배율')
            if 'cell' in d:
                fields(d['cell'],['width','height','edge'])
                for k in ('width','height'): number(d['cell'].get(k),1,4096,'셀 크기',True)
                number(d['cell'].get('edge',0),0,min(d['cell']['width'],d['cell']['height'])//2,'여백',True)
            if 'targetAnchor' in d: point(d['targetAnchor'],'목표 앵커')
            if d.get('mode') not in (None,'preserve-source-scale','shared-scale-foot-anchor'): raise AppError('ALIGNMENT_MODE','지원하지 않는 정렬 모드입니다.')
            if d.get('mode',g['mode'])=='shared-scale-foot-anchor':
                m=d.get('bodyMeasurement',g.get('bodyMeasurement'))
                if not m or not m.get('approved') or m.get('bottomY',0)<=m.get('topY',0): raise AppError('BODY_MEASUREMENT','승인된 몸 기준점이 필요합니다.')
                number(m.get('targetHeight'),1,8192,'목표 몸 체고'); d['sharedScale']=m['targetHeight']/(m['bottomY']-m['topY'])
                number(d['sharedScale'],.01,8,'공통 배율')
            g.update(d); g['groupRevisionId']=uid()
            for fid in g['frameVersionIds']:
                if fid in p['alignments']:
                    invalidate_review(p['alignments'][fid],'approval',REVIEW_REASONS[t])
                    p['alignments'][fid]['groupRevisionId']=g['groupRevisionId']
        elif t=='setAlignment':
            fid=op['frameVersionId']; find(p['frames'],'frameVersionId',fid); a=dict(op['alignment'])
            fields(a,['sourceAnchor','anchorSpace','method','contactMode','rootAnchor','authoredOffsetPx','approval','frameVersionId','groupRevisionId','reviewInvalidatedReason'])
            # UI sends the full object; this diagnostic is server-owned.
            a.pop('reviewInvalidatedReason',None)
            for k in ('sourceAnchor','rootAnchor','authoredOffsetPx'):
                if k in a: point(a[k],k)
            if a.get('anchorSpace','crop')!='crop': raise AppError('ANCHOR_SPACE','현재 편집은 crop 좌표를 사용합니다.')
            for k,allowed in [('method',['automatic','manual']),('contactMode',['grounded','airborne']),('approval',['pending','approved'])]:
                if k in a and a[k] not in allowed: raise AppError('ANCHOR_INVALID','앵커 설정이 잘못되었습니다.')
            current=p['alignments'].get(fid,{})
            was_approved=current.get('approval')=='approved'
            changed=any(current.get(k)!=v for k,v in a.items() if k not in ('approval','frameVersionId','groupRevisionId'))
            current.update(a)
            # A copied approved flag must not approve changed coordinates. A later
            # approval of these same coordinates (including a full object) is explicit.
            if was_approved and (changed or a.get('approval')=='pending'):
                invalidate_review(current,'approval',REVIEW_REASONS[t],True)
            elif a.get('approval')=='approved': current.pop('reviewInvalidatedReason',None)
            group=next((g for g in p['alignmentGroups'] if fid in g['frameVersionIds']),None)
            if not group: raise AppError('GROUP_MISSING','정렬 그룹이 없습니다.')
            current.update(frameVersionId=fid,groupRevisionId=group['groupRevisionId']); p['alignments'][fid]=current
            if current.get('contactMode')=='airborne' and current.get('approval')=='approved' and not current.get('rootAnchor'): raise AppError('ROOT_ANCHOR_REQUIRED','공중 자세의 root 앵커를 지정하세요.')
        elif t=='setOutline':
            d=op['outline']; fields(d,['enabled','mode','teamLabel','colorRGBA','thicknessPx','directions','opacityPerCopy','rendererVersion'])
            if d.get('mode',p['outline']['mode']) not in ('preview-only','bake'): raise AppError('OUTLINE_MODE','아웃라인 모드가 잘못되었습니다.')
            if 'thicknessPx' in d: number(d['thicknessPx'],1,16,'테두리 두께',True)
            if 'opacityPerCopy' in d: number(d['opacityPerCopy'],0,1,'불투명도')
            if d.get('directions',8) not in (4,8): raise AppError('OUTLINE_DIRECTIONS','4방향 또는 8방향을 선택하세요.')
            if 'colorRGBA' in d:
                if len(d['colorRGBA'])!=4: raise AppError('COLOR_INVALID','RGBA 색이 필요합니다.')
                for v in d['colorRGBA']: number(v,0,255,'색',True)
            p['outline'].update(d)
        elif t=='updateCharacter': p['characterName']=op['name']
        if clip is not None:
            clip['clipRevisionId']=uid()
            if t=='updateClip' and set(op['changes'])=={'review'}:
                if clip['review']=='approved': clip.pop('reviewInvalidatedReason',None)
                elif clip_was_approved: invalidate_review(clip,'review','동작 승인이 해제되었습니다.',True)
            else:
                reason='연결된 기준이 변경되었습니다.' if t=='updateClip' and 'referenceRevisionId' in op['changes'] else REVIEW_REASONS.get(t,'동작 설정이 변경되었습니다.')
                invalidate_review(clip,'review',reason,clip_was_approved)
        if t in ('setAlignment','setAlignmentGroup','setFrameReview','setOutline'):
            affected=set(g['frameVersionIds']) if t=='setAlignmentGroup' else {op.get('frameVersionId')}
            for cl in p['clips']:
                if t=='setOutline' or any(o['frameVersionId'] in affected for o in cl['occurrences']):
                    cl['clipRevisionId']=uid(); invalidate_review(cl,'review',REVIEW_REASONS[t])
    return p
