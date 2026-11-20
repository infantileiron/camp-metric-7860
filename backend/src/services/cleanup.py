import copy,json
from datetime import datetime,timezone
from pathlib import Path
from src.models.entities import Fact,Snapshot,Cleanup
NOTE='合作班级已退场停办，其原始记录与班级标识已按退场清理任务清除；分子、分母与比值保留冻结历史值，可用于解释历史签核。'
def stamp():return datetime.now(timezone.utc).isoformat()
def retired_classes(s):
 """已发起退场清理（含排队/进行/失败/完成）的班级，一律不再纳入新试算与录入。"""
 return {c.class_code for c in s.query(Cleanup).all()}
def snapshot_classes(result):
 """快照副本中仍出现的班级标识：冻结事实行与按班分组。"""
 classes=set()
 if result:
  frozen=result.get('snapshot') or {}
  classes|={f.get('class_code') for f in frozen.get('facts') or []}
  classes|={g.get('class_code') for g in result.get('groups') or []}
 classes.discard(None)
 return classes
def incomplete_cleanup(s,result):
 """命中未完成清理任务的快照属于残缺快照，完成前不开放签核与下载。"""
 classes=snapshot_classes(result)
 if not classes:return None
 return s.query(Cleanup).filter(Cleanup.class_code.in_(classes),Cleanup.state!='done').first()
def scrub_snapshot(result,class_code,task_id,at):
 """清除单个副本中该班的原始记录与班级标识；保留历史分子分母与比值并附清理说明。幂等：已清除副本不重复扣减。"""
 removed=0;changed=False
 frozen=result.get('snapshot')
 if frozen and frozen.get('facts'):
  kept=[f for f in frozen['facts'] if f.get('class_code')!=class_code]
  if len(kept)!=len(frozen['facts']):removed+=len(frozen['facts'])-len(kept);frozen['facts']=kept;changed=True
 if result.get('groups'):
  kept=[g for g in result['groups'] if g.get('class_code')!=class_code]
  if len(kept)!=len(result['groups']):removed+=len(result['groups'])-len(kept);result['groups']=kept;changed=True
 if changed:result['cleanup']=dict(task=task_id,removed_rows=removed,at=at,note=NOTE)
 return changed,removed
def run_cleanup(s,task_id):
 """由待处理进入完成；遇中断可接续恢复，反复重试不重复扣减。逐副本单事务提交，完成前不开放残缺快照。"""
 t=s.get(Cleanup,task_id)
 if not t or t.state!='queued':return
 at=stamp();t.state='running'
 remaining=[r.id for r in s.query(Snapshot).all() if t.class_code in snapshot_classes(r.result)]
 t.remaining=remaining;t.snapshots_total=t.snapshots_done+len(remaining)
 t.facts_total=t.facts_removed+s.query(Fact).filter(Fact.class_code==t.class_code).count()
 s.commit()
 try:
  for sid in list(remaining):
   row=s.get(Snapshot,sid)
   if row and row.result:
    result=copy.deepcopy(row.result);changed,removed=scrub_snapshot(result,t.class_code,t.id,at)
    if changed:row.result=result;t.records_removed+=removed
    p=Path('/artifacts/'+str(sid)+'.json')
    if p.exists():p.write_text(json.dumps(row.result,ensure_ascii=False))
   t.snapshots_done+=1;t.remaining=[x for x in t.remaining if x!=sid];s.commit()
  t.facts_removed+=s.query(Fact).filter(Fact.class_code==t.class_code).delete(synchronize_session=False)
  t.state='done';t.finished=stamp();s.commit()
 except Exception as e:
  s.rollback();t=s.get(Cleanup,task_id)
  t.state='failed';t.error='清理中断：'+str(e)+'；未清除副本 '+('、'.join('#'+str(x) for x in t.remaining) or '无')
  s.commit()
