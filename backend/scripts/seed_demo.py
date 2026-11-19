import math
from src.database import Session,Base,engine
from src.models import *
from src.security import password_hash
from src.common import rows

LAT_M=111320.0
def moved(lat,lng,east,north):
 return lat+north/LAT_M,lng+east/(LAT_M*math.cos(math.radians(lat)))
def seed():
 Base.metadata.create_all(engine)
 with Session() as s:
  for role in ['operator','supervisor','viewer']:
   if not any(x.email==role+'@changqiao.local' for x in rows(s,User)):s.add(User(email=role+'@changqiao.local',password=password_hash('Address2026!'),role=role))
  if not s.get(Registry,1):s.add(Registry(id=1,now='2026-11-18T09:00:00',correction_version=0))
  s.flush()
  if not any(x.code=='CQ-018-A' for x in rows(s,Entrance)):
   batch=Batch(code='PC-11-A',name='长桥路东段11月首采',note='同批整体偏移，含一次复测对照登记错误',created='2026-11-18T08:30:00')
   s.add(batch);s.flush()
   batch2=Batch(code='PC-11-B',name='长桥路西段11月首采',note='仅一个对照，不足以估偏',created='2026-11-18T08:35:00')
   s.add(batch2);s.flush()
   rowspec=[('CQ-018-A',18,'长桥路18号正门',31.2100,121.4800,'A'),('CQ-018-B',18,'长桥路十八号旧门牌',31.2101,121.4800,'A'),('CQ-081',81,'长桥路81号',31.2110,121.4800,'A'),('CQ-018-C',18,'长桥路18号南入口',31.2102,121.4800,'A'),('CQ-019-A',19,'长桥路19号正门',31.2120,121.4800,'B'),('CQ-019-B',19,'长桥路十九号旧门牌',31.2121,121.4800,'B')]
   shift={'A':(8.0,6.0),'B':(-5.0,9.0)}
   truth={};by={}
   for code,num,label,lat,lng,bk in rowspec:
    truth[code]=(lat,lng)
    olat,olng=moved(lat,lng,*shift[bk])
    b=batch if bk=='A' else batch2
    e=Entrance(code=code,street='长桥路',number=num,label=label,lat=olat,lng=olng,batch_id=b.id);s.add(e);s.flush();by[code]=e
    a=Alias(entrance_id=e.id,text=label);s.add(a);s.flush();s.add(Evidence(alias_id=a.id,reference='照片-'+code,description='2026年11月现场门牌照片与老地籍图位置核验说明'))
   # 批次A：正门、81号、南入口三个对照彼此一致；旧门牌复测时把真值向西错记20米，作错标样本由中位数抵消。
   controls=[('CQ-018-A',0,1,'正门复测GPS与首采同批平移一致'),('CQ-081',0,0,'复测GPS与首采同批平移一致'),('CQ-018-C',0,0,'南入口复测坐标与首采差在同批平移内'),('CQ-018-B',-20,0,'复测时真值误记为向西20米，保留作错标对照样本')]
   for code,err_e,err_n,note in controls:
    tlat,tlng=moved(*truth[code],err_e,err_n)
    s.add(Control(batch_id=batch.id,entrance_id=by[code].id,true_lat=tlat,true_lng=tlng,note=note,created='2026-11-18T08:40:00',updated='2026-11-18T08:40:00'))
   # 批次B只有一个对照：不足以确认整体偏移，候选沿用文字分。
   s.add(Control(batch_id=batch2.id,entrance_id=by['CQ-019-A'].id,true_lat=truth['CQ-019-A'][0],true_lng=truth['CQ-019-A'][1],note='仅一个对照，不能代表整批偏移',created='2026-11-18T08:45:00',updated='2026-11-18T08:45:00'))
   s.flush()
   p=Proposal(code='P031',source_id=by['CQ-018-B'].id,target_id=by['CQ-018-A'].id,reason='历史十八号门牌与现18号正门同宗同入口',correction_version=0);s.add(p);s.flush()
   s.add(Objection(proposal_id=p.id,code='Y031',note='住户认为旧门牌对应独立南入口，申请现场复核',state='open'))
  s.commit()
if __name__=='__main__':seed()
