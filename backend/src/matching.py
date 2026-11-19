import re,hashlib,json,math
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import precision_score,recall_score
from sklearn.model_selection import train_test_split
from .correction import offset_m
NUM={'零':0,'〇':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
def number(text):
 m=re.search(r'([0-9零〇一二三四五六七八九十]+)号',text)
 if not m:return None
 t=m.group(1)
 if t.isdigit():return int(t)
 if '十' in t:
  a,b=t.split('十');return (NUM.get(a,1) if a else 1)*10+(NUM.get(b,0) if b else 0)
 return int(''.join(str(NUM[x]) for x in t))
def normalize(text):
 n=number(text)
 return re.sub(r'([0-9零〇一二三四五六七八九十]+)号',f'{n}号',text) if n is not None else text
# Simulated labelled historical alias pairs. Split before TFIDF fit/threshold selection.
def evaluation():
 pairs=[]
 for street in ['长桥路','青石街','河滨路','新民巷','榕树街','学府路','东湖路','西堤路','南苑街','北园街','柳岸路','梅花巷']:
  pairs.extend([(street+'18号',street+'十八号',1),(street+'18号南入口',street+'十八号南门',1),(street+'18号',street+'81号',0),(street+'18号',street+'19号',0)])
 tr,te=train_test_split(list(range(len(pairs))),test_size=.25,stratify=[x[2] for x in pairs],random_state=42)
 vec=TfidfVectorizer(analyzer='char',ngram_range=(1,3));vec.fit([normalize(t) for i in tr for t in pairs[i][:2]])
 def pred(ids,threshold):
  out=[]
  for i in ids:
   a,b,_=pairs[i];v=vec.transform([normalize(a),normalize(b)]);sim=float((v[0]@v[1].T).toarray()[0,0]);out.append(int(number(a)==number(b) and sim>=threshold))
  return out
 threshold=max([.35,.45,.55,.65,.75],key=lambda z:(precision_score([pairs[i][2] for i in tr],pred(tr,z),zero_division=0)+recall_score([pairs[i][2] for i in tr],pred(tr,z),zero_division=0),z))
 y=[pairs[i][2] for i in te];pr=pred(te,threshold)
 return {'seed':42,'train_pairs':len(tr),'holdout_pairs':len(te),'train_ids':tr,'holdout_ids':te,'precision':precision_score(y,pr,zero_division=0),'recall':recall_score(y,pr,zero_division=0),'threshold':threshold,'label_source':'模拟历史别名对；不代表真实地址精度'}
def _rank_score(similarity,distance_m):
 # 文字分与校正后距离共同排序；数字冲突只在提案阶段拦截，这里照实列出。
 d=max(distance_m,0.0);proximity=1.0/(1.0+d/50.0)
 return round(0.5*similarity+0.5*proximity,6)
def match(entrances,aliases,corrections=None):
 if len(entrances)<2 or len(aliases)<2:raise ValueError('至少两个入口和两个有文字的别名')
 texts=[normalize(a['text']) for a in aliases];vec=TfidfVectorizer(analyzer='char',ngram_range=(1,3));v=vec.fit_transform(texts);sim=(v@v.T).toarray();dist=np.clip(1-sim,0,2);np.fill_diagonal(dist,0)
 labels=AgglomerativeClustering(n_clusters=None,distance_threshold=.55,metric='precomputed',linkage='average').fit_predict(dist)
 eval=evaluation();candidates=[];by={x['id']:x for x in entrances};corr=corrections or {}
 for i,x in enumerate(entrances):
  for y in entrances[i+1:]:
   ix=[j for j,a in enumerate(aliases) if a['entrance_id']==x['id']];iy=[j for j,a in enumerate(aliases) if a['entrance_id']==y['id']]
   if not ix or not iy:continue
   score=float(max(sim[a,b] for a in ix for b in iy));conflict=x['number']!=y['number'] or x['street']!=y['street']
   if score<.2:continue
   cx=corr.get(x['id']) if isinstance(corr,dict) else None;cy=corr.get(y['id']) if isinstance(corr,dict) else None
   distance=None;applied=False;reasons=[];controls=[]
   if cx and cy and cx.get('applied') and cy.get('applied'):
    east,north=offset_m({'lat':cx['corrected_lat'],'lng':cx['corrected_lng']},{'lat':cy['corrected_lat'],'lng':cy['corrected_lng']})
    distance=round(math.hypot(east,north),3);applied=True
    controls=sorted(set(cx['control_ids'])|set(cy['control_ids']))
   else:
    for c,side in ((cx,'来源'),(cy,'目标')):
     if not c or not c.get('applied'):
      reasons.append(f"{side}入口{('#'+str(c['entrance_id']) if c else '')}：{(c or {}).get('reason') or '无可信校正'}")
   rank=_rank_score(score,distance) if applied else None
   candidates.append({'source_id':x['id'],'target_id':y['id'],'similarity':round(score,6),'conflict':int(conflict),
    'distance_m':distance,'distance_applied':int(applied),'rank_score':rank,'controls_used':controls,
    'fallback_reason':'' if applied else '；'.join(reasons) or '缺少可信校正，沿用文字分'})
 candidates.sort(key=lambda c:((c['rank_score'] is None),-(c['rank_score'] if c['rank_score'] is not None else 0),-c['similarity'],c['source_id'],c['target_id']))
 return {'algorithm':'字符TF-IDF+AgglomerativeClustering average linkage；候选按校正后距离与文字分合成排序','source_sha256':hashlib.sha256(json.dumps([entrances,aliases],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'evaluation':eval,'clusters':[{'alias_id':a['id'],'label':int(k)} for a,k in zip(aliases,labels)],'candidates':candidates}
