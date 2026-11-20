import os,json
from datetime import datetime,timezone
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Metric,Fact,Snapshot,Audit,Cleanup
from src.schemas.business import Login,MetricInput,FactInput,RunInput,NoteInput,CleanupInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.repository import save_metric,save_fact
from src.services.cleanup import retired_classes,snapshot_classes,incomplete_cleanup
from src.controllers import business as ensure
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/metrics')
def metrics(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Metric).order_by(Metric.code,Metric.version).all()]
@router.post('/metrics')
def create_metric(data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data);audit(s,u,'建立口径 '+r.code+' v'+str(r.version));return dump(r)
@router.put('/metrics/{i}')
def edit_metric(i:int,data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data,i);audit(s,u,'修订口径 '+str(i));return dump(r)
@router.get('/facts')
def facts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Fact).order_by(Fact.day.desc(),Fact.class_code).all()]
@router.post('/facts')
def create_fact(data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data);audit(s,u,'录入事实 '+str(r.id));return dump(r)
@router.put('/facts/{i}')
def edit_fact(i:int,data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data,i);audit(s,u,'修订事实 '+str(i));return dump(r)
@router.get('/snapshots')
def snapshots(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Snapshot).order_by(Snapshot.id.desc()).all()]
@router.post('/snapshots')
def run(data:RunInput,u=Depends(editor),s=Depends(db)):
 m=ensure.metric(s,data.metric_id);baseline=None
 if data.baseline_id:
  b=ensure.snapshot(s,data.baseline_id)
  if b.state!='done':raise HTTPException(409,'仅成功快照可作为比较基线')
  if b.result['metric']['code']!=m.code:raise HTTPException(409,'只能比较同一指标代码的口径版本')
  baseline=dict(id=b.id,date_from=b.date_from,date_to=b.date_to,result={k:b.result[k] for k in ['metric','value','facts_checksum']})
 values=data.model_dump(mode='json');retired=retired_classes(s);rows=[dump(f) for f in s.query(Fact).filter(Fact.day>=values['date_from'],Fact.day<=values['date_to']).order_by(Fact.day,Fact.class_code).all() if f.class_code not in retired]
 frozen={'metric':dump(m),'facts':rows,'baseline':baseline,'date_from':values['date_from'],'date_to':values['date_to']}
 r=Snapshot(**values,result={'snapshot':frozen});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('camp:snapshots',r.id)
 except redis.RedisError:r.state='failed';r.error='队列不可用，请恢复后重新试算';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交试算 '+str(r.id));return dump(r)
@router.get('/snapshots/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure.snapshot(s,i))
@router.put('/snapshots/{i}/note')
def note(i:int,data:NoteInput,u=Depends(editor),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可编辑意见')
 r.note=data.note;s.commit();audit(s,u,'起草签核意见 '+str(i));return dump(r)
@router.post('/snapshots/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可签核')
 if incomplete_cleanup(s,r.result):raise HTTPException(409,'涉及班级退场清理未完成，完成前不开放签核')
 if r.result['value'] is None:raise HTTPException(409,'零分母undefined快照不能签核，请修正口径')
 if len(r.note)<8:raise HTTPException(409,'先填写至少8字业务解释')
 m=ensure.metric(s,r.metric_id)
 if any(getattr(m,k)!=v for k,v in r.result['metric'].items() if k not in ['locked']):raise HTTPException(409,'口径在试算后已变更，请用当前版本重新试算再签核')
 r.approval='approved';r.approved_by=u.email;m.locked=True;s.commit();audit(s,u,'签核冻结 '+str(i));return dump(r)
@router.get('/snapshots/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功快照可导出')
 if incomplete_cleanup(s,r.result):raise HTTPException(409,'涉及班级退场清理未完成，完成前不开放下载')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="camp-metric-{i}.json"'})
def push_cleanup(t,s):
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('camp:cleanups',t.id)
 except redis.RedisError:t.state='failed';t.error='队列不可用，请恢复后重试';s.commit();raise HTTPException(503,t.error)
@router.get('/cleanups')
def cleanups(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Cleanup).order_by(Cleanup.id.desc()).all()]
@router.get('/cleanups/preview')
def cleanup_preview(class_code:str,u=Depends(editor),s=Depends(db)):
 existing=s.query(Cleanup).filter_by(class_code=class_code).first()
 affected=[dict(id=r.id,state=r.state,approval=r.approval) for r in s.query(Snapshot).all() if class_code in snapshot_classes(r.result)]
 return dict(class_code=class_code,facts=s.query(Fact).filter(Fact.class_code==class_code).count(),snapshots=affected,existing=dump(existing) if existing else None)
@router.post('/cleanups')
def cleanup_create(data:CleanupInput,u=Depends(admin),s=Depends(db)):
 if s.query(Cleanup).filter_by(class_code=data.class_code).first():raise HTTPException(409,'该班级已存在退场清理任务，请在列表查看进度或重试失败任务')
 affected=[r.id for r in s.query(Snapshot).all() if data.class_code in snapshot_classes(r.result)]
 facts=s.query(Fact).filter(Fact.class_code==data.class_code).count()
 if not facts and not affected:raise HTTPException(404,'未发现该班级的日报或试算副本，无需清理')
 t=Cleanup(class_code=data.class_code,note=data.note,state='queued',facts_total=facts,snapshots_total=len(affected),remaining=affected,created_by=u.email,created=datetime.now(timezone.utc).isoformat())
 s.add(t)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'该班级已存在退场清理任务，请在列表查看进度或重试失败任务')
 push_cleanup(t,s);audit(s,u,'发起班级退场清理 '+t.class_code+' 任务#'+str(t.id));return dump(t)
@router.post('/cleanups/{i}/retry')
def cleanup_retry(i:int,u=Depends(admin),s=Depends(db)):
 t=s.get(Cleanup,i)
 if not t:raise HTTPException(404,'清理任务不存在')
 if t.state!='failed':raise HTTPException(409,'仅失败的清理任务可重试接续；重试不重复扣减')
 t.state='queued';t.error='';s.commit()
 push_cleanup(t,s);audit(s,u,'重试班级退场清理 '+t.class_code+' 任务#'+str(t.id));return dump(t)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
