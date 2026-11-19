from .models import Entrance,Alias,Evidence,Batch
from .common import *
from .batch_service import _bump
def create_entrance(s,d):
 lock(s)
 if d.get('batch_id') is not None:get(s,Batch,d['batch_id'])
 x=Entrance(**d);s.add(x);s.flush();return x
def locate(s,id,d):
 lock(s);x=get(s,Entrance,id)
 changed=abs(x.lat-d['lat'])>1e-9 or abs(x.lng-d['lng'])>1e-9
 x.lat=d['lat'];x.lng=d['lng']
 if changed:
  # 坐标更正会改变校正后距离，旧名单不再代表现行校正。
  s.flush();_bump(s)
 return x
def alias(s,d):
 lock(s);get(s,Entrance,d['entrance_id']);x=Alias(**d);s.add(x);s.flush();return x
def evidence(s,d):
 lock(s);get(s,Alias,d['alias_id']);x=Evidence(**d);s.add(x);s.flush();return x
