from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import Metric,Fact,Cleanup

def save_metric(s,data,i=None):
 r=s.get(Metric,i) if i else Metric()
 if not r:raise HTTPException(404,'口径版本不存在')
 if r.locked:raise HTTPException(409,'已签核口径不可覆盖，请建立新版本')
 for k,v in data.model_dump(mode='json').items():setattr(r,k,v)
 s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'相同指标代码和版本已存在')
 return r

def save_fact(s,data,i=None):
 retired={c.class_code for c in s.query(Cleanup).all()}
 r=s.get(Fact,i) if i else Fact()
 if not r:raise HTTPException(404,'班级日事实不存在')
 if data.class_code in retired or (i and r.class_code in retired):raise HTTPException(409,'班级已进入退场清理，禁止录入或修订日报')
 for k,v in data.model_dump(mode='json').items():setattr(r,k,v)
 s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'相同班级与日期已有事实，请修订原记录')
 return r
