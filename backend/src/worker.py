import os,time,pathlib,logging
import redis
from .database import Session
from .models import MatchRun,Entrance,Alias,Candidate
from .common import lock,rows,dump
from .matching import match
from .correction import correction_map
q=redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
def process(run_id):
 """计算一次匹配。返回 True 表示结果被采用。"""
 with Session() as s:
  r=lock(s);run=s.get(MatchRun,int(run_id))
  if not run:return False
  if run.state=='queued' and int(run.correction_version or 0)!=int(r.correction_version or 0):
   # 复测更正与匹配并发：校正版本已推进时不得用旧校正出名单。
   run.state='stale';run.error='计算期间复测对照已更新，本次结果基于旧校正，未采用；请重新计算'
   s.commit();return False
  if run.state!='queued':return False
  try:
   entrances=[dump(x) for x in rows(s,Entrance)];aliases=[dump(x) for x in rows(s,Alias)]
   result=match(entrances,aliases,correction_map(s))
   run.result=result
   for d in result['candidates']:s.add(Candidate(run_id=run.id,**d))
   run.state='ready'
  except Exception as e:run.state='failed';run.error=str(e)[:500];logging.exception('matching failed')
  s.commit()
  return run.state=='ready'
def main():
 while True:
  pathlib.Path('/artifacts/address-heartbeat').write_text(str(time.time()))
  item=q.blpop('address:matching',timeout=2)
  if item:process(item[1])
if __name__=='__main__':main()
