import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Snapshot,Cleanup
from src.services.analysis import calculate
from src.services.cleanup import run_cleanup,retired_classes
r=redis.Redis.from_url(os.environ['REDIS_URL'])
with Session() as recovery:
 for pending in recovery.query(Snapshot).filter(Snapshot.state.in_(['queued','running'])).all():
  pending.state='queued';r.rpush('camp:snapshots',pending.id)
 for pending in recovery.query(Cleanup).filter(Cleanup.state.in_(['queued','running'])).all():
  pending.state='queued';r.rpush('camp:cleanups',pending.id)
 recovery.commit()
def trial(s,i):
 row=s.get(Snapshot,i)
 if not row or row.state!='queued':return
 snapshot=row.result['snapshot'];retired=retired_classes(s)
 if retired:snapshot={**snapshot,'facts':[f for f in snapshot['facts'] if f['class_code'] not in retired]}
 row.state='running';row.result={'snapshot':snapshot};s.commit()
 try:
  row.result={**calculate(snapshot),'snapshot':snapshot};row.state='done'
  Path('/artifacts/'+str(row.id)+'.json').write_text(json.dumps(row.result,ensure_ascii=False))
 except Exception as e:row.state='failed';row.error=str(e)
 s.commit()
while True:
 Path('/tmp/heartbeat').touch()
 try:
  item=r.blpop(['camp:cleanups','camp:snapshots'],timeout=3)
  if not item:continue
  with Session() as s:
   if item[0]==b'camp:cleanups':run_cleanup(s,int(item[1]))
   else:trial(s,int(item[1]))
 except Exception:logging.exception('worker');time.sleep(2)
