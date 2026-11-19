"""采点批次、复测对照与校正版本的登记。

每次对照新增、更正或删除都会推进 Registry.correction_version，并把此前
已算好的候选名单标记为 stale；现行名单因此不会继续展示旧校正的结果。
"""
from .models import Batch, Control, Entrance, MatchRun
from .common import *
from .correction import correction_map, batch_summaries


def _bump(s):
 """调用方已持有 Registry 锁；推进校正版本并作废旧候选名单。"""
 r = get(s, Registry, 1)
 r.correction_version = int(r.correction_version or 0) + 1
 for run in rows(s, MatchRun):
  if run.state == 'ready':
   run.state = 'stale'
   run.error = '复测对照或采点坐标已更新，此前候选基于旧校正，请重新计算'
 return r.correction_version


def create_batch(s, d):
 r = lock(s)
 x = Batch(**d, created=r.now)
 s.add(x)
 s.flush()
 return x


def assign_batch(s, entrance_id, batch_id):
 lock(s)
 e = get(s, Entrance, entrance_id)
 get(s, Batch, batch_id)
 if e.batch_id is not None and e.batch_id != batch_id and any(c.entrance_id == e.id for c in rows(s, Control)):
  fail('该入口已有其他批次的复测对照，不能直接改批次；请先删除原对照或登记到原批次')
 if e.batch_id != batch_id:
  e.batch_id = batch_id
  s.flush()
  _bump(s)
  s.flush()
 return e


def upsert_control(s, d):
 r = lock(s)
 e = get(s, Entrance, d['entrance_id'])
 batch = get(s, Batch, d['batch_id'])
 if e.batch_id is not None and e.batch_id != batch.id:
  fail('该入口已登记在其他采点批次，请先确认批次归属')
 if e.batch_id is None:
  e.batch_id = batch.id
 x = next((c for c in rows(s, Control) if c.entrance_id == e.id), None)
 if x is None:
  x = Control(batch_id=batch.id, entrance_id=e.id, true_lat=d['true_lat'],
              true_lng=d['true_lng'], note=d['note'], created=r.now, updated=r.now)
  s.add(x)
  s.flush()
  _bump(s)
  s.flush()
  return x
 changed = (x.batch_id != batch.id or abs(x.true_lat - d['true_lat']) > 1e-9
            or abs(x.true_lng - d['true_lng']) > 1e-9)
 x.batch_id = batch.id
 x.true_lat = d['true_lat']
 x.true_lng = d['true_lng']
 x.note = d['note']
 x.updated = r.now
 s.flush()
 if changed:
  # 只有实际改正对照坐标才推进校正版本；重复提交同一对照不影响现行名单。
  _bump(s)
  s.flush()
 return x


def remove_control(s, id):
 lock(s)
 x = get(s, Control, id)
 s.delete(x)
 s.flush()
 _bump(s)
 s.flush()
 return x


def preview(s):
 return {'batches': batch_summaries(s),
         'corrections': list(correction_map(s).values()),
         'correction_version': int(getattr(s.get(Registry, 1), 'correction_version', 0) or 0)}
