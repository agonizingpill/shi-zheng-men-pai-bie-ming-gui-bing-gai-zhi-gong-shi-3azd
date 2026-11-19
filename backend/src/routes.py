import os,redis
from fastapi import APIRouter,Depends
from .database import Session
from .models import *
from .schemas import *
from .security import current,allow
from .common import *
from . import entrance_service as entrance,proposal_service as proposal,publication_service as publication,directory_service as directory,batch_service as batch
router=APIRouter()
def change(u,action,fn,supervisor=False):
 allow(u,*(['supervisor'] if supervisor else ['operator','supervisor']))
 with Session() as s:
  x=fn(s);log(s,u,action,dump(x));s.commit();return dump(x)
@router.get('/register')
def register(u=Depends(current)):
 from .correction import correction_map,batch_summaries
 with Session() as s:
  payload={name:[dump(x) for x in rows(s,cls)] for name,cls in [('entrances',Entrance),('aliases',Alias),('evidence',Evidence),('runs',MatchRun),('candidates',Candidate),('proposals',Proposal),('objections',Objection),('notices',Notice),('redirects',Redirect),('batches',Batch),('controls',Control),('clock',Registry)]}
  payload['batch_summaries']=batch_summaries(s)
  payload['corrections']=list(correction_map(s).values())
  current=int(getattr(s.get(Registry,1),'correction_version',0) or 0)
  payload['correction_version']=current
  payload['current_run_id']=next((r.id for r in reversed(rows(s,MatchRun)) if r.state=='ready' and int(r.correction_version or 0)==current),None)
  return payload
@router.get('/audit')
def audit(u=Depends(current)):
 with Session() as s:return [dump(x) for x in rows(s,Audit)]
@router.get('/corrections/preview')
def correction_preview(u=Depends(current)):
 with Session() as s:return batch.preview(s)
@router.post('/batches')
def bcreate(d:BatchIn,u=Depends(current)):return change(u,'登记采点批次',lambda s:batch.create_batch(s,d.model_dump()))
@router.post('/batches/assign')
def bassign(d:BatchAssignIn,u=Depends(current)):return change(u,'登记入口采点批次',lambda s:batch.assign_batch(s,d.entrance_id,d.batch_id))
@router.post('/controls')
def ccreate(d:ControlIn,u=Depends(current)):return change(u,'登记复测对照',lambda s:batch.upsert_control(s,d.model_dump()))
@router.delete('/controls/{id}')
def cremove(id:int,u=Depends(current)):return change(u,'删除复测对照',lambda s:batch.remove_control(s,id),True)
@router.post('/entrances')
def ecreate(d:EntranceIn,u=Depends(current)):return change(u,'登记入口',lambda s:entrance.create_entrance(s,d.model_dump()))
@router.patch('/entrances/{id}/location')
def locate(id:int,d:LocationIn,u=Depends(current)):return change(u,'补正坐标',lambda s:entrance.locate(s,id,d.model_dump()))
@router.post('/aliases')
def aliases(d:AliasIn,u=Depends(current)):return change(u,'登记别名',lambda s:entrance.alias(s,d.model_dump()))
@router.post('/evidence')
def evidence(d:EvidenceIn,u=Depends(current)):return change(u,'登记证据',lambda s:entrance.evidence(s,d.model_dump()))
@router.post('/matches')
def matching(u=Depends(current)):
 def create(s):
  r=lock(s);x=MatchRun(state='queued',correction_version=int(r.correction_version or 0));s.add(x);s.flush();return x
 d=change(u,'匹配别名',create)
 try:redis.from_url(os.environ['REDIS_URL']).rpush('address:matching',d['id'])
 except Exception:
  with Session() as s:x=s.get(MatchRun,d['id']);x.state='failed';x.error='匹配队列不可达，可重新提交';s.commit()
  fail('匹配队列不可达，可重新提交')
 return d
@router.post('/proposals')
def pcreate(d:ProposalIn,u=Depends(current)):return change(u,'归并提案',lambda s:proposal.create(s,d.model_dump()))
@router.post('/objections')
def ocreate(d:ObjectionIn,u=Depends(current)):return change(u,'登记异议',lambda s:proposal.object_to(s,d.model_dump()))
@router.post('/objections/{id}/resolve')
def oresolve(id:int,d:ResolveIn,u=Depends(current)):return change(u,'复核异议',lambda s:proposal.resolve(s,id,d.model_dump()),True)
@router.post('/notices')
def ncreate(d:NoticeIn,u=Depends(current)):return change(u,'发布公示',lambda s:publication.publish(s,d.model_dump()),True)
@router.post('/notices/{id}/effective')
def neffect(id:int,u=Depends(current)):return change(u,'公示生效',lambda s:publication.effective(s,id),True)
@router.post('/clock')
def clock(d:ClockIn,u=Depends(current)):return change(u,'推进演示时钟',lambda s:publication.advance(s,d.model_dump()),True)
@router.get('/directory/{id}')
def lookup(id:int,u=Depends(current)):
 with Session() as s:return directory.resolve_root(s,id)
@router.post('/redirects/{id}/rollback')
def rollback(id:int,d:ReasonIn,u=Depends(current)):return change(u,'回滚目录',lambda s:directory.rollback(s,id,d.model_dump()),True)
